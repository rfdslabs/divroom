# Divroom

A localhost dashboard to **discover and control** a Divoom Pixoo 64 on your
own LAN. It finds the device and drives the display through the device's
local HTTP API.

For **stock firmware**. (Flashing WLED is a separate, destructive path that
removes everything this tool talks to — see `docs/` discussion if you go there.)

## Run

```
./launch
```

Opens `http://127.0.0.1:8000` in your browser. Override the port with
`PORT=8080 ./launch`.

## What you can do

- **Discover** — the header shows the Pixoo's name, IP, and device ID
  (via Divoom's `ReturnSameLANDevice` lookup, with a LAN probe fallback).
- **Control** — color, scrolling text, brightness, channel, screen on/off,
  image/GIF upload, and a raw-command box. All sent to the device's **local
  HTTP API only**.

## Safety

- The server binds to `127.0.0.1` only — never exposed to the network.
- Mutating requests are rejected unless they come from a localhost Origin.

## Known values (this network)

Device IP `192.168.4.20`, DeviceId `300046041`, gateway `192.168.4.1`,
interface `en0`. Override discovery with `PIXOO_IP`; set `PORT` to change
the dashboard port.

## CLI

`pixoo.py` is a thin CLI over the same control module:

```
.venv/bin/python pixoo.py --ip 192.168.4.20 color ff0080
.venv/bin/python pixoo.py --ip 192.168.4.20 text "BRB" --background 000000 --color "#00FF00"
.venv/bin/python pixoo.py --ip 192.168.4.20 image ~/Pictures/cat.gif
.venv/bin/python pixoo.py --ip 192.168.4.20 info
```

## Tests

```
.venv/bin/python -m pytest -q
```

The live device test is skipped unless `PIXOO_LIVE=1 PIXOO_IP=<ip>` are set.
