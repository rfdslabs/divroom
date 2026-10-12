"""Passively observe and analyze a Pixoo's network behaviour.

What you can actually see depends on where you capture:

- On a normal switched LAN a host only receives broadcast (ARP, DHCP),
  multicast it has joined (mDNS 5353, SSDP 1900), and its *own* unicast
  traffic. The device's unicast to the Divoom cloud is NOT visible here.
- To observe the device phoning home, capture at the gateway/router you
  control (or a span/mirror port) and feed the .pcap to `analyze_pcap`.

This module ships NO MITM: it never spoofs ARP, never injects, never
decrypts TLS. It reads what the network already hands you. The analyzers
below work on plain packet dicts and need no scapy or network, so the
logic is unit-tested without hardware; scapy is a lazily-imported optional
dependency used only by `parse_pcap` / `live_capture`.

Use only on networks and devices you are authorized to test.
"""
import ipaddress
import re

# Packet-dict shape the analyzers expect (parse_pcap produces these):
#   {"src","dst","proto","sport","dport","dns_qname","tls_sni","payload"}

# Keys / patterns that betray a location in a cleartext payload.
_GEO_RE = re.compile(
    rb'"?(latitude|longitude|lat|lon|lng|gps|geohash|coordinate)"?\s*[:=]\s*'
    rb'"?(-?\d{1,3}\.\d+)',
    re.IGNORECASE,
)


def is_private(ip):
    """True for RFC1918 / loopback / link-local — i.e. not a public endpoint."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a.is_link_local or a.is_multicast


def dns_queries(packets):
    """Sorted unique DNS names the capture asked for."""
    return sorted({p["dns_qname"] for p in packets if p.get("dns_qname")})


def tls_sni_names(packets):
    """Sorted unique TLS SNI hostnames (plaintext in the ClientHello)."""
    return sorted({p["tls_sni"] for p in packets if p.get("tls_sni")})


def remote_endpoints(packets, device_ip):
    """Public (dst, dport) the device talks to, with a flow count, busiest first."""
    counts = {}
    for p in packets:
        if p.get("src") != device_ip:
            continue
        dst = p.get("dst", "")
        if not dst or is_private(dst):
            continue
        key = (dst, p.get("dport"))
        counts[key] = counts.get(key, 0) + 1
    out = [{"dst": d, "dport": port, "count": n}
           for (d, port), n in counts.items()]
    out.sort(key=lambda e: (-e["count"], e["dst"], e["dport"] or 0))
    return out


def _as_text(payload):
    if isinstance(payload, str):
        return payload
    if not payload:
        return ""
    # Only treat it as text if it is mostly printable — skips TLS records etc.
    printable = sum(1 for b in payload if 9 <= b <= 13 or 32 <= b <= 126)
    if printable < len(payload) * 0.8:
        return ""
    return payload.decode("latin-1", "replace")


def scan_for_geo(packets):
    """Find cleartext latitude/longitude-looking fields in packet payloads."""
    hits = []
    for p in packets:
        text = _as_text(p.get("payload"))
        if not text:
            continue
        for field, value in _GEO_RE.findall(text.encode("latin-1", "replace")):
            hits.append({
                "src": p.get("src"), "dst": p.get("dst"), "dport": p.get("dport"),
                "field": field.decode(), "value": value.decode(),
            })
    return hits


def analyze(packets, device_ip):
    """Roll the analyzers up into one report dict."""
    return {
        "device_ip": device_ip,
        "packets": len(packets),
        "dns_queries": dns_queries(packets),
        "tls_sni": tls_sni_names(packets),
        "endpoints": remote_endpoints(packets, device_ip),
        "geo_hits": scan_for_geo(packets),
    }


# ---------------------------------------------------------------------------
# scapy-backed entry points (optional dependency; imported lazily so the core
# control toolkit and the unit tests never require scapy).
# ---------------------------------------------------------------------------

def _require_scapy():
    try:
        from scapy.all import DNS, DNSQR, IP, TCP, UDP, rdpcap, sniff  # noqa: F401
        import scapy.all as s
        return s
    except Exception as e:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "passive capture needs scapy: pip install -r requirements-capture.txt"
        ) from e


def _tls_sni(raw):  # pragma: no cover - parsing exercised via live/pcap paths
    """Best-effort SNI extraction from a TLS ClientHello payload (plaintext)."""
    i = raw.find(b"\x00\x00")  # server_name extension marker is fuzzy; keep simple
    m = re.search(rb"[\x20-\x7e]{4,253}\.[a-z]{2,}", raw)
    return m.group().decode() if m and raw[:1] == b"\x16" else None


def _to_dict(pkt, s):  # pragma: no cover - requires scapy packets
    if s.IP not in pkt:
        return None
    ip = pkt[s.IP]
    d = {"src": ip.src, "dst": ip.dst, "proto": "IP", "sport": None,
         "dport": None, "dns_qname": None, "tls_sni": None, "payload": b""}
    if s.UDP in pkt:
        d["proto"], d["sport"], d["dport"] = "UDP", int(pkt[s.UDP].sport), int(pkt[s.UDP].dport)
    elif s.TCP in pkt:
        d["proto"], d["sport"], d["dport"] = "TCP", int(pkt[s.TCP].sport), int(pkt[s.TCP].dport)
    if pkt.haslayer(s.DNSQR):
        try:
            d["dns_qname"] = pkt[s.DNSQR].qname.decode().rstrip(".")
        except Exception:
            pass
    payload = bytes(pkt[s.TCP].payload) if s.TCP in pkt else (
        bytes(pkt[s.UDP].payload) if s.UDP in pkt else b"")
    d["payload"] = payload
    if d["dport"] == 443 and payload[:1] == b"\x16":
        d["tls_sni"] = _tls_sni(payload)
    return d


def parse_pcap(path):  # pragma: no cover - requires scapy + a file
    """Read a .pcap into analyzer-ready packet dicts."""
    s = _require_scapy()
    return [d for d in (_to_dict(p, s) for p in s.rdpcap(path)) if d]


def analyze_pcap(path, device_ip):  # pragma: no cover
    return analyze(parse_pcap(path), device_ip)


def live_capture(iface=None, seconds=60, bpf=None):  # pragma: no cover
    """Passively sniff `seconds` of traffic. On a switched LAN this is mostly
    broadcast/multicast + this host's own traffic — see the module docstring."""
    s = _require_scapy()
    pkts = s.sniff(iface=iface, timeout=seconds, filter=bpf, store=True)
    return [d for d in (_to_dict(p, s) for p in pkts) if d]
