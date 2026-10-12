#!/usr/bin/env python3
"""CLI for the Divoom Pixoo 64, thin wrapper over divroom.control."""
import argparse
import os
import sys

from divroom.control import Pixoo, PixooError, CHANNELS
from divroom.discovery import discover
from divroom import animate, art


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
    s.add_argument("--fps", type=int, default=12)
    sub.add_parser("info")

    args = p.parse_args()
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
