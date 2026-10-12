import sys
import time
from divroom.capture import Capture


def test_tcpdump_death_is_reported():
    events = []
    cap = Capture(
        ip="1.2.3.4", gateway="1.2.3.1", iface="lo0",
        on_event=events.append,
        tcpdump_cmd=[sys.executable, "-c", "import sys; sys.exit(3)"],
        arp_cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
    )
    cap.start()
    time.sleep(1.5)
    cap.stop()
    statuses = [e for e in events if e["type"] == "status"]
    assert any(s["error"] for s in statuses), f"expected an error status, got {statuses}"


def test_stop_is_idempotent():
    cap = Capture(ip="1.2.3.4", gateway="1.2.3.1", iface="lo0",
                  on_event=lambda e: None,
                  tcpdump_cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
                  arp_cmd=[sys.executable, "-c", "import time; time.sleep(30)"])
    cap.start()
    cap.stop()
    cap.stop()
    assert cap.status()["running"] is False
