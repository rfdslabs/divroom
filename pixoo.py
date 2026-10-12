#!/usr/bin/env python3
"""CLI for the Divoom Pixoo 64, thin wrapper over divroom.control."""
import argparse
import os
import sys

from divroom.control import Pixoo, PixooError, CHANNELS
from divroom.discovery import discover
from divroom import animate, art, sniff


def _pick_ip(explicit):
    if explicit:
        return explicit
    env = os.environ.get("PIXOO_IP")
    if env:
        return env
    devices = discover()
    if not devices:
        sys.exit("No Pixoo found on this network; pass --ip")
    return devices[0].ip


def _print_report(rep):
    print(f"device: {rep['device_ip']}   packets: {rep['packets']}")
    print("\nDNS queries:")
    for q in rep["dns_queries"] or ["  (none seen)"]:
        print(f"  {q}")
    print("\nTLS SNI:")
    for q in rep["tls_sni"] or ["  (none seen)"]:
        print(f"  {q}")
    print("\nRemote endpoints (device → public):")
    for e in rep["endpoints"] or []:
        print(f"  {e['dst']}:{e['dport']}  ({e['count']} flows)")
    if not rep["endpoints"]:
        print("  (none — capture at a gateway to see unicast to the cloud)")
    print("\nCleartext geolocation hits:")
    if rep["geo_hits"]:
        for h in rep["geo_hits"]:
            print(f"  {h['src']} → {h['dst']}:{h['dport']}  {h['field']}={h['value']}")
    else:
        print("  (none in cleartext — telemetry to the cloud is likely TLS-encrypted)")


def _run_sniff(args):
    device_ip = args.device_ip or args.ip or os.environ.get("PIXOO_IP") or ""
    try:
        if args.mode == "analyze":
            if not args.pcap:
                sys.exit("usage: pixoo.py sniff analyze <file.pcap> [--device-ip IP]")
            rep = sniff.analyze_pcap(args.pcap, device_ip)
        else:
            print(f"passively listening on {args.iface or 'default iface'} "
                  f"for {args.seconds}s (Ctrl-C to stop early)...")
            print("note: on a switched LAN this sees broadcast/multicast + this "
                  "host's own traffic; capture at your gateway to observe the "
                  "device's unicast to the cloud.")
            pkts = sniff.live_capture(iface=args.iface, seconds=args.seconds, bpf=args.bpf)
            rep = sniff.analyze(pkts, device_ip)
    except RuntimeError as e:          # scapy missing
        sys.exit(str(e))
    except (FileNotFoundError, IsADirectoryError, PermissionError) as e:
        sys.exit(f"cannot read pcap: {e}")
    except KeyboardInterrupt:
        sys.exit("\nstopped")
    _print_report(rep)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ip", default=None, help="device IP (auto-discovered if omitted)")
    sub = p.add_subparsers(dest="action", required=True)

    s = sub.add_parser("image"); s.add_argument("path")
    s = sub.add_parser("color"); s.add_argument("hex")
    s = sub.add_parser("text"); s.add_argument("msg")
    s.add_argument("--color", default="#FFFFFF"); s.add_argument("--y", type=int, default=28)
    s.add_argument("--background")
    s = sub.add_parser("brightness"); s.add_argument("level", type=int)
    s = sub.add_parser("channel"); s.add_argument("name", choices=CHANNELS)
    s = sub.add_parser("screen"); s.add_argument("state", choices=["on", "off"])
    s = sub.add_parser("animate"); s.add_argument("name", choices=animate.ANIMATIONS)
    s.add_argument("--speed", type=int, default=100); s.add_argument("--frames", type=int, default=30)
    s.add_argument("--color", default="#ffffff"); s.add_argument("--color2", default="#00e0ff")
    s = sub.add_parser("gradient"); s.add_argument("a"); s.add_argument("b")
    s.add_argument("--angle", type=int, default=0)
    s = sub.add_parser("art"); s.add_argument("pack"); s.add_argument("file")
    s.add_argument("--speed", type=int, default=100); s.add_argument("--frames", type=int, default=60)
    s = sub.add_parser("slideshow"); s.add_argument("--year", type=int, default=2024)
    s.add_argument("--hold", type=int, default=30); s.add_argument("--speed", type=int, default=60)
    s = sub.add_parser("camera"); s.add_argument("--index", type=int, default=0)
    s.add_argument("--fps", type=int, default=None, help="force capture fps (default: camera's native mode)")
    s = sub.add_parser("sniff", help="passively observe the device's traffic (authorized networks only)")
    s.add_argument("mode", choices=["live", "analyze"])
    s.add_argument("pcap", nargs="?", help="pcap file for 'analyze' (capture it at a gateway you control)")
    s.add_argument("--device-ip", default=None, help="the Pixoo's IP (defaults to --ip / PIXOO_IP)")
    s.add_argument("--iface", default=None); s.add_argument("--seconds", type=int, default=60)
    s.add_argument("--bpf", default=None, help="optional BPF capture filter")
    sub.add_parser("info")

    args = p.parse_args()

    if args.action == "sniff":
        _run_sniff(args)
        return

    dev = Pixoo(_pick_ip(args.ip))
    try:
        if args.action == "image":
            print(f"sent {dev.image(args.path)} frame(s)")
        elif args.action == "color":
            dev.color(args.hex)
        elif args.action == "text":
            if args.background:
                dev.color(args.background.lstrip("#"))
            dev.text(args.msg, color=args.color, y=args.y)
        elif args.action == "brightness":
            dev.brightness(args.level)
        elif args.action == "channel":
            dev.channel(args.name)
        elif args.action == "screen":
            dev.screen(args.state == "on")
        elif args.action == "animate":
            frames = animate.build(args.name, frames=args.frames,
                                   color=args.color, a=args.color, b=args.color2)
            dev.send_frames(frames, speed_ms=args.speed)
            print(f"played {args.name} ({len(frames)} frames)")
        elif args.action == "gradient":
            dev.send_frames(animate.build("gradient", a=args.a, b=args.b, angle=args.angle))
            print("sent gradient")
        elif args.action == "art":
            frames = art.build(args.pack, args.file, frames=args.frames)
            dev.send_frames(frames, speed_ms=args.speed)
            print(f"scrolled {args.pack}/{args.file} ({len(frames)} frames)")
        elif args.action == "slideshow":
            import time
            from divroom.slideshow import Slideshow
            show = Slideshow(ip=dev.ip, year=args.year, speed=args.speed, hold=args.hold).start()
            print(f"slideshow: random pieces from {args.year}, {args.hold}s each, "
                  f"prefetching 10. Ctrl-C to stop.")
            last = None
            try:
                while True:
                    st = show.status()
                    if st["current"] and st["current"] != last:
                        last = st["current"]
                        print(f"▶ {last['pack']}/{last['file']}  ({st['queued']} ready)")
                    if st["error"]:
                        print("note:", st["error"])
                    time.sleep(1)
            except KeyboardInterrupt:
                show.stop(); print("\nstopped")
        elif args.action == "camera":
            import time
            from divroom.camera import CameraStream, list_devices
            cams = list_devices()
            print("cameras:", ", ".join(f"[{d['index']}] {d['name']}" for d in cams) or "none found")
            cam = CameraStream(ip=dev.ip, index=args.index, fps=args.fps).start()
            print(f"streaming camera {args.index} → {dev.ip}. Ctrl-C to stop.")
            try:
                while True:
                    st = cam.status()
                    if st["error"]:
                        print("\n" + st["error"]); break
                    print(f"  {st['frames_sent']} frames · {st['fps']} fps   ", end="\r", flush=True)
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                cam.stop(); print("\nstopped")
        elif args.action == "info":
            for k, v in dev.cmd("Channel/GetAllConf").items():
                print(f"{k}: {v}")
    except PixooError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
