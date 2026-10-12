#!/usr/bin/env python3
"""CLI for the Divoom Pixoo 64, thin wrapper over divroom.control."""
import argparse
import os
import sys

from divroom.control import Pixoo, PixooError, CHANNELS
from divroom.discovery import discover


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
        elif args.action == "info":
            for k, v in dev.cmd("Channel/GetAllConf").items():
                print(f"{k}: {v}")
    except PixooError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
