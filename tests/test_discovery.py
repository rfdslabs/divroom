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
