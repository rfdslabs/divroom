# Contributing

Thanks for your interest! divroom is hobby/research software for the Divoom
Pixoo 64.

## Ground rules

- **Authorization boundary.** Contributions must respect the scope in
  [SECURITY.md](SECURITY.md): LAN-scoped, owned/authorized devices only,
  observation-only for network tooling. PRs that add MITM, mass scanning,
  TLS interception, or firmware-bricking paths will be declined.
- **Tests.** New behavior comes with tests. Keep the suite green:
  ```bash
  .venv/bin/python -m pytest -q
  ```
  Network/device/hardware is injectable — unit tests must not require a real
  Pixoo, the Divoom cloud, scapy, or a camera.
- **Stock firmware.** This project targets the shipped firmware's local API.

## Dev setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-capture.txt   # optional: scapy
```

## Conventions

- Small, focused modules; each file has one clear responsibility.
- Prefer pure, testable functions with injected dependencies over code that
  reaches for the network/hardware directly.
- Match the surrounding style.

Open an issue to discuss larger changes before sending a big PR.
