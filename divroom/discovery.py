"""Find Pixoo devices: Divoom's cloud lookup, with a LAN probe fallback.

The cloud `ReturnSameLANDevice` only lists devices that recently checked in from
the caller's public IP, so it often returns []. The LAN fallback scans the ARP
table and confirms a candidate by hitting the device's own HTTP API.
"""
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
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


def _arp_candidates(arp_output):
    """IPv4 unicast addresses from `arp -a` output (drops multicast/broadcast)."""
    out = []
    for ip in re.findall(r"\((\d+\.\d+\.\d+\.\d+)\)", arp_output):
        first, last = int(ip.split(".")[0]), int(ip.split(".")[-1])
        if first >= 224 or last in (0, 255):  # multicast / network / broadcast
            continue
        out.append(ip)
    return out


def probe(ip, mac="", timeout=0.6):
    """Confirm a Pixoo at ip by calling its local API. Returns a Device or None."""
    try:
        r = requests.post(f"http://{ip}/post", json={"Command": "Channel/GetAllConf"},
                          timeout=timeout)
        data = r.json()
    except Exception:
        return None
    if data.get("error_code", 1) != 0:
        return None
    return Device(name="Pixoo64", ip=ip, mac=mac, device_id=0, hardware=0)


def discover_lan():
    try:
        # -n: numeric, skip per-entry reverse DNS (plain `arp -a` can hang past the timeout).
        arp = subprocess.run(["arp", "-an"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        arp = ""
    macs = dict(re.findall(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+)", arp))
    cands = _arp_candidates(arp)
    env_ip = os.environ.get("PIXOO_IP")
    if env_ip and env_ip not in cands:
        cands.insert(0, env_ip)
    found = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for dev in ex.map(lambda ip: probe(ip, mac=macs.get(ip, "").replace(":", "")), cands):
            if dev:
                found.append(dev)
    return found


def discover(timeout=8):
    try:
        r = requests.post(LAN_LOOKUP, timeout=timeout)
        devices = parse_lan_devices(r.json())
    except Exception:
        devices = []
    if devices:
        return devices
    return discover_lan()  # cloud came back empty/unreachable
