from divroom.mqtt import decode_mqtt, decode_pcap, MqttEvent

FIXTURE = "tests/fixtures/pixoo_ota.pcap"


def _publish_frame(topic: bytes, body: bytes) -> bytes:
    var = len(topic).to_bytes(2, "big") + topic + body
    return bytes([0x30]) + bytes([len(var)]) + var


def test_decode_single_publish():
    frame = _publish_frame(b"divoom/2/300046041/get",
                           b'{"Command":"Sys/SetConf","Latitude":28.1}')
    events = decode_mqtt(frame)
    assert len(events) == 1
    e = events[0]
    assert e.topic == "divoom/2/300046041/get"
    assert e.direction == "cloud->device"
    assert e.command == "Sys/SetConf"
    assert e.json["Latitude"] == 28.1


def test_decode_ignores_garbage():
    assert decode_mqtt(b"\x00\x01\x02not-a-frame") == []
    assert decode_mqtt(b"") == []


def test_decode_truncated_frame_does_not_raise():
    frame = _publish_frame(b"divoom/2/1/state", b'{"Command":"Device/Hearbeat"}')
    decode_mqtt(frame[:8])


def test_decode_pcap_recovers_known_commands():
    events = decode_pcap(FIXTURE)
    commands = {e.command for e in events}
    assert "Sys/SetConf" in commands
    assert "Device/Hearbeat" in commands
    topics = {e.topic for e in events}
    assert "divoom/2/300046041/state" in topics
    assert "divoom/2/300046041/get" in topics
    setconf = next(e for e in events if e.command == "Sys/SetConf")
    assert setconf.json["Latitude"] == 28.1
    assert setconf.json["Longitude"] == -82.7
