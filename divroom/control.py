"""Drive a Divoom Pixoo 64 over its local HTTP API (POST http://<ip>/post)."""
import base64

import requests
from PIL import Image, ImageSequence

SIZE = 64
MAX_FRAMES = 60
CHANNELS = {"faces": 0, "cloud": 1, "visualizer": 2, "custom": 3}


class PixooError(Exception):
    pass


def _to_frame(img):
    img = img.convert("RGB")
    resample = Image.NEAREST if max(img.size) <= SIZE * 2 else Image.LANCZOS
    img.thumbnail((SIZE, SIZE), resample)
    canvas = Image.new("RGB", (SIZE, SIZE))
    canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2))
    return canvas


class Pixoo:
    def __init__(self, ip):
        self.ip = ip
        self.url = f"http://{ip}/post"

    def cmd(self, command, **params):
        try:
            r = requests.post(self.url, json={"Command": command, **params}, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise PixooError(f"{command}: transport error: {e}") from e
        if data.get("error_code", 0) != 0:
            raise PixooError(f"{command} failed: {data}")
        return data

    def send_frames(self, frames, speed_ms=100):
        self.cmd("Draw/ResetHttpGifId")
        pic_id = self.cmd("Draw/GetHttpGifId")["PicId"]
        for offset, frame in enumerate(frames):
            self.cmd("Draw/SendHttpGif", PicNum=len(frames), PicWidth=SIZE,
                     PicOffset=offset, PicID=pic_id, PicSpeed=speed_ms,
                     PicData=base64.b64encode(frame.tobytes()).decode())

    def reset_gif(self):
        self.cmd("Draw/ResetHttpGifId")

    def push_still(self, frame, pic_id, speed_ms=1000):
        """One-request single-frame upload for live streaming (no reset/get-id)."""
        self.cmd("Draw/SendHttpGif", PicNum=1, PicWidth=SIZE, PicOffset=0,
                 PicID=pic_id, PicSpeed=speed_ms,
                 PicData=base64.b64encode(frame.tobytes()).decode())

    def color(self, hex):
        self.send_frames([Image.new("RGB", (SIZE, SIZE), "#" + hex.lstrip("#"))])

    def brightness(self, level):
        self.cmd("Channel/SetBrightness", Brightness=max(0, min(100, int(level))))

    def channel(self, name):
        self.cmd("Channel/SetIndex", SelectIndex=CHANNELS[name])

    def screen(self, on):
        self.cmd("Channel/OnOffScreen", OnOff=1 if on else 0)

    def text(self, msg, color="#FFFFFF", y=28, speed=50):
        self.cmd("Draw/ClearHttpText")
        self.cmd("Draw/SendHttpText", TextId=1, x=0, y=y, dir=0, font=2,
                 TextWidth=SIZE, speed=speed, TextString=msg, color=color, align=1)

    def image(self, path):
        img = Image.open(path)
        frames, durations = [], []
        for f in ImageSequence.Iterator(img):
            frames.append(_to_frame(f.copy()))
            durations.append(f.info.get("duration", 100))
            if len(frames) >= MAX_FRAMES:
                break
        speed = max(20, int(sum(durations) / len(durations)))
        self.send_frames(frames, speed)
        return len(frames)
