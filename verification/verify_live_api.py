import json
import sys
from pathlib import Path

import requests

API_BASE = "http://127.0.0.1:8000"


def check(condition, name, details=""):
    if condition:
        print(f"PASS  {name}")
        return True
    print(f"FAIL  {name}")
    if details:
        print(details)
    return False


def main():
    ok = True

    try:
        health = requests.get(f"{API_BASE}/health", timeout=5).json()
        events = requests.get(f"{API_BASE}/events?limit=5", timeout=5).json()
        devices = requests.get(f"{API_BASE}/devices", timeout=5).json()
    except Exception as e:
        print("FAIL  could not reach API")
        print(e)
        return 2

    print("HEALTH")
    print(json.dumps(health, indent=2))
    print("\nEVENTS")
    print(json.dumps(events, indent=2))
    print("\nDEVICES")
    print(json.dumps(devices, indent=2))

    ok &= check(isinstance(health, dict), "/health returns JSON object")
    ok &= check("model_loaded" in health, "/health has model_loaded")
    ok &= check(isinstance(events, list), "/events returns list")
    ok &= check(isinstance(devices, dict), "/devices returns object")
    ok &= check("devices" in devices, "/devices has devices key")
    ok &= check(isinstance(devices.get("devices", None), list), "/devices.devices is list")

    if events:
        e = events[-1]
        ok &= check("label" in e, "latest event has label")
        ok &= check("confidence" in e, "latest event has confidence")
        ok &= check("source_ip" in e or "src_ip" in e, "latest event has source IP")
        ok &= check("dest_ip" in e or "dst_ip" in e, "latest event has destination IP")

    if devices.get("devices"):
        d = devices["devices"][0]
        bw = d.get("bandwidth", {})
        ok &= check("bps" in bw, "device bandwidth has bps")
        ok &= check("kbps" in bw, "device bandwidth has kbps")
        ok &= check("mbps" in bw, "device bandwidth has mbps")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())