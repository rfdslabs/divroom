# Divroom — Pixoo 64 Capture & Control Dashboard

**Date:** 2026-10-11
**Status:** Approved design, pre-plan
**Author:** Rafael (rafa.silva@gmail.com) with Claude

## Purpose

A local macOS tool to observe and control a Divoom Pixoo 64 on the home LAN.
It discovers the device, captures its network traffic live (including the
cloud MQTT/HTTP channels), decodes that traffic into human-readable commands,
and drives the device through its local HTTP API. It is a personal
reverse-engineering and control workbench for hardware the user owns — not a
product, not multi-user, not internet-facing.

Intended outcome: the user runs one command, a dashboard opens in the browser,
and they can (a) see the Pixoo identified on the network, (b) start/stop a live
packet capture, (c) watch packets and decoded MQTT commands stream in real time,
and (d) send display commands to the device.

## Context

Established earlier in this session (empirically, from a real capture):

- Device: `Pixoo64`, IP `192.168.4.20`, MAC `94:b5:55:76:e7:64`, DeviceId
  `300046041`, hardware type `90`. Mac host `192.168.4.27` on `en0`, gateway
  `192.168.4.1`.
- The device exposes an **unauthenticated local HTTP API** at
  `http://192.168.4.20/post` (JSON `{"Command": ...}`). Proven working:
  `Draw/SendHttpGif`, `Draw/SendHttpText`, `Channel/SetBrightness`,
  `Channel/SetIndex`, `Channel/OnOffScreen`, `Channel/GetAllConf`.
- Cloud traffic is **entirely cleartext**: HTTP on port 80 to
  `appin.divoom-gz.com` and **MQTT on port 1883** to `47.251.187.233`.
  No TLS. Device identifies as `ESP32 HTTP Client/1.0` (confirms ESP32 MCU).
- MQTT topic scheme: `divoom/2/<DeviceId>/{get,set,sett,state}`. `state` is
  device→cloud (heartbeats/status); `get`/`set`/`sett` are cloud→device.
  Observed commands in cleartext: `Device/Heartbeat`, `Device/PushAppIP`,
  `Sys/SetConf` (which carries the device's latitude/longitude and timezone).
- Existing code in the repo (to be folded in, kept working):
  `pixoo.py` (control CLI), `arp_redirect.py` (ARP MITM), `carve_firmware.py`
  (pcap firmware carver), and a real capture `pixoo_ota.pcap` (~843 KB) used as
  a test fixture.

## Decisions (from brainstorming)

1. **Form factor:** local web dashboard (Python backend + browser UI), not a
   native `.app` or menu-bar app. Reason: live packet capture needs root, which
   is painful inside a sandboxed native app; Python already has the scapy
   tooling and iterates fastest.
2. **Capture privilege:** shell out to `sudo tcpdump` (+ `sudo` ARP redirect).
   One macOS password prompt at Start. No persistent privileged helper installed.
3. **Control path:** the device's **local HTTP API only**. MQTT is used
   **read-only** (subscribe/decode). No publishing to Divoom's cloud broker.

## Non-goals (YAGNI)

- No user accounts, auth, or multi-user support.
- No database or persistence beyond pcap files on disk.
- No firmware carving in the UI (`carve_firmware.py` stays a CLI).
- No MQTT command injection to the cloud broker.
- No remote/internet access; binds to localhost only.

## Architecture

```
browser (single-page dashboard)
   │  REST (discovery, capture start/stop, control)
   │  WebSocket (live packets + decoded MQTT)
   ▼
FastAPI + uvicorn  (divroom/server.py)
   ├── discovery.py   find the Pixoo (cloud ReturnSameLANDevice + ARP sweep)
   ├── capture.py     manage sudo tcpdump + arp redirect; tail pcap; decode
   ├── mqtt.py        decode MQTT frames; optional read-only paho subscribe
   └── control.py     Pixoo local HTTP API wrapper (refactored pixoo.py)
```

Binds to `127.0.0.1` only. Single long-lived server process; the browser is a
thin live view.

### Components

**`discovery.py`** — `discover() -> list[Device]`. Queries
`https://app.divoom-gz.com/Device/ReturnSameLANDevice`; optionally cross-checks
the ARP table for the device MAC. `Device` dataclass: name, ip, mac, device_id,
hardware. Pure parsing of the JSON response is unit-tested; the network call is
thin and injectable.

**`capture.py`** — owns capture lifecycle:
- `start(ip, iface)`: spawn `sudo tcpdump -i <iface> -s0 -U -w <pcap> host <ip>`
  (packet-buffered so the file grows live) and `sudo .venv/bin/python
  arp_redirect.py --target <ip> --gateway <gw> --iface <iface>`. Record both
  PIDs.
- A reader thread uses `scapy.PcapReader` to read packets as they are appended
  to the pcap, decodes each (via `mqtt.py` for 1883, an HTTP line parser for 80,
  a generic summary otherwise), and hands structured events to a callback
  (the WebSocket broadcaster).
- `stop()`: terminate tcpdump; interrupt `arp_redirect.py` so it restores ARP
  caches; set `net.inet.ip.forwarding=0`. Idempotent; also runs on server exit.
- Status object (running?, pkt count, pcap path, last error) for the UI.

**`mqtt.py`** — `decode_mqtt(payload: bytes) -> list[MqttEvent]`. Parses MQTT
PUBLISH frames (fixed header → topic → payload), extracts the JSON body, pulls
`Command`, and classifies direction from the topic suffix
(`get/set/sett`=cloud→device, `state`=device→cloud). `MqttEvent`: topic,
direction, command, json, raw_len. Optional `subscribe(broker, device_id, cb)`
using paho-mqtt for a richer read-only live feed. Decoder is unit-tested
against `pixoo_ota.pcap`.

**`control.py`** — refactor of `pixoo.py`'s `Pixoo` class: `cmd()`,
`send_frames()`, `text()`, plus helpers for color/brightness/channel/screen and
`raw(command_json)`. Image/GIF handling (Pillow) moves here. `pixoo.py` keeps a
thin CLI that imports this. Live test: `color` → assert `error_code == 0`.

**`server.py`** — FastAPI app:
- `GET /api/discover` → device list.
- `POST /api/capture/start`, `POST /api/capture/stop`, `GET /api/capture/status`.
- `POST /api/control/{action}` (color/text/image/brightness/channel/screen/raw).
- `WS /ws` → streams `{type: "packet"|"mqtt"|"status", ...}` events.
- Serves `static/index.html`, `app.js`, `style.css` (dark UI matching the
  agreed mockup: header with device + Start/Stop + pkt count; two live panels,
  raw packets | MQTT decode; a control panel with a Send-command form).

### Data flow

Start → `capture.start` spawns tcpdump + ARP redirect (one sudo prompt) →
reader thread decodes appended packets → events broadcast on `/ws` → browser
renders the two panels. Control form → `POST /api/control/*` → `control.py` →
device HTTP API. Stop → `capture.stop` → teardown + ARP restore.

### Error handling

Every failure becomes a `status` event shown in the UI status bar, never a
silent crash:
- sudo declined / tcpdump not permitted → "capture needs admin; Start again".
- no device found → discovery returns empty; UI shows "Pixoo not found".
- subprocess dies → reader notices, status flips to stopped with the error.
- server shutdown (signal/atexit) always runs `capture.stop` teardown.

### Testing

- `tests/test_mqtt.py` — feed `tests/fixtures/pixoo_ota.pcap` to the decoder;
  assert it recovers `Sys/SetConf`, `Device/Heartbeat`, the topic set
  `divoom/2/300046041/{get,set,sett,state}`, and the lat/long `-82.7 / 28.1`.
- `tests/test_discovery.py` — parse a captured `ReturnSameLANDevice` JSON into a
  `Device`.
- `tests/test_control.py` — build-command assertions offline; one live test
  (marked, skipped if device unreachable) sends `color` and asserts
  `error_code == 0`.
- Capture start/stop is covered by a smoke test with tcpdump stubbed (no root in
  CI); real capture is verified manually.

### Project layout

```
divroom/
  divroom/
    __init__.py
    discovery.py
    capture.py
    mqtt.py
    control.py
    server.py
    static/{index.html,app.js,style.css}
  tests/
    test_mqtt.py  test_discovery.py  test_control.py
    fixtures/pixoo_ota.pcap
  pixoo.py            # thin CLI over control.py (kept)
  arp_redirect.py     # kept, used by capture.py
  carve_firmware.py   # kept as CLI
  launch              # one command: start uvicorn on 127.0.0.1, open browser
  requirements.txt    # fastapi, uvicorn, scapy, pillow, requests, paho-mqtt
  .venv/
```

## Security & privacy notes (surfaced in the UI)

- All services bind to localhost; the capture is of the user's own device on
  the user's own LAN.
- MQTT is strictly read-only; nothing is published to Divoom's cloud.
- The dashboard explicitly flags that `Sys/SetConf` leaks approximate home
  coordinates in cleartext — a finding to show, not hide.
- Teardown always restores ARP caches and disables IP forwarding so the tool
  leaves the network as it found it.

## Open items for the plan

- Exact mechanism for live-tailing the pcap (incremental `PcapReader` vs. a
  second `tcpdump -l` text stream) — plan picks one and justifies it.
- Whether the ARP redirect is always-on during capture or a separate toggle in
  the UI.
