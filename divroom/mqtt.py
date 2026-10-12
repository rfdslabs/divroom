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
        rem, j = _remaining_length(payload, i + 1)
        if rem is None or j + rem > n:
            break
        frame = payload[j:j + rem]
        i = j + rem
        if (b & 0xF0) != 0x30:  # not a PUBLISH — skip this frame, keep scanning
            continue
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
