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
