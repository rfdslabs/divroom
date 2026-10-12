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


@pytest.fixture
def no_device(monkeypatch):
    # Control routes shouldn't actually touch the network in tests.
    monkeypatch.setattr("divroom.control.Pixoo.color", lambda self, hex: None)


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


def test_animate_pushes_frames(client, monkeypatch):
    sent = {}
    def fake_send(self, frames, speed_ms=100):
        sent["n"] = len(frames); sent["speed"] = speed_ms
    monkeypatch.setattr("divroom.control.Pixoo.send_frames", fake_send)
    r = client.post("/api/animate/rainbow",
                    json={"ip": "192.168.4.20", "frames": 6, "speed": 80})
    assert r.status_code == 200
    assert sent["n"] == 6 and sent["speed"] == 80


def test_animate_unknown_returns_404(client, monkeypatch):
    monkeypatch.setattr("divroom.control.Pixoo.send_frames", lambda self, frames, speed_ms=100: None)
    r = client.post("/api/animate/nope", json={"ip": "192.168.4.20"})
    assert r.status_code == 404


def test_animate_device_error_returns_502(client, monkeypatch):
    from divroom.control import PixooError
    def boom(self, frames, speed_ms=100): raise PixooError("unreachable")
    monkeypatch.setattr("divroom.control.Pixoo.send_frames", boom)
    r = client.post("/api/animate/plasma", json={"ip": "192.168.4.20", "frames": 4})
    assert r.status_code == 502


def test_art_pushes_frames(client, monkeypatch):
    from PIL import Image
    monkeypatch.setattr("divroom.art.fetch_piece",
                        lambda *a, **k: Image.new("RGB", (64, 256)))
    sent = {}
    monkeypatch.setattr("divroom.control.Pixoo.send_frames",
                        lambda self, frames, speed_ms=100: sent.update(n=len(frames), speed=speed_ms))
    r = client.post("/api/art", json={"ip": "192.168.4.20", "pack": "fire-46",
                                      "file": "AK-KING.ANS", "frames": 10, "speed": 60})
    assert r.status_code == 200
    assert sent["n"] == 10 and sent["speed"] == 60


def test_art_fetch_failure_returns_502(client, monkeypatch):
    import requests
    def boom(*a, **k): raise requests.RequestException("not found")
    monkeypatch.setattr("divroom.art.fetch_piece", boom)
    r = client.post("/api/art", json={"ip": "192.168.4.20", "pack": "x", "file": "y.ANS"})
    assert r.status_code == 502


def test_control_image_rejects_non_image(client):
    r = client.post("/api/control/image",
                    data={"ip": "192.168.4.20"},
                    files={"file": ("x.txt", io.BytesIO(b"not an image"), "text/plain")})
    assert r.status_code == 400


def test_rejects_foreign_origin(client, no_device):
    r = client.post("/api/control/color", json={"ip": "192.168.4.20", "hex": "ff0000"},
                    headers={"origin": "http://evil.example"})
    assert r.status_code == 403


def test_allows_localhost_origin(client, no_device):
    r = client.post("/api/control/color", json={"ip": "192.168.4.20", "hex": "ff0000"},
                    headers={"origin": "http://127.0.0.1:8000"})
    assert r.status_code == 200


def test_allows_no_origin(client, no_device):
    r = client.post("/api/control/color", json={"ip": "192.168.4.20", "hex": "ff0000"})
    assert r.status_code == 200
