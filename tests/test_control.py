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


def test_push_still_sends_one_sendhttpgif(monkeypatch):
    from PIL import Image
    sent = []
    monkeypatch.setattr("divroom.control.requests.post",
                        lambda url, json=None, timeout=None: (sent.append(json),
                                                              FakeResp({"error_code": 0}))[1])
    Pixoo("1.2.3.4").push_still(Image.new("RGB", (64, 64), (1, 2, 3)), pic_id=5)
    assert len(sent) == 1                       # a single request, not 3
    j = sent[0]
    assert j["Command"] == "Draw/SendHttpGif"
    assert j["PicNum"] == 1 and j["PicID"] == 5 and j["PicOffset"] == 0
    assert j["PicWidth"] == 64 and "PicData" in j


def test_channels_map():
    assert CHANNELS == {"faces": 0, "cloud": 1, "visualizer": 2, "custom": 3}


@pytest.mark.skipif(os.environ.get("PIXOO_LIVE") != "1",
                    reason="set PIXOO_LIVE=1 and PIXOO_IP to hit the real device")
def test_live_color_roundtrip():
    dev = Pixoo(os.environ["PIXOO_IP"])
    dev.color("00ff00")
