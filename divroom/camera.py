"""Stream a Mac webcam to the Pixoo via ffmpeg's avfoundation input.

ffmpeg grabs the camera, center-crops to square, and scales to 64x64 rgb24,
piping raw frames to us; a reader thread keeps the latest frame and a pusher
thread sends it to the device as fast as the HTTP API allows. Capture rate and
push rate are decoupled, so we always show the freshest frame (no lag buildup).

macOS note: ffmpeg can only open the camera when the process that launched it
has been granted Camera access (System Settings > Privacy & Security > Camera).
If no frame arrives within first_frame_timeout, status reports that instead of
hanging. The frame source is injectable, so the logic is tested without hardware.
"""
import re
import subprocess
import threading
import time

from PIL import Image

from .control import SIZE, Pixoo

FRAME_BYTES = SIZE * SIZE * 3


def to_panel(img):
    """Center-crop to square and scale to SIZExSIZE RGB."""
    img = img.convert("RGB")
    w, h = img.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    img = img.crop((left, top, left + s, top + s))
    if img.size != (SIZE, SIZE):
        img = img.resize((SIZE, SIZE), Image.LANCZOS if s > SIZE else Image.NEAREST)
    return img


def _parse_devices(text):
    """Pull [index] name video devices out of `ffmpeg -list_devices` output."""
    out, in_video = [], False
    for line in text.splitlines():
        low = line.lower()
        if "video devices" in low:
            in_video = True; continue
        if "audio devices" in low:
            in_video = False; continue
        if not in_video:
            continue
        m = re.search(r"\[(\d+)\]\s+(.+?)\s*$", line)
        if m and "capture screen" not in m.group(2).lower():
            out.append({"index": int(m.group(1)), "name": m.group(2)})
    return out


def list_devices(timeout=10):
    try:
        p = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation",
                            "-list_devices", "true", "-i", ""],
                           capture_output=True, text=True, timeout=timeout)
        return _parse_devices(p.stderr)
    except Exception:
        return []


def _ffmpeg_cmd(index, fps, video_size):
    return ["ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "avfoundation", "-framerate", str(fps),
            "-video_size", video_size, "-i", str(index),
            "-vf", rf"crop=min(iw\,ih):min(iw\,ih),scale={SIZE}:{SIZE}",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]


class CameraStream:
    def __init__(self, ip, index=0, fps=12, video_size="640x480", speed=100,
                 player=None, source=None, first_frame_timeout=6):
        self.ip = ip
        self.index = index
        self.fps = fps
        self.video_size = video_size
        self.speed = speed
        self._player = player or self._default_player
        self._source = source          # iterable of PIL images, or None -> ffmpeg
        self._first_timeout = first_frame_timeout
        self.frames_sent = 0
        self.error = None
        self.started_at = None
        self._latest = None
        self._read_count = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads = []
        self._proc = None

    def _default_player(self, frame):
        Pixoo(self.ip).send_frames([frame], speed_ms=self.speed)

    def _iter_source(self):
        return iter(self._source) if self._source is not None else self._ffmpeg_frames()

    def _ffmpeg_frames(self):
        self._proc = subprocess.Popen(_ffmpeg_cmd(self.index, self.fps, self.video_size),
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while not self._stop.is_set():
            buf = self._proc.stdout.read(FRAME_BYTES)
            if not buf or len(buf) < FRAME_BYTES:
                break
            yield Image.frombytes("RGB", (SIZE, SIZE), buf)

    def start(self):
        if self._threads:
            return self
        self._stop.clear()
        self.started_at = time.time()
        self._threads = [
            threading.Thread(target=self._read_loop, daemon=True),
            threading.Thread(target=self._push_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()
        return self

    def _read_loop(self):
        try:
            for frame in self._iter_source():
                if self._stop.is_set():
                    break
                f = to_panel(frame)
                with self._lock:
                    self._latest = f
                    self._read_count += 1
        except Exception as e:
            self.error = f"capture: {e}"
        # surface an ffmpeg startup failure (bad index/size, etc.)
        if self._proc and self._read_count == 0 and not self._stop.is_set():
            err = (self._proc.stderr.read() or b"").decode("utf-8", "replace").strip()
            if err:
                self.error = f"ffmpeg: {err[:300]}"

    def _push_loop(self):
        last = -1
        while not self._stop.is_set():
            with self._lock:
                f, rc = self._latest, self._read_count
            if f is None or rc == last:
                if (self._read_count == 0 and self.error is None
                        and time.time() - self.started_at > self._first_timeout):
                    self.error = ("no camera frames within "
                                  f"{self._first_timeout}s — on macOS grant Camera access to "
                                  "your terminal (System Settings ▸ Privacy & Security ▸ Camera), "
                                  "then retry")
                self._stop.wait(0.02)
                continue
            try:
                self._player(f)
                self.frames_sent += 1
                last = rc
            except Exception as e:
                self.error = f"device: {e}"
                self._stop.wait(0.1)

    def stop(self):
        self._stop.set()
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
        for t in self._threads:
            t.join(timeout=2)
        self._threads = []

    def status(self):
        elapsed = (time.time() - self.started_at) if self.started_at else 0
        fps = round(self.frames_sent / elapsed, 1) if elapsed > 0.5 else 0
        return {
            "running": bool(self._threads) and not self._stop.is_set(),
            "index": self.index,
            "frames_sent": self.frames_sent,
            "fps": fps,
            "error": self.error,
        }
