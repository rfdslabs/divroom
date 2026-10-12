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


def test_arp_candidates_parses_ips():
    from divroom.discovery import _arp_candidates
    arp = (
        "ip-192-168-4-1.us-east-2.compute.internal (192.168.4.1) at 94:cd:fd:30:c2:52 on en0 ifscope [ethernet]\n"
        "? (192.168.4.20) at 94:b5:55:76:e7:64 on en0 ifscope [ethernet]\n"
        "? (224.0.0.251) at 1:0:5e:0:0:fb on en0 ifscope permanent [ethernet]\n"
    )
    cands = _arp_candidates(arp)
    assert "192.168.4.20" in cands
    assert "192.168.4.1" in cands
    assert "224.0.0.251" not in cands  # multicast excluded


def test_probe_confirms_pixoo(monkeypatch):
    from divroom import discovery
    class R:
        def json(self): return {"error_code": 0, "Brightness": 60}
    monkeypatch.setattr(discovery.requests, "post", lambda *a, **k: R())
    dev = discovery.probe("192.168.4.20", mac="94b55576e764")
    assert dev is not None
    assert dev.ip == "192.168.4.20"
    assert dev.mac == "94b55576e764"


def test_probe_rejects_non_pixoo(monkeypatch):
    from divroom import discovery
    def boom(*a, **k): raise OSError("refused")
    monkeypatch.setattr(discovery.requests, "post", boom)
    assert discovery.probe("192.168.4.99") is None
