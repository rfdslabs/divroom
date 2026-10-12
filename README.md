# Divroom

A localhost dashboard to **discover, capture, decode, and control** a Divoom
Pixoo 64 on your own LAN. It finds the device, sniffs its traffic live (HTTP +
cloud MQTT, both cleartext), decodes the MQTT commands, and drives the display
through the device's local HTTP API.

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
  (via Divoom's `ReturnSameLANDevice` lookup).
- **Start/Stop capture** — streams the device's packets live into the dashboard.
  **Start prompts for your macOS password once** — it runs `sudo tcpdump` plus
  an ARP redirect so the device's cloud traffic routes through your Mac and is
  visible. Capture is of **your own device on your own network**.
- **MQTT decode** — the right panel shows decoded MQTT (`divoom/2/<id>/{get,set,state}`),
  including the command names. When the device's `Sys/SetConf` goes by, a banner
  flags that it leaks your approximate coordinates **in cleartext** — a real
  privacy finding, shown not hidden.
- **Control** — color, scrolling text, brightness, channel, screen on/off,
  image/GIF upload, and a raw-command box. All sent to the device's **local
  HTTP API only**. MQTT is read-only; nothing is published to Divoom's cloud.

## Safety

- The server binds to `127.0.0.1` only — never exposed to the network.
- Stopping the capture **always** restores the ARP caches and disables IP
  forwarding, leaving your network as it was. If credentials expired and
  forwarding didn't reset, run: `sudo sysctl -w net.inet.ip.forwarding=0`.

## Known values (this network)

Device IP `192.168.4.20`, DeviceId `300046041`, gateway `192.168.4.1`,
interface `en0`, cloud broker `47.251.187.233:1883`. Override discovery-adjacent
defaults with env vars: `PIXOO_GW`, `PIXOO_IFACE`, `PORT`.

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
