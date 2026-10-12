"""Procedural 64x64 animations, generated on the host and pushed as GIF frames.

Every generator is a pure function returning a list of RGB PIL Images (one per
frame); `gradient` is a single static frame. `build()` dispatches by name and
always returns a list, so the server can treat every effect uniformly.
"""
import colorsys
import math

from PIL import Image

from .control import SIZE


def _rgb(hex):
    h = hex.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _frame(pixels):
    img = Image.new("RGB", (SIZE, SIZE))
    img.putdata(pixels)
    return img


def rainbow(frames=30):
    """A hue sweep flowing diagonally across the panel, cycling over the loop."""
    out = []
    for k in range(frames):
        phase = k / frames
        px = []
        for y in range(SIZE):
            for x in range(SIZE):
                h = ((x + y) / (2 * SIZE) + phase) % 1.0
                r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
                px.append((int(r * 255), int(g * 255), int(b * 255)))
        out.append(_frame(px))
    return out


def plasma(frames=30):
    """Classic summed-sine plasma field, animated over a seamless loop."""
    out = []
    for k in range(frames):
        t = 2 * math.pi * k / frames
        px = []
        for y in range(SIZE):
            for x in range(SIZE):
                v = (math.sin(x / 8.0 + t)
                     + math.sin(y / 8.0 - t)
                     + math.sin((x + y) / 16.0 + t)
                     + math.sin(math.hypot(x - 32, y - 32) / 8.0 - t))
                h = (v + 4) / 8.0  # normalise 0..1
                r, g, b = colorsys.hsv_to_rgb(h % 1.0, 0.85, 1.0)
                px.append((int(r * 255), int(g * 255), int(b * 255)))
        out.append(_frame(px))
    return out


def sweep(a, b, frames=30):
    """A soft band of colour `b` travelling across a field of colour `a`."""
    ca, cb = _rgb(a), _rgb(b)
    out = []
    for k in range(frames):
        centre = (k / frames) * SIZE
        px = []
        for y in range(SIZE):
            for x in range(SIZE):
                d = abs(x - centre)
                d = min(d, SIZE - d)          # wrap so the loop is seamless
                t = max(0.0, 1.0 - d / 10.0)  # band ~10px wide
                px.append(_lerp(ca, cb, t))
        out.append(_frame(px))
    return out


def pulse(color, frames=30):
    """A solid colour breathing from black to full and back over the loop."""
    c = _rgb(color)
    out = []
    for k in range(frames):
        t = (1 - math.cos(2 * math.pi * k / frames)) / 2  # 0..1..0
        out.append(Image.new("RGB", (SIZE, SIZE), _lerp((0, 0, 0), c, t)))
    return out


def gradient(a, b, angle=0):
    """A static linear gradient from `a` to `b`. angle 0 = left->right, 90 = top->bottom."""
    ca, cb = _rgb(a), _rgb(b)
    rad = math.radians(angle)
    dx, dy = math.cos(rad), math.sin(rad)
    denom = (SIZE - 1) * (abs(dx) + abs(dy)) or 1.0
    px = []
    for y in range(SIZE):
        for x in range(SIZE):
            t = (x * dx + y * dy) / denom
            px.append(_lerp(ca, cb, max(0.0, min(1.0, t))))
    return _frame(px)


ANIMATIONS = ("rainbow", "plasma", "sweep", "pulse")


def build(name, **opts):
    """Return a frame list for `name`. gradient is wrapped as a 1-frame list."""
    if name == "rainbow":
        return rainbow(frames=opts.get("frames", 30))
    if name == "plasma":
        return plasma(frames=opts.get("frames", 30))
    if name == "sweep":
        return sweep(opts.get("a", "#000000"), opts.get("b", "#ffffff"),
                     frames=opts.get("frames", 30))
    if name == "pulse":
        return pulse(opts.get("color", "#ffffff"), frames=opts.get("frames", 30))
    if name == "gradient":
        return [gradient(opts.get("a", "#000000"), opts.get("b", "#ffffff"),
                         angle=opts.get("angle", 0))]
    raise KeyError(name)
