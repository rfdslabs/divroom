#!/usr/bin/env python3
"""Control a Divoom Pixoo 64 over its local HTTP API (POST http://<ip>/post)."""
import argparse
import base64
import os
import sys

import requests
from PIL import Image, ImageSequence

SIZE = 64
MAX_FRAMES = 60  # the device gets unstable with long animations
CHANNELS = {"faces": 0, "cloud": 1, "visualizer": 2, "custom": 3}


def discover():
    r = requests.post("https://app.divoom-gz.com/Device/ReturnSameLANDevice", timeout=8)
    devices = r.json().get("DeviceList") or []
    if not devices:
        sys.exit("No Pixoo found on this network; pass --ip")
    return devices[0]["DevicePrivateIP"]


class Pixoo:
    def __init__(self, ip):
        self.url = f"http://{ip}/post"

    def cmd(self, command, **params):
        r = requests.post(self.url, json={"Command": command, **params}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("error_code", 0) != 0:
            raise RuntimeError(f"{command} failed: {data}")
        return data

    def send_frames(self, frames, speed_ms=100):
        # Resetting the ID before each push keeps the device from freezing after many uploads.
        self.cmd("Draw/ResetHttpGifId")
        pic_id = self.cmd("Draw/GetHttpGifId")["PicId"]
        for offset, frame in enumerate(frames):
            self.cmd(
                "Draw/SendHttpGif",
                PicNum=len(frames),
                PicWidth=SIZE,
                PicOffset=offset,
                PicID=pic_id,
                PicSpeed=speed_ms,
                PicData=base64.b64encode(frame.tobytes()).decode(),
            )

    def text(self, msg, color="#FFFFFF", y=28, speed=50, font=2, text_id=1):
        self.cmd(
            "Draw/SendHttpText",
            TextId=text_id, x=0, y=y, dir=0, font=font, TextWidth=SIZE,
            speed=speed, TextString=msg, color=color, align=1,
        )


def to_frame(img):
    img = img.convert("RGB")
    # Nearest-neighbour keeps pixel art crisp; letterbox non-square images on black.
    img.thumbnail((SIZE, SIZE), Image.NEAREST if max(img.size) <= SIZE * 2 else Image.LANCZOS)
    canvas = Image.new("RGB", (SIZE, SIZE))
    canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2))
    return canvas


def load_frames(path):
    img = Image.open(path)
    frames, durations = [], []
    for f in ImageSequence.Iterator(img):
        frames.append(to_frame(f.copy()))
        durations.append(f.info.get("duration", 100))
        if len(frames) >= MAX_FRAMES:
            break
    speed = max(20, int(sum(durations) / len(durations)))
    return frames, speed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ip", default=os.environ.get("PIXOO_IP"), help="device IP (auto-discovered if omitted)")
    sub = p.add_subparsers(dest="action", required=True)

    s = sub.add_parser("image", help="show a PNG/JPG or animated GIF")
    s.add_argument("path")
    s.add_argument("--speed", type=int, help="ms per frame (defaults to the GIF's timing)")

    s = sub.add_parser("color", help="fill the screen with one color")
    s.add_argument("hex", help="e.g. ff0080")

    s = sub.add_parser("text", help="overlay scrolling text on the current image")
    s.add_argument("msg")
    s.add_argument("--color", default="#FFFFFF")
    s.add_argument("--y", type=int, default=28)
    s.add_argument("--background", help="hex color to draw behind the text first")

    s = sub.add_parser("brightness", help="0-100")
    s.add_argument("level", type=int)

    s = sub.add_parser("channel", help="switch back to a built-in channel")
    s.add_argument("name", choices=CHANNELS)

    s = sub.add_parser("screen", help="turn the display on/off")
    s.add_argument("state", choices=["on", "off"])

    sub.add_parser("info", help="print device settings")

    args = p.parse_args()
    dev = Pixoo(args.ip or discover())

    if args.action == "image":
        frames, speed = load_frames(args.path)
        dev.send_frames(frames, args.speed or speed)
        print(f"sent {len(frames)} frame(s)")
    elif args.action == "color":
        dev.send_frames([Image.new("RGB", (SIZE, SIZE), "#" + args.hex.lstrip("#"))])
    elif args.action == "text":
        if args.background:
            dev.send_frames([Image.new("RGB", (SIZE, SIZE), "#" + args.background.lstrip("#"))])
        dev.cmd("Draw/ClearHttpText")
        dev.text(args.msg, color=args.color, y=args.y)
    elif args.action == "brightness":
        dev.cmd("Channel/SetBrightness", Brightness=max(0, min(100, args.level)))
    elif args.action == "channel":
        dev.cmd("Channel/SetIndex", SelectIndex=CHANNELS[args.name])
    elif args.action == "screen":
        dev.cmd("Channel/OnOffScreen", OnOff=1 if args.state == "on" else 0)
    elif args.action == "info":
        for k, v in dev.cmd("Channel/GetAllConf").items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
