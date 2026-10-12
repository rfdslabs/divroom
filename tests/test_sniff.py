"""Tests for the passive observation / analysis helpers.

The analyzers work on plain packet dicts, so none of this needs scapy or a
network — scapy is only touched by the live/pcap entry points, which are not
exercised here.
"""
from divroom import sniff


def pkt(src, dst, proto="TCP", sport=12345, dport=443,
        dns_qname=None, tls_sni=None, payload=b""):
    return {"src": src, "dst": dst, "proto": proto, "sport": sport,
            "dport": dport, "dns_qname": dns_qname, "tls_sni": tls_sni,
            "payload": payload}


DEVICE = "192.168.4.20"


def test_is_private_classifies_rfc1918_and_public():
    assert sniff.is_private("192.168.4.20")
    assert sniff.is_private("10.1.2.3")
    assert sniff.is_private("172.16.0.1")
    assert not sniff.is_private("8.8.8.8")
    assert not sniff.is_private("47.91.0.1")


def test_dns_queries_unique_and_sorted():
    pkts = [
        pkt(DEVICE, "192.168.4.1", proto="UDP", dport=53, dns_qname="app.divoom-gz.com"),
        pkt(DEVICE, "192.168.4.1", proto="UDP", dport=53, dns_qname="app.divoom-gz.com"),
        pkt(DEVICE, "192.168.4.1", proto="UDP", dport=53, dns_qname="f.divoom-gz.com"),
    ]
    assert sniff.dns_queries(pkts) == ["app.divoom-gz.com", "f.divoom-gz.com"]


def test_tls_sni_names():
    pkts = [pkt(DEVICE, "47.91.0.1", tls_sni="app.divoom-gz.com"),
            pkt(DEVICE, "47.91.0.1")]
    assert sniff.tls_sni_names(pkts) == ["app.divoom-gz.com"]


def test_remote_endpoints_only_device_to_public():
    pkts = [
        pkt(DEVICE, "47.91.0.1", dport=443),        # device -> cloud (counted)
        pkt(DEVICE, "47.91.0.1", dport=443),        # same endpoint, +1
        pkt(DEVICE, "192.168.4.1", dport=53),       # LAN (dropped)
        pkt("192.168.4.33", "47.91.0.1", dport=443),  # other host (dropped)
    ]
    eps = sniff.remote_endpoints(pkts, DEVICE)
    assert eps == [{"dst": "47.91.0.1", "dport": 443, "count": 2}]


def test_scan_for_geo_finds_plaintext_coordinates():
    body = b'POST /telemetry {"Latitude":37.7749,"Longitude":-122.4194}'
    pkts = [
        pkt(DEVICE, "47.91.0.1", dport=80, payload=body),
        pkt(DEVICE, "47.91.0.1", dport=443, payload=b"\x16\x03\x01encrypted"),
    ]
    hits = sniff.scan_for_geo(pkts)
    fields = {h["field"].lower() for h in hits}
    assert "latitude" in fields and "longitude" in fields
    assert all(h["dst"] == "47.91.0.1" for h in hits)


def test_scan_for_geo_ignores_encrypted_binary():
    pkts = [pkt(DEVICE, "47.91.0.1", dport=443, payload=bytes(range(256)))]
    assert sniff.scan_for_geo(pkts) == []


def test_analyze_builds_report():
    pkts = [
        pkt(DEVICE, "192.168.4.1", proto="UDP", dport=53, dns_qname="app.divoom-gz.com"),
        pkt(DEVICE, "47.91.0.1", dport=443, tls_sni="app.divoom-gz.com"),
        pkt(DEVICE, "47.91.0.1", dport=80, payload=b'{"lat":1.5,"lon":2.5}'),
    ]
    rep = sniff.analyze(pkts, DEVICE)
    assert rep["device_ip"] == DEVICE
    assert "app.divoom-gz.com" in rep["dns_queries"]
    assert "app.divoom-gz.com" in rep["tls_sni"]
    assert rep["endpoints"] and rep["endpoints"][0]["dst"] == "47.91.0.1"
    assert rep["geo_hits"]              # cleartext lat/lon caught
    assert rep["packets"] == 3
