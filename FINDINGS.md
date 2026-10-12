# Findings: what the Pixoo 64 does on the wire

A reproducible research note on a device the author owns, on the author's own
network. Everything here is **observation only** — no MITM, no TLS decryption.
Reproduce it yourself with the steps below; fill the result tables from *your*
capture rather than trusting numbers in a README.

## Method

The honest constraint: on a switched LAN, a normal host only receives
broadcast, multicast it has joined, and its own unicast. The device's unicast
to the Divoom cloud is **not** visible from another host. So:

1. Capture at a vantage point you control — your **gateway/router**, a managed
   switch **mirror/span port**, or (for a hotspot) the Mac sharing the
   connection:
   ```bash
   # example: capture the device's IP at a gateway/host you control
   sudo tcpdump -i <iface> host <device-ip> -w capture.pcap
   ```
2. Exercise the device: boot it, change channels, let the clock/weather update.
3. Analyze:
   ```bash
   .venv/bin/python pixoo.py sniff analyze capture.pcap --device-ip <device-ip>
   ```

`sniff analyze` surfaces: DNS queries, TLS SNI (plaintext in the ClientHello),
the public endpoints the device contacts, and any **cleartext**
latitude/longitude-looking fields in payloads.

## Finding 1 — Unauthenticated local control API

The device serves a JSON API on `http://<device-ip>/post` with no auth and no
TLS. Any LAN peer can read config and drive the display. Confirmed trivially:

```bash
curl -s http://<device-ip>/post -d '{"Command":"Channel/GetAllConf"}'
```

Returns a non-error JSON config blob. See [SECURITY.md](SECURITY.md) for the
owner implications.

## Finding 2 — The device phones home to the Divoom cloud

Discovery itself relies on Divoom's cloud endpoint:

```
https://app.divoom-gz.com/Device/ReturnSameLANDevice
```

This endpoint lists devices that recently checked in **from the caller's
public IP** — meaning the device (and app) report their presence to the cloud,
keyed to your network's public address. Beyond discovery, the device contacts
Divoom infrastructure for time, weather, and app-pushed content.

**Reproduce:** run `sniff analyze` and read the `DNS queries` / `TLS SNI` /
`Remote endpoints` sections. Record what *you* see:

| Destination (host / IP:port) | Seen via | Purpose (inferred) |
|------------------------------|----------|--------------------|
| `app.divoom-gz.com`          | discovery / DNS | device registration, LAN lookup |
| _(fill from your capture)_   |          |                    |

## Finding 3 — Location / telemetry

The Divoom ecosystem's weather and location features imply the device or the
paired app sends location data to the cloud. `sniff analyze` flags any
**cleartext** coordinate fields (`latitude`, `longitude`, `lat`, `lon`,
`lng`, `gps`, `geohash`, `coordinate`).

Two honest outcomes, both worth recording:

- **Cleartext hit** — the analyzer prints `… latitude=… longitude=…` with the
  source/destination. Record it below. (Plaintext HTTP or MQTT telemetry is
  where this shows up.)
- **No cleartext hit** — the location data is inside TLS. You still learn the
  *destination* it goes to (endpoint + SNI). Decrypting it would require TLS
  interception, which this project intentionally does not do.

| Observation | Value from your capture |
|-------------|-------------------------|
| Cleartext geo field(s) found | _(e.g. none — telemetry was TLS)_ |
| Destination carrying it      | _(host / IP:port)_ |
| Protocol                     | _(HTTP / MQTT / TLS)_ |

## Takeaways for owners

- The local API is open to anyone on the same L2 network — segment the device.
- The device reports to the Divoom cloud, correlated with your public IP.
- Location-bearing telemetry exists in the ecosystem; whether it's observable
  in cleartext depends on the firmware/app version — capture and check.

*This is independent research on owned hardware. Not affiliated with Divoom.*
