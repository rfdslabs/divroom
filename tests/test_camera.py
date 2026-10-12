import time

from PIL import Image

from divroom import camera
from divroom.control import SIZE


SAMPLE = """
[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Camera
[AVFoundation indev @ 0x1] [1] rfds Camera
[AVFoundation indev @ 0x1] [4] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] rfds Microphone
"""


def test_parse_devices_video_only_excludes_screen_and_audio():
    devs = camera._parse_devices(SAMPLE)
    assert {"index": 0, "name": "MacBook Pro Camera"} in devs
    assert {"index": 1, "name": "rfds Camera"} in devs
    names = [d["name"] for d in devs]
    assert all("Capture screen" not in n for n in names)   # screens dropped
    assert "rfds Microphone" not in names                  # audio section dropped


def test_to_panel_center_crops_to_square_64():
    out = camera.to_panel(Image.new("RGB", (100, 60), (10, 20, 30)))
    assert out.size == (SIZE, SIZE) and out.mode == "RGB"


def test_stream_pushes_normalized_frames():
    pushed = []
    src = [Image.new("RGB", (100, 80), (v, v, v)) for v in (50, 100, 150)]
    s = camera.CameraStream(ip="x", source=src, player=pushed.append, first_frame_timeout=5)
    s.start()
    deadline = time.time() + 5
    while s.status()["frames_sent"] < 1 and time.time() < deadline:
        time.sleep(0.02)
    running = s.status()["running"]
    s.stop()
    assert pushed and all(f.size == (SIZE, SIZE) for f in pushed)
    assert running is True
    assert s.status()["running"] is False


def test_stream_reports_no_frames_timeout():
    s = camera.CameraStream(ip="x", source=[], player=lambda f: None, first_frame_timeout=0.05)
    s.start()
    deadline = time.time() + 3
    while s.status()["error"] is None and time.time() < deadline:
        time.sleep(0.02)
    err = s.status()["error"]
    s.stop()
    assert err and "no camera frames" in err


def test_stream_reports_capture_error():
    def bad():
        raise RuntimeError("boom")
        yield  # pragma: no cover
    s = camera.CameraStream(ip="x", source=bad(), player=lambda f: None, first_frame_timeout=5)
    s.start()
    deadline = time.time() + 3
    while s.status()["error"] is None and time.time() < deadline:
        time.sleep(0.02)
    err = s.status()["error"]
    s.stop()
    assert err and "boom" in err
