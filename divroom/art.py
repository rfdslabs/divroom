"""Pull pixel/ANSI art from 16colo.rs and pan a 64x64 window across it.

16colo.rs renders every piece as a PNG at three sizes:
    https://16colo.rs/pack/<pack>/x1/<urlencoded FILE.ANS>.png   (full, 1:1)
    .../x2/...  (double)   .../tn/...  (thumbnail)
Pieces are 80 columns wide (720px at x1) and arbitrarily tall, so the natural
motion is a vertical scroll: fit the width to the panel, then ping-pong a
64x64 window down the piece and back for a seamless loop.
"""
import io
from urllib.parse import quote

import requests
from PIL import Image

from .control import SIZE

BASE = "https://16colo.rs"
_UA = {"User-Agent": "divroom/0.1 (local Pixoo dashboard)"}


def piece_url(pack, file, view="x1"):
    return f"{BASE}/pack/{pack}/{view}/{quote(file)}.png"


def fetch_piece(pack, file, view="x1", timeout=15):
    r = requests.get(piece_url(pack, file, view), headers=_UA, timeout=timeout)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def _fit_width(img, width):
    if img.width == width:
        return img
    h = max(1, round(img.height * width / img.width))
    resample = Image.NEAREST if width >= img.width else Image.LANCZOS
    return img.resize((width, h), resample)


def pan_frames(img, frames=60, width=SIZE):
    """Ping-pong a SIZExSIZE window across `img`. Returns `frames` RGB frames."""
    img = img.convert("RGB")
    if width:
        img = _fit_width(img, width)
    # Pad up to at least one window in each dimension, centred.
    W, H = img.size
    cw, ch = max(W, SIZE), max(H, SIZE)
    if (cw, ch) != (W, H):
        canvas = Image.new("RGB", (cw, ch))
        canvas.paste(img, ((cw - W) // 2, (ch - H) // 2))
        img, W, H = canvas, cw, ch
    xr, yr = W - SIZE, H - SIZE
    n = max(1, frames)
    out = []
    for k in range(n):
        t = 0.0 if n == 1 else 1 - abs(2 * (k / (n - 1)) - 1)  # 0..1..0 triangle
        x, y = round(xr * t), round(yr * t)
        out.append(img.crop((x, y, x + SIZE, y + SIZE)))
    return out


def build(pack, file, frames=60, view="x1", width=SIZE, timeout=15):
    img = fetch_piece(pack, file, view=view, timeout=timeout)
    return pan_frames(img, frames=frames, width=width)
