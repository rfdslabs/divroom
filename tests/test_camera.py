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


def test_ffmpeg_cmd_auto_omits_mode():
    cmd = camera._ffmpeg_cmd(0, None, None)
    assert "-framerate" not in cmd and "-video_size" not in cmd
    assert cmd[cmd.index("-i") + 1] == "0"


def test_ffmpeg_cmd_includes_mode_when_given():
    cmd = camera._ffmpeg_cmd(1, 30, "640x480")
    assert cmd[cmd.index("-framerate") + 1] == "30"
    assert cmd[cmd.index("-video_size") + 1] == "640x480"


MODES_TEXT = """
[in#0 @ 0x1] Selected framerate (99999.00) is not supported by the device.
[in#0 @ 0x1] Supported modes:
[in#0 @ 0x1]   640x480@[15.000000 30.000000]fps
[in#0 @ 0x1]   1280x720@[15.000000 30.000000]fps
[in#0 @ 0x1]   1760x1328@[15.000000 30.000000]fps
"""


def test_parse_modes():
    modes = camera._parse_modes(MODES_TEXT)
    assert (640, 480, 15.0, 30.0) in modes
    assert len(modes) == 3


def test_pick_mode_smallest_at_30():
    size, fps = camera.pick_mode(camera._parse_modes(MODES_TEXT))
    assert size == "640x480" and fps == 30


def test_pick_mode_uses_max_when_30_out_of_range():
    assert camera.pick_mode([(1920, 1440, 1.0, 25.0)]) == ("1920x1440", 25)


def test_pick_mode_empty_is_none():
    assert camera.pick_mode([]) is None


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
