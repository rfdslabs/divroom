# Security & authorized use

## Use boundary

This project is for **devices and networks you own or are explicitly
authorized to test**. The discovery, control, and observation tools are
LAN-scoped and assume consent. Do not use them against third-party devices or
networks.

What this project deliberately does **not** do:

- No internet-wide scanning or mass targeting of devices you don't own.
- No ARP spoofing, no MITM, no packet injection.
- No TLS interception or decryption.
- No firmware flashing or anything that bricks the device.

The observation tooling (`divroom/sniff.py`) is **read-only**: it analyzes
traffic the network already delivers to the capturing host (your own gateway
capture, or the broadcast/multicast a host legitimately receives).

## Device finding: the Pixoo 64 local API is unauthenticated

The Pixoo 64 exposes a JSON HTTP API on port 80 with **no authentication,
no authorization, and no transport encryption**:

```bash
curl -s http://<device-ip>/post -d '{"Command":"Channel/GetAllConf"}'
```

Any host on the same L2 network can read configuration and drive the display
(`Draw/SendHttpGif`, `Channel/SetBrightness`, `Channel/OnOffScreen`, …). There
is no pairing, token, or ACL.

**Implications for owners**

- Treat the Pixoo as an untrusted LAN peer. Anyone on the same Wi-Fi
  (including guests) can control it or turn it off.
- Put it on an IoT/guest VLAN segment if your network supports it.
- The device also talks to the Divoom cloud; see
  [FINDINGS.md](FINDINGS.md) for how to observe that traffic yourself.

This is a property of the shipped firmware, not a flaw introduced by this
project. It is documented here so owners understand the exposure.

## Reporting a vulnerability in *this project*

If you find a security issue in the divroom code (not the device), please open
a private report via GitHub Security Advisories on the repository, or contact
the maintainer, rather than filing a public issue. Include repro steps and the
affected version/commit.

For issues in the Divoom **device or cloud**, report to the vendor (Divoom).
This project is an independent, unaffiliated hobby/research effort.
