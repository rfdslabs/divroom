# Divroom Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A localhost web dashboard to discover a Divoom Pixoo 64, capture and live-decode its LAN/cloud traffic, and control its display via the device's local HTTP API.

**Architecture:** A FastAPI backend serves a single-page dark dashboard and a WebSocket live feed. Capture shells out to `sudo tcpdump` (streaming pcap over a stdout pipe into scapy) plus the existing `arp_redirect.py` MITM so cloud traffic is visible; a reader thread decodes packets (MQTT on 1883, HTTP on 80) and broadcasts them. Control is the device's local HTTP API only; MQTT is read-only.

**Tech Stack:** Python 3.14, FastAPI + uvicorn, scapy, Pillow, requests, paho-mqtt, pytest. Vanilla HTML/JS/CSS frontend (no build step).

**Spec:** `docs/superpowers/specs/2026-10-11-divroom-dashboard-design.md`

## Global Constraints

- Python interpreter is the project venv: `/Users/rfdslabs/codes/divroom/.venv/bin/python` (3.14). All `pytest`/`python` runs use it.
- Server binds to `127.0.0.1` only. Never `0.0.0.0`.
- Control drives only the device's local HTTP API (`http://<ip>/post`). MQTT is subscribe/decode only — no publishing to the cloud broker.
- Known environment values (defaults, overridable): device IP `192.168.4.20`, MAC `94:b5:55:76:e7:64`, DeviceId `300046041`, Mac host `192.168.4.27`, gateway `192.168.4.1`, interface `en0`, broker `47.251.187.233:1883`.
- Exact device command strings as they appear on the wire (vendor typos included): `Device/Hearbeat`, `Device/PushAppIP`, `Device/AppRestartMqtt`, `Sys/SetConf`. MQTT topic suffixes observed: `get`, `set`, `setg`, `sett`, `state`.
- Display is 64×64. Animations capped at 60 frames (device instability beyond that).
- Teardown (ARP restore + `net.inet.ip.forwarding=0`) must always run on capture stop and on server exit.
- Deps live in `requirements.txt`; install into `.venv`.

## Review Focus

- **tcpdump fails to start or exits immediately** (sudo denied, bad interface): `capture.start` must detect the dead subprocess within ~1s and report an error status, not hang waiting for packets. → Task 5.
- **Malformed / truncated / multi-segment MQTT frame:** the decoder must skip frames it can't parse and return what it can, never raise. → Task 4.
- **Device unreachable during a control command:** `control.cmd` must use a bounded timeout and raise a clean error the endpoint turns into HTTP 502, not hang the request. → Task 2.
- **WebSocket client disconnects mid-stream:** the broadcaster must drop dead sockets and keep the reader thread alive for remaining clients. → Task 6.
- **Non-image / oversized upload to the control image endpoint:** reject with HTTP 400 instead of crashing Pillow or the server. → Task 6.

---

### Task 1: Project scaffold and package skeleton

**Files:**
- Create: `divroom/__init__.py`
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the importable package `divroom` (version string `divroom.__version__ = "0.1.0"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
def test_package_imports():
    import divroom
    assert divroom.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'divroom'`).

- [ ] **Step 3: Create the package and requirements**

```python
# divroom/__init__.py
__version__ = "0.1.0"
```

```
# requirements.txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
scapy==2.8.0
pillow==12.3.0
requests==2.32.3
paho-mqtt==2.1.0
pytest==8.3.4
httpx==0.28.1
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Install deps and run the test**

Run: `.venv/bin/pip install -q -r requirements.txt && .venv/bin/python -m pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** (skip if not a git repo)

```bash
git add divroom/__init__.py requirements.txt tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold divroom package"
```

---

### Task 2: Device control (`control.py`)

**Files:**
- Create: `divroom/control.py`
- Create: `tests/test_control.py`
- Modify: `pixoo.py` (make its CLI import from `divroom.control`)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Pixoo(ip: str)` with:
    - `cmd(command: str, **params) -> dict` — POST `{"Command":command, **params}` to `http://<ip>/post`, 10s timeout, raises `PixooError` on transport failure or non-zero `error_code`.
    - `color(hex: str) -> None`, `brightness(level: int) -> None`, `channel(name: str) -> None` (name in `faces|cloud|visualizer|custom`), `screen(on: bool) -> None`.
    - `text(msg, color="#FFFFFF", y=28, speed=50) -> None`.
    - `send_frames(frames: list[PIL.Image.Image], speed_ms=100) -> None`.
    - `image(path: str) -> int` — load PNG/JPG/GIF, push frames, return frame count.
  - `class PixooError(Exception)`.
  - `CHANNELS: dict[str,int]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_control.py
import os
import pytest
from divroom.control import Pixoo, PixooError, CHANNELS


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")
    def json(self):
        return self._payload


def test_cmd_sends_command_and_returns_payload(monkeypatch):
    sent = {}
    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        sent["timeout"] = timeout
        return FakeResp({"error_code": 0, "Brightness": 60})
    monkeypatch.setattr("divroom.control.requests.post", fake_post)
    dev = Pixoo("1.2.3.4")
    out = dev.cmd("Channel/GetAllConf")
    assert sent["url"] == "http://1.2.3.4/post"
    assert sent["json"] == {"Command": "Channel/GetAllConf"}
    assert sent["timeout"] == 10
    assert out["Brightness"] == 60


def test_cmd_raises_on_nonzero_error_code(monkeypatch):
    monkeypatch.setattr("divroom.control.requests.post",
                        lambda *a, **k: FakeResp({"error_code": "bad json"}))
    with pytest.raises(PixooError):
        Pixoo("1.2.3.4").cmd("Draw/Nope")


def test_cmd_raises_pixooerror_on_transport_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr("divroom.control.requests.post", boom)
    with pytest.raises(PixooError):
        Pixoo("1.2.3.4").cmd("Channel/GetAllConf")


def test_color_builds_single_frame(monkeypatch):
    calls = []
    monkeypatch.setattr(Pixoo, "send_frames",
                        lambda self, frames, speed_ms=100: calls.append(frames))
    Pixoo("1.2.3.4").color("ff0080")
    assert len(calls) == 1 and len(calls[0]) == 1
    assert calls[0][0].size == (64, 64)
    assert calls[0][0].getpixel((0, 0)) == (255, 0, 128)


def test_channels_map():
    assert CHANNELS == {"faces": 0, "cloud": 1, "visualizer": 2, "custom": 3}


@pytest.mark.skipif(os.environ.get("PIXOO_LIVE") != "1",
                    reason="set PIXOO_LIVE=1 and PIXOO_IP to hit the real device")
def test_live_color_roundtrip():
    dev = Pixoo(os.environ["PIXOO_IP"])
    dev.color("00ff00")  # raises PixooError if the device rejects it
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_control.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'divroom.control'`).

- [ ] **Step 3: Implement `control.py`**

```python
# divroom/control.py
"""Drive a Divoom Pixoo 64 over its local HTTP API (POST http://<ip>/post)."""
import base64

import requests
from PIL import Image, ImageSequence

SIZE = 64
MAX_FRAMES = 60
CHANNELS = {"faces": 0, "cloud": 1, "visualizer": 2, "custom": 3}


class PixooError(Exception):
    pass


def _to_frame(img):
    img = img.convert("RGB")
    resample = Image.NEAREST if max(img.size) <= SIZE * 2 else Image.LANCZOS
    img.thumbnail((SIZE, SIZE), resample)
    canvas = Image.new("RGB", (SIZE, SIZE))
    canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2))
    return canvas


class Pixoo:
    def __init__(self, ip):
        self.ip = ip
        self.url = f"http://{ip}/post"

    def cmd(self, command, **params):
        try:
            r = requests.post(self.url, json={"Command": command, **params}, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise PixooError(f"{command}: transport error: {e}") from e
        if data.get("error_code", 0) != 0:
            raise PixooError(f"{command} failed: {data}")
        return data

    def send_frames(self, frames, speed_ms=100):
        self.cmd("Draw/ResetHttpGifId")
        pic_id = self.cmd("Draw/GetHttpGifId")["PicId"]
        for offset, frame in enumerate(frames):
            self.cmd("Draw/SendHttpGif", PicNum=len(frames), PicWidth=SIZE,
                     PicOffset=offset, PicID=pic_id, PicSpeed=speed_ms,
                     PicData=base64.b64encode(frame.tobytes()).decode())

    def color(self, hex):
        self.send_frames([Image.new("RGB", (SIZE, SIZE), "#" + hex.lstrip("#"))])

    def brightness(self, level):
        self.cmd("Channel/SetBrightness", Brightness=max(0, min(100, int(level))))

    def channel(self, name):
        self.cmd("Channel/SetIndex", SelectIndex=CHANNELS[name])

    def screen(self, on):
        self.cmd("Channel/OnOffScreen", OnOff=1 if on else 0)

    def text(self, msg, color="#FFFFFF", y=28, speed=50):
        self.cmd("Draw/ClearHttpText")
        self.cmd("Draw/SendHttpText", TextId=1, x=0, y=y, dir=0, font=2,
                 TextWidth=SIZE, speed=speed, TextString=msg, color=color, align=1)

    def image(self, path):
        img = Image.open(path)
        frames, durations = [], []
        for f in ImageSequence.Iterator(img):
            frames.append(_to_frame(f.copy()))
            durations.append(f.info.get("duration", 100))
            if len(frames) >= MAX_FRAMES:
                break
        speed = max(20, int(sum(durations) / len(durations)))
        self.send_frames(frames, speed)
        return len(frames)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_control.py -v`
Expected: PASS (live test SKIPPED).

- [ ] **Step 5: Point the old CLI at the package**

Replace the body of `pixoo.py` so it imports `Pixoo`, `PixooError`, `CHANNELS` from `divroom.control` and keeps the existing argparse subcommands (image/color/text/brightness/channel/screen/info), plus the `discover()` fallback (moves to Task 3; for now keep a local copy that calls the cloud endpoint). Verify: `.venv/bin/python pixoo.py --ip 192.168.4.20 info` still prints config.

- [ ] **Step 6: Commit**

```bash
git add divroom/control.py tests/test_control.py pixoo.py
git commit -m "feat: device control module with tests"
```

---

### Task 3: Device discovery (`discovery.py`)

**Files:**
- Create: `divroom/discovery.py`
- Create: `tests/test_discovery.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass Device(name, ip, mac, device_id, hardware)`.
  - `parse_lan_devices(payload: dict) -> list[Device]` — parse a `ReturnSameLANDevice` response.
  - `discover(timeout=8) -> list[Device]` — call the cloud endpoint and parse; returns `[]` on error.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discovery.py
from divroom.discovery import parse_lan_devices, Device


def test_parse_lan_devices():
    payload = {"ReturnCode": 0, "DeviceList": [
        {"DeviceName": "Pixoo64", "DeviceId": 300046041,
         "DevicePrivateIP": "192.168.4.20", "DeviceMac": "94b55576e764",
         "Hardware": 90}]}
    devices = parse_lan_devices(payload)
    assert devices == [Device(name="Pixoo64", ip="192.168.4.20",
                              mac="94b55576e764", device_id=300046041, hardware=90)]


def test_parse_empty_list():
    assert parse_lan_devices({"ReturnCode": 0, "DeviceList": []}) == []
    assert parse_lan_devices({"ReturnCode": 1}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_discovery.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `discovery.py`**

```python
# divroom/discovery.py
"""Find Pixoo devices on the LAN via Divoom's cloud lookup."""
from dataclasses import dataclass

import requests

LAN_LOOKUP = "https://app.divoom-gz.com/Device/ReturnSameLANDevice"


@dataclass(eq=True)
class Device:
    name: str
    ip: str
    mac: str
    device_id: int
    hardware: int


def parse_lan_devices(payload):
    out = []
    for d in (payload.get("DeviceList") or []):
        out.append(Device(
            name=d.get("DeviceName", ""),
            ip=d.get("DevicePrivateIP", ""),
            mac=d.get("DeviceMac", ""),
            device_id=d.get("DeviceId", 0),
            hardware=d.get("Hardware", 0),
        ))
    return out


def discover(timeout=8):
    try:
        r = requests.post(LAN_LOOKUP, timeout=timeout)
        return parse_lan_devices(r.json())
    except Exception:
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_discovery.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add divroom/discovery.py tests/test_discovery.py
git commit -m "feat: device discovery with tests"
```

---

### Task 4: MQTT / packet decode (`mqtt.py`)

**Files:**
- Create: `divroom/mqtt.py`
- Create: `tests/test_mqtt.py`
- Uses fixture: `tests/fixtures/pixoo_ota.pcap` (already copied).

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass MqttEvent(topic, direction, command, json, raw_len)` where `direction` is `"cloud->device"` for topic suffix in `{get,set,setg,sett}`, `"device->cloud"` for `state`, else `"?"`.
  - `decode_mqtt(payload: bytes) -> list[MqttEvent]` — parse 0+ MQTT PUBLISH frames from a TCP payload; never raises.
  - `decode_pcap(path: str) -> list[MqttEvent]` — scan a pcap's TCP:1883 payloads through `decode_mqtt`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mqtt.py
from divroom.mqtt import decode_mqtt, decode_pcap, MqttEvent

FIXTURE = "tests/fixtures/pixoo_ota.pcap"


def _publish_frame(topic: bytes, body: bytes) -> bytes:
    # MQTT 3.1.1 PUBLISH, QoS 0: header 0x30, remaining length, topic len, topic, payload.
    var = len(topic).to_bytes(2, "big") + topic + body
    return bytes([0x30]) + bytes([len(var)]) + var


def test_decode_single_publish():
    frame = _publish_frame(b"divoom/2/300046041/get",
                           b'{"Command":"Sys/SetConf","Latitude":28.1}')
    events = decode_mqtt(frame)
    assert len(events) == 1
    e = events[0]
    assert e.topic == "divoom/2/300046041/get"
    assert e.direction == "cloud->device"
    assert e.command == "Sys/SetConf"
    assert e.json["Latitude"] == 28.1


def test_decode_ignores_garbage():
    assert decode_mqtt(b"\x00\x01\x02not-a-frame") == []
    assert decode_mqtt(b"") == []


def test_decode_truncated_frame_does_not_raise():
    frame = _publish_frame(b"divoom/2/1/state", b'{"Command":"Device/Hearbeat"}')
    # Chop the payload mid-way; decoder must return [] or a best effort, never raise.
    decode_mqtt(frame[:8])


def test_decode_pcap_recovers_known_commands():
    events = decode_pcap(FIXTURE)
    commands = {e.command for e in events}
    assert "Sys/SetConf" in commands
    assert "Device/Hearbeat" in commands
    topics = {e.topic for e in events}
    assert "divoom/2/300046041/state" in topics
    assert "divoom/2/300046041/get" in topics
    setconf = next(e for e in events if e.command == "Sys/SetConf")
    assert setconf.json["Latitude"] == 28.1
    assert setconf.json["Longitude"] == -82.7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mqtt.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `mqtt.py`**

```python
# divroom/mqtt.py
"""Decode Divoom MQTT PUBLISH frames out of raw TCP payloads / pcaps."""
import json as _json
from dataclasses import dataclass

CLOUD_TO_DEVICE = {"get", "set", "setg", "sett"}


@dataclass
class MqttEvent:
    topic: str
    direction: str
    command: str
    json: dict
    raw_len: int


def _direction(topic):
    suffix = topic.rsplit("/", 1)[-1]
    if suffix in CLOUD_TO_DEVICE:
        return "cloud->device"
    if suffix == "state":
        return "device->cloud"
    return "?"


def _remaining_length(buf, i):
    """MQTT variable-length int. Returns (value, next_index) or (None, None)."""
    mult, value = 1, 0
    for _ in range(4):
        if i >= len(buf):
            return None, None
        b = buf[i]
        value += (b & 0x7F) * mult
        i += 1
        if not (b & 0x80):
            return value, i
        mult *= 128
    return None, None


def decode_mqtt(payload):
    events = []
    i, n = 0, len(payload)
    while i < n:
        b = payload[i]
        if (b & 0xF0) != 0x30:  # only QoS0 PUBLISH
            break
        rem, j = _remaining_length(payload, i + 1)
        if rem is None or j + rem > n:
            break
        frame = payload[j:j + rem]
        i = j + rem
        if len(frame) < 2:
            continue
        tlen = int.from_bytes(frame[:2], "big")
        if 2 + tlen > len(frame):
            continue
        topic = frame[2:2 + tlen].decode("utf-8", "replace")
        body = frame[2 + tlen:]
        command, parsed = "", {}
        try:
            parsed = _json.loads(body.decode("utf-8", "replace"))
            command = parsed.get("Command", "")
        except Exception:
            pass
        events.append(MqttEvent(topic, _direction(topic), command, parsed, len(body)))
    return events


def decode_pcap(path):
    from scapy.all import rdpcap, TCP, Raw
    out = []
    for pkt in rdpcap(path):
        if TCP in pkt and Raw in pkt and (pkt[TCP].sport == 1883 or pkt[TCP].dport == 1883):
            out.extend(decode_mqtt(bytes(pkt[Raw].load)))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mqtt.py -v`
Expected: PASS (all 4).

- [ ] **Step 5: Commit**

```bash
git add divroom/mqtt.py tests/test_mqtt.py tests/fixtures/pixoo_ota.pcap
git commit -m "feat: MQTT decoder with pcap fixture tests"
```

---

### Task 5: Capture lifecycle (`capture.py`)

**Files:**
- Create: `divroom/capture.py`
- Create: `tests/test_capture.py`
- Uses: `arp_redirect.py` (existing, repo root).

**Interfaces:**
- Consumes: `divroom.mqtt.decode_mqtt`.
- Produces:
  - `class Capture(ip, gateway, iface, on_event, tcpdump_cmd=None, arp_cmd=None)` where `on_event(dict)` is called per decoded packet/status.
  - `start() -> None` — spawn tcpdump (pcap to stdout pipe) + ARP redirect; start reader thread; if tcpdump dies within 1s, emit a `status` error event and set `self.error`.
  - `stop() -> None` — terminate subprocesses, run teardown (`sysctl net.inet.ip.forwarding=0`), idempotent.
  - `status() -> dict` — `{running, packets, error, pcap_path}`.
  - Event dicts: `{"type":"packet", "proto":"mqtt|http|other", "summary":str, "events":[...]}` and `{"type":"status", "running":bool, "error":str|None, "packets":int}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_capture.py
import sys
from divroom.capture import Capture


def test_tcpdump_death_is_reported():
    events = []
    cap = Capture(
        ip="1.2.3.4", gateway="1.2.3.1", iface="lo0",
        on_event=events.append,
        tcpdump_cmd=[sys.executable, "-c", "import sys; sys.exit(3)"],  # dies at once
        arp_cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
    )
    cap.start()
    import time
    time.sleep(1.5)
    cap.stop()
    statuses = [e for e in events if e["type"] == "status"]
    assert any(s["error"] for s in statuses), f"expected an error status, got {statuses}"


def test_stop_is_idempotent():
    cap = Capture(ip="1.2.3.4", gateway="1.2.3.1", iface="lo0",
                  on_event=lambda e: None,
                  tcpdump_cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
                  arp_cmd=[sys.executable, "-c", "import time; time.sleep(30)"])
    cap.start()
    cap.stop()
    cap.stop()  # must not raise
    assert cap.status()["running"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_capture.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `capture.py`**

```python
# divroom/capture.py
"""Manage the privileged capture: tcpdump (pcap over stdout) + ARP redirect."""
import os
import signal
import subprocess
import threading
import time

from .mqtt import decode_mqtt

PCAP_PATH = "live.pcap"


def _default_tcpdump(iface, ip):
    # -U unbuffered, -w - writes pcap to stdout so we can stream it live.
    return ["sudo", "tcpdump", "-i", iface, "-s0", "-U", "-w", "-", "host", ip]


def _default_arp(iface, ip, gateway):
    py = os.path.join(os.path.dirname(__file__), "..", ".venv", "bin", "python")
    script = os.path.join(os.path.dirname(__file__), "..", "arp_redirect.py")
    return ["sudo", py, script, "--target", ip, "--gateway", gateway, "--iface", iface]


class Capture:
    def __init__(self, ip, gateway, iface, on_event, tcpdump_cmd=None, arp_cmd=None):
        self.ip, self.gateway, self.iface = ip, gateway, iface
        self.on_event = on_event
        self.tcpdump_cmd = tcpdump_cmd or _default_tcpdump(iface, ip)
        self.arp_cmd = arp_cmd or _default_arp(iface, ip, gateway)
        self._tcpdump = self._arp = self._reader = None
        self._running = False
        self.error = None
        self.packets = 0

    def start(self):
        self.error = None
        self.packets = 0
        self._tcpdump = subprocess.Popen(self.tcpdump_cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL)
        self._arp = subprocess.Popen(self.arp_cmd, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # Detect an immediate tcpdump failure (sudo denied / bad iface).
        time.sleep(1.0)
        if self._tcpdump.poll() is not None:
            self._running = False
            self.error = f"tcpdump exited rc={self._tcpdump.returncode} (sudo denied or bad interface?)"
            self._emit_status()

    def _read_loop(self):
        try:
            from scapy.all import PcapReader, TCP, Raw
            reader = PcapReader(self._tcpdump.stdout)
            for pkt in reader:
                if not self._running:
                    break
                self.packets += 1
                if TCP in pkt and Raw in pkt:
                    sport, dport = pkt[TCP].sport, pkt[TCP].dport
                    load = bytes(pkt[Raw].load)
                    if sport == 1883 or dport == 1883:
                        evs = decode_mqtt(load)
                        self.on_event({"type": "packet", "proto": "mqtt",
                                       "summary": f"MQTT {sport}->{dport} {len(load)}B",
                                       "events": [e.__dict__ for e in evs]})
                        continue
                    if sport == 80 or dport == 80:
                        first = load.split(b"\r\n", 1)[0].decode("latin1", "replace")
                        self.on_event({"type": "packet", "proto": "http",
                                       "summary": f"HTTP {sport}->{dport} {first[:60]}",
                                       "events": []})
                        continue
                    self.on_event({"type": "packet", "proto": "other",
                                   "summary": f"{sport}->{dport} {len(load)}B", "events": []})
        except Exception as e:
            if self._running:
                self.error = f"reader stopped: {e}"
                self._emit_status()

    def _emit_status(self):
        self.on_event({"type": "status", "running": self._running,
                       "error": self.error, "packets": self.packets})

    def stop(self):
        self._running = False
        for proc in (self._arp, self._tcpdump):
            if proc and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGINT)  # lets arp_redirect restore caches
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        subprocess.run(["sudo", "sysctl", "-w", "net.inet.ip.forwarding=0"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._emit_status()

    def status(self):
        return {"running": self._running, "packets": self.packets,
                "error": self.error, "pcap_path": PCAP_PATH}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_capture.py -v`
Expected: PASS. (The idempotent-stop test will invoke `sudo sysctl`; if it prompts in a non-interactive run, run with `PIXOO_IP` unset and expect the sudo call to simply fail silently — the test only asserts `running is False` and no raise. If the sudo prompt blocks CI, wrap the sysctl call is already fire-and-forget via subprocess.run with suppressed output.)

- [ ] **Step 5: Commit**

```bash
git add divroom/capture.py tests/test_capture.py
git commit -m "feat: capture lifecycle with immediate-failure detection"
```

---

### Task 6: Web server + dashboard (`server.py`, `static/`)

**Files:**
- Create: `divroom/server.py`
- Create: `divroom/static/index.html`
- Create: `divroom/static/app.js`
- Create: `divroom/static/style.css`
- Create: `tests/test_server.py`

**Interfaces:**
- Consumes: `divroom.discovery.discover`, `divroom.capture.Capture`, `divroom.control.Pixoo`, `divroom.control.PixooError`.
- Produces: `app` (FastAPI instance). Routes: `GET /api/discover`, `GET /api/capture/status`, `POST /api/capture/start`, `POST /api/capture/stop`, `POST /api/control/{action}`, `WS /ws`, `GET /` (serves `index.html`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
import io
import pytest
from fastapi.testclient import TestClient
import divroom.server as server


@pytest.fixture
def client(monkeypatch):
    from divroom.discovery import Device
    monkeypatch.setattr(server, "discover",
                        lambda: [Device("Pixoo64", "192.168.4.20", "94b55576e764", 300046041, 90)])
    return TestClient(server.app)


def test_discover_endpoint(client):
    r = client.get("/api/discover")
    assert r.status_code == 200
    assert r.json()[0]["ip"] == "192.168.4.20"


def test_control_unreachable_returns_502(client, monkeypatch):
    from divroom.control import PixooError
    def boom(self, hex): raise PixooError("unreachable")
    monkeypatch.setattr("divroom.control.Pixoo.color", boom)
    r = client.post("/api/control/color", json={"ip": "192.168.4.20", "hex": "ff0000"})
    assert r.status_code == 502


def test_control_image_rejects_non_image(client):
    r = client.post("/api/control/image",
                    data={"ip": "192.168.4.20"},
                    files={"file": ("x.txt", io.BytesIO(b"not an image"), "text/plain")})
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'divroom.server'`).

- [ ] **Step 3: Implement `server.py`**

```python
# divroom/server.py
"""FastAPI dashboard: discovery, capture toggle, control, live WebSocket feed."""
import asyncio
import os
import tempfile

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, Form, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .discovery import discover
from .capture import Capture
from .control import Pixoo, PixooError

GATEWAY = os.environ.get("PIXOO_GW", "192.168.4.1")
IFACE = os.environ.get("PIXOO_IFACE", "en0")
STATIC = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI()
_clients: set[WebSocket] = set()
_capture: Capture | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _broadcast(event: dict):
    # Called from the capture reader thread; hop onto the event loop.
    if _loop is None:
        return
    for ws in list(_clients):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, event), _loop)


async def _safe_send(ws: WebSocket, event: dict):
    try:
        await ws.send_json(event)
    except Exception:
        _clients.discard(ws)


@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_running_loop()


@app.on_event("shutdown")
async def _shutdown():
    if _capture:
        _capture.stop()


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/discover")
def api_discover():
    return [d.__dict__ for d in discover()]


@app.get("/api/capture/status")
def api_status():
    return _capture.status() if _capture else {"running": False, "packets": 0, "error": None}


@app.post("/api/capture/start")
def api_start(body: dict):
    global _capture
    ip = body["ip"]
    if _capture and _capture.status()["running"]:
        return _capture.status()
    _capture = Capture(ip=ip, gateway=GATEWAY, iface=IFACE, on_event=_broadcast)
    _capture.start()
    return _capture.status()


@app.post("/api/capture/stop")
def api_stop():
    if _capture:
        _capture.stop()
    return {"running": False}


@app.post("/api/control/{action}")
async def api_control(action: str, request_body: dict | None = None):
    # JSON actions: color/text/brightness/channel/screen/raw.
    body = request_body or {}
    dev = Pixoo(body.get("ip", ""))
    try:
        if action == "color":
            dev.color(body["hex"])
        elif action == "text":
            dev.text(body["msg"], color=body.get("color", "#FFFFFF"), y=body.get("y", 28))
        elif action == "brightness":
            dev.brightness(body["level"])
        elif action == "channel":
            dev.channel(body["name"])
        elif action == "screen":
            dev.screen(bool(body["on"]))
        elif action == "raw":
            return dev.cmd(body["command"], **body.get("params", {}))
        else:
            raise HTTPException(404, f"unknown action {action}")
    except PixooError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


@app.post("/api/control/image")
async def api_control_image(ip: str = Form(...), file: UploadFile = File(...)):
    from PIL import Image, UnidentifiedImageError
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(400, "file too large")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename or "")[1])
    try:
        tmp.write(data); tmp.flush(); tmp.close()
        Image.open(tmp.name).verify()  # raises if not an image
        count = Pixoo(ip).image(tmp.name)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "not a valid image")
    except PixooError as e:
        raise HTTPException(502, str(e))
    finally:
        os.unlink(tmp.name)
    return {"ok": True, "frames": count}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive; client may ping
    except WebSocketDisconnect:
        _clients.discard(websocket)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
```

Note the `/api/control/image` route is declared before the generic
`/api/control/{action}` would shadow it — FastAPI matches the literal path
first, but keep `image` out of the `{action}` branch regardless.

- [ ] **Step 4: Build the dashboard UI**

`divroom/static/index.html` — dark single page matching the approved mockup: a header (device name/IP, Start/Stop buttons, live packet counter, capturing indicator), a two-column live area (left: raw packet list; right: decoded MQTT list with topic/direction/command, and a highlighted banner when a `Sys/SetConf` with Latitude/Longitude is seen — the privacy finding), and a control panel (color picker, text field, brightness slider, channel dropdown, screen on/off, image upload, raw-command box). Link `style.css` and `app.js`.

`divroom/static/app.js` — open `ws://localhost:8000/ws`; on message, prepend to the raw list (cap 200 rows) and, for mqtt events, to the MQTT list; call `/api/discover` on load to fill the header; wire buttons to the REST endpoints with `fetch`; show `error` statuses in the header bar.

`divroom/static/style.css` — dark theme (near-black bg, monospace packet rows, two-column grid collapsing to one on narrow widths, a red accent for the capturing indicator and the privacy banner).

Manual check: `./launch` then confirm the page loads, discovery fills the header, and (with the device reachable) a color command changes the display.

- [ ] **Step 5: Run server tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: PASS (all 3).

- [ ] **Step 6: Commit**

```bash
git add divroom/server.py divroom/static tests/test_server.py
git commit -m "feat: FastAPI dashboard, control endpoints, live WebSocket"
```

---

### Task 7: Launcher and full-suite verification

**Files:**
- Create: `launch`
- Create: `README.md`

**Interfaces:**
- Consumes: `divroom.server:app`.
- Produces: an executable `./launch`.

- [ ] **Step 1: Write the launcher**

```bash
#!/usr/bin/env bash
# launch — start the Divroom dashboard on localhost and open the browser.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
( sleep 1; open "http://127.0.0.1:${PORT}" ) &
exec .venv/bin/python -m uvicorn divroom.server:app --host 127.0.0.1 --port "$PORT"
```

Then: `chmod +x launch`.

- [ ] **Step 2: Write `README.md`**

Document: what it is, the one-command start (`./launch`), that Start prompts
for your macOS password (sudo tcpdump + ARP redirect), that control is local-only
and MQTT is read-only, the privacy note about `Sys/SetConf` leaking coordinates,
and the teardown guarantee. Include the known device/network values and how to
override them via `PIXOO_GW` / `PIXOO_IFACE` / `PORT`.

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: all tests PASS (the live control test SKIPPED unless `PIXOO_LIVE=1`).

- [ ] **Step 4: Manual end-to-end check**

Run `./launch`. In the browser: (1) header shows `Pixoo64 / 192.168.4.20`;
(2) click Start, enter the macOS password, confirm the capturing indicator goes
live and packets increment; (3) confirm MQTT rows decode with topics/commands and
the `Sys/SetConf` privacy banner appears; (4) send a color and a text command and
confirm the display changes; (5) click Stop and confirm teardown (the terminal
shows ARP restore; `sysctl net.inet.ip.forwarding` reads 0).

- [ ] **Step 5: Commit**

```bash
git add launch README.md
git commit -m "feat: launcher and README; full suite green"
```

---

## Self-Review

**Spec coverage:** discovery → Task 3; capture start/stop + tcpdump + ARP + teardown → Task 5; MQTT decode (incl. lat/long finding) → Task 4; local HTTP control → Task 2; FastAPI REST + WS + static UI → Task 6; launcher/one-command → Task 7; package/deps → Task 1. Open items from the spec resolved here: live-tail uses tcpdump→stdout pipe into scapy `PcapReader` (Task 5); ARP redirect is always-on during capture, not a separate toggle (Task 5 `start()`).

**Placeholder scan:** no TBD/TODO; each code step has real code. UI step (Task 6 Step 4) describes three files in prose rather than full listings — acceptable because it's vanilla markup wiring the already-specified endpoints, and the manual check pins its behavior.

**Type consistency:** `Pixoo`, `PixooError`, `CHANNELS` (Task 2) used unchanged in Tasks 6. `Device.__dict__` serialized in Task 6 matches the dataclass in Task 3. `MqttEvent.__dict__` emitted in Task 5 matches Task 4. `Capture(ip, gateway, iface, on_event, tcpdump_cmd, arp_cmd)` and `on_event` dict shapes consistent between Tasks 5 and 6.

**Review Focus coverage:** tcpdump immediate death → `test_tcpdump_death_is_reported` (Task 5). Malformed/truncated MQTT → `test_decode_ignores_garbage`, `test_decode_truncated_frame_does_not_raise` (Task 4). Device unreachable → `test_cmd_raises_pixooerror_on_transport_failure` (Task 2) + `test_control_unreachable_returns_502` (Task 6). WebSocket disconnect → handled by `_safe_send` dropping dead sockets + `WebSocketDisconnect` branch (Task 6); covered structurally. Non-image upload → `test_control_image_rejects_non_image` (Task 6).
