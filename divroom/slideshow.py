"""Server-side random art slideshow with a prefetch buffer.

ArtBuffer keeps up to `target` pieces picked-and-built ahead of time, so the
player can switch instantly instead of picking + downloading + building at
each switch. Slideshow wraps it in two daemon threads: one fills the buffer,
one shows the next piece every `hold` seconds. Both pickers/builders/players
are injectable, so the logic is tested without network, device, or real waits.
"""
import threading
from collections import deque

from . import art
from .control import Pixoo


class ArtBuffer:
    def __init__(self, year, target=10, picker=None, builder=None, frames=60):
        self.year = year
        self.target = target
        self.frames = frames
        self._picker = picker or art.random_piece
        self._builder = builder or art.build
        self._q = deque()
        self._lock = threading.Lock()

    def __len__(self):
        with self._lock:
            return len(self._q)

    def fill_once(self):
        """Prepare one piece if below target. Returns True if it did work."""
        if len(self) >= self.target:
            return False
        pack, file = self._picker(self.year)
        frames = self._builder(pack, file, frames=self.frames)
        with self._lock:
            self._q.append({"pack": pack, "file": file, "frames": frames})
        return True

    def pop(self):
        with self._lock:
            return self._q.popleft() if self._q else None


class Slideshow:
    def __init__(self, ip, year, speed=60, hold=30, target=10, frames=60,
                 picker=None, builder=None, player=None, buffer=None):
        self.ip = ip
        self.year = year
        self.speed = speed
        self.hold = hold
        self._buf = buffer or ArtBuffer(year, target=target, picker=picker,
                                        builder=builder, frames=frames)
        self._player = player or self._default_player
        self.current = None
        self.error = None
        self._stop = threading.Event()
        self._threads = []

    def _default_player(self, frames):
        Pixoo(self.ip).send_frames(frames, speed_ms=self.speed)

    def start(self):
        if self._threads:
            return self
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._fill_loop, daemon=True),
            threading.Thread(target=self._play_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()
        return self

    def _fill_loop(self):
        while not self._stop.is_set():
            try:
                if not self._buf.fill_once():
                    self._stop.wait(0.2)
            except Exception as e:
                self.error = f"fetch: {e}"
                self._stop.wait(1.0)

    def _play_loop(self):
        while not self._stop.is_set():
            item = self._buf.pop()
            if item is None:
                self._stop.wait(0.2)
                continue
            try:
                self._player(item["frames"])
                self.current = {"pack": item["pack"], "file": item["file"]}
                self.error = None
            except Exception as e:
                self.error = f"device: {e}"
            self._stop.wait(self.hold)

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)
        self._threads = []

    def status(self):
        return {
            "running": bool(self._threads) and not self._stop.is_set(),
            "year": self.year,
            "current": self.current,
            "queued": len(self._buf),
            "error": self.error,
        }
