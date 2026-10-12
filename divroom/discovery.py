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
