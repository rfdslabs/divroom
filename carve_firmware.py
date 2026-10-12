#!/usr/bin/env python3
"""Carve HTTP responses out of a pcap and flag likely firmware images.

Reassembles TCP streams per connection, splits HTTP request/response, saves every
response body, and highlights ones that look like firmware (by URL, size, or the
ESP32 image magic byte 0xE9).
"""
import argparse
import os
import re
from collections import defaultdict

from scapy.all import IP, TCP, Raw, rdpcap


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pcap")
    p.add_argument("--out", default="carved")
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)

    # Reassemble payload bytes per (src,sport,dst,dport) in capture order.
    streams = defaultdict(bytearray)
    for pkt in rdpcap(args.pcap):
        if TCP in pkt and Raw in pkt:
            k = (pkt[IP].src, pkt[TCP].sport, pkt[IP].dst, pkt[TCP].dport)
            streams[k] += bytes(pkt[Raw].load)

    # Collect requested URLs per client-side tuple so we can name the responses.
    urls = {}
    for (src, sport, dst, dport), data in streams.items():
        m = re.match(rb"(GET|POST) (\S+) HTTP/1", bytes(data))
        if m:
            host = b""
            h = re.search(rb"[Hh]ost:\s*(\S+)", bytes(data))
            if h:
                host = h.group(1)
            urls[(dst, dport, src, sport)] = (host + m.group(2)).decode("latin1")

    n = 0
    for key, data in streams.items():
        data = bytes(data)
        if not data.startswith(b"HTTP/1"):
            continue
        hdr_end = data.find(b"\r\n\r\n")
        if hdr_end < 0:
            continue
        body = data[hdr_end + 4:]
        if not body:
            continue
        url = urls.get(key, "unknown")
        fname = re.sub(r"[^A-Za-z0-9._-]", "_", url)[-80:] or f"resp{n}"
        path = os.path.join(args.out, f"{n:02d}_{fname}.bin")
        with open(path, "wb") as f:
            f.write(body)
        magic = body[:1]
        firmware = (
            body[:1] == b"\xe9"                      # ESP32/ESP8266 image magic
            or re.search(r"\.(bin|img|ota|fw)", url, re.I)
            or len(body) > 200_000
        )
        tag = "  <-- LIKELY FIRMWARE" if firmware else ""
        print(f"{path}  {len(body):>9} bytes  first=0x{magic.hex()}  url={url}{tag}")
        n += 1

    if n == 0:
        print("No HTTP response bodies found. The download may be HTTPS (encrypted) "
              "or the app pushed it to the device over the LAN instead of the device "
              "fetching it. Check the pcap with: tcpdump -r %s -nn" % args.pcap)


if __name__ == "__main__":
    main()
