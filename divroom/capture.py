"""Manage the privileged capture: tcpdump (pcap over stdout) + ARP redirect."""
import os
import signal
import subprocess
import threading
import time

from .mqtt import decode_mqtt

PCAP_PATH = "live.pcap"


def _default_tcpdump(iface, ip):
    # -U unbuffered, -w - writes pcap to stdout so we can stream it live.
    return ["sudo", "tcpdump", "-i", iface, "-s0", "-U", "-w", "-", "host", ip]


def _default_arp(iface, ip, gateway):
    py = os.path.join(os.path.dirname(__file__), "..", ".venv", "bin", "python")
    script = os.path.join(os.path.dirname(__file__), "..", "arp_redirect.py")
    return ["sudo", py, script, "--target", ip, "--gateway", gateway, "--iface", iface]


class Capture:
    def __init__(self, ip, gateway, iface, on_event, tcpdump_cmd=None, arp_cmd=None):
        self.ip, self.gateway, self.iface = ip, gateway, iface
        self.on_event = on_event
        self.tcpdump_cmd = tcpdump_cmd or _default_tcpdump(iface, ip)
        self.arp_cmd = arp_cmd or _default_arp(iface, ip, gateway)
        self._tcpdump = self._arp = self._reader = None
        self._running = False
        self.error = None
        self.packets = 0

    def start(self):
        self.error = None
        self.packets = 0
        self._tcpdump = subprocess.Popen(self.tcpdump_cmd, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL)
        self._arp = subprocess.Popen(self.arp_cmd, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # Detect an immediate tcpdump failure (sudo denied / bad iface).
        time.sleep(1.0)
        if self._tcpdump.poll() is not None:
            self._running = False
            self.error = (f"tcpdump exited rc={self._tcpdump.returncode} "
                          f"(sudo denied or bad interface?)")
            self._emit_status()

    def _read_loop(self):
        try:
            from scapy.all import PcapReader, TCP, Raw
            reader = PcapReader(self._tcpdump.stdout)
            for pkt in reader:
                if not self._running:
                    break
                self.packets += 1
                if TCP in pkt and Raw in pkt:
                    sport, dport = pkt[TCP].sport, pkt[TCP].dport
                    load = bytes(pkt[Raw].load)
                    if sport == 1883 or dport == 1883:
                        evs = decode_mqtt(load)
                        self.on_event({"type": "packet", "proto": "mqtt",
                                       "summary": f"MQTT {sport}->{dport} {len(load)}B",
                                       "events": [e.__dict__ for e in evs]})
                        continue
                    if sport == 80 or dport == 80:
                        first = load.split(b"\r\n", 1)[0].decode("latin1", "replace")
                        self.on_event({"type": "packet", "proto": "http",
                                       "summary": f"HTTP {sport}->{dport} {first[:60]}",
                                       "events": []})
                        continue
                    self.on_event({"type": "packet", "proto": "other",
                                   "summary": f"{sport}->{dport} {len(load)}B", "events": []})
        except Exception as e:
            if self._running:
                self.error = f"reader stopped: {e}"
                self._emit_status()

    def _emit_status(self):
        self.on_event({"type": "status", "running": self._running,
                       "error": self.error, "packets": self.packets})

    def stop(self):
        self._running = False
        for proc in (self._arp, self._tcpdump):
            if proc and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGINT)  # lets arp_redirect restore caches
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        # Non-interactive: reuses cached sudo creds from Start, never blocks on a prompt.
        subprocess.run(["sudo", "-n", "sysctl", "-w", "net.inet.ip.forwarding=0"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._emit_status()

    def status(self):
        return {"running": self._running, "packets": self.packets,
                "error": self.error, "pcap_path": PCAP_PATH}
