"""Pull pixel/ANSI art from 16colo.rs and pan a 64x64 window across it.

16colo.rs renders every piece as a PNG at three sizes:
    https://16colo.rs/pack/<pack>/x1/<urlencoded FILE.ANS>.png   (full, 1:1)
    .../x2/...  (double)   .../tn/...  (thumbnail)
Pieces are 80 columns wide (720px at x1) and arbitrarily tall, so the natural
motion is a vertical scroll: fit the width to the panel, then ping-pong a
64x64 window down the piece and back for a seamless loop.
"""
import io
import random as _random
import re
from urllib.parse import quote, unquote

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


# --- random slideshow picking ------------------------------------------------

def _get_text(url, timeout=15):
    r = requests.get(url, headers=_UA, timeout=timeout)
    r.raise_for_status()
    return r.text


def _dedup(items):
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it); out.append(it)
    return out


def _pack_names(html):
    return _dedup(re.findall(r'href="/pack/([^/"]+)/"', html))


def _piece_files(html, pack):
    # one path segment after the pack that ends in .ANS, so the x1/x2/tn/ PNG
    # renders (which have another slash) and .NFO/.DIZ sidecars are excluded.
    pat = rf'/pack/{re.escape(pack)}/([^"\'/<>\s]+?\.ANS)(?=["\'])'
    return _dedup(unquote(f) for f in re.findall(pat, html, re.I))


def list_packs(year, timeout=15):
    return _pack_names(_get_text(f"{BASE}/year/{year}/", timeout=timeout))


def list_pieces(pack, timeout=15):
    return _piece_files(_get_text(f"{BASE}/pack/{pack}/", timeout=timeout), pack)


def random_piece(year, rng=None, timeout=15):
    """Pick a random (pack, file) from a year, skipping packs with no .ANS."""
    rng = rng or _random
    packs = list_packs(year, timeout=timeout)
    if not packs:
        raise LookupError(f"no packs for year {year}")
    for _ in range(min(8, len(packs)) + 2):
        pack = rng.choice(packs)
        pieces = list_pieces(pack, timeout=timeout)
        if pieces:
            return pack, rng.choice(pieces)
    raise LookupError(f"no renderable piece found in year {year}")
