import json
from pathlib import Path

LOG_DIR = Path("logs")
EVENTS = LOG_DIR / "events.jsonl"
ATTACKS = LOG_DIR / "attack_logs.jsonl"
DEVICES = LOG_DIR / "device_snapshot.jsonl"
PACKETS = LOG_DIR / "packet_logs.jsonl"
FLOWS = LOG_DIR / "flow_logs.jsonl"


def tail_jsonl(path: Path, n: int = 1):
    if not path.exists():
        return []
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return []
    return [json.loads(x) for x in lines[-n:]]


def is_benign(label):
    return "BENIGN" in str(label or "").upper()


def fmt(v):
    return json.dumps(v, indent=2, ensure_ascii=False)


def check(condition, name, details=""):
    if condition:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}")
        if details:
            print(details)
    return condition


def main():
    ok = True

    latest_event = tail_jsonl(EVENTS, 1)
    latest_device = tail_jsonl(DEVICES, 1)
    latest_flow = tail_jsonl(FLOWS, 1)
    latest_packet = tail_jsonl(PACKETS, 1)
    latest_attack = tail_jsonl(ATTACKS, 1)

    if not check(bool(latest_event), "events.jsonl has at least one row"):
        ok = False
    if not check(bool(latest_device), "device_snapshot.jsonl has at least one row"):
        ok = False
    if not check(bool(latest_flow), "flow_logs.jsonl has at least one row"):
        ok = False
    if not check(bool(latest_packet), "packet_logs.jsonl has at least one row"):
        ok = False

    if not ok:
        return 1

    event = latest_event[-1]
    device_snapshot = latest_device[-1]
    flow = latest_flow[-1]
    packet = latest_packet[-1]

    flow_meta = flow.get("flow_meta", {})
    event_src = event.get("source_ip")
    event_dst = event.get("dest_ip")
    flow_src = flow_meta.get("src_ip") or flow_meta.get("source_ip")
    flow_dst = flow_meta.get("dst_ip") or flow_meta.get("dest_ip")
    pkt_src = packet.get("src_ip")
    pkt_dst = packet.get("dst_ip")

    print("\nLATEST EVENT")
    print(fmt(event))
    print("\nLATEST FLOW")
    print(fmt(flow))
    print("\nLATEST PACKET")
    print(fmt(packet))
    print("\nLATEST DEVICE SNAPSHOT")
    print(fmt(device_snapshot))

    ok &= check(
        event_src == flow_src or event_src == flow_meta.get("source_ip"),
        "event source_ip matches flow src_ip/source_ip",
        f"event={event_src}, flow={flow_src}, flow.source_ip={flow_meta.get('source_ip')}",
    )
    ok &= check(
        event_dst == flow_dst or event_dst == flow_meta.get("dest_ip"),
        "event dest_ip matches flow dst_ip/dest_ip",
        f"event={event_dst}, flow={flow_dst}, flow.dest_ip={flow_meta.get('dest_ip')}",
    )
    ok &= check(
        pkt_src is not None and pkt_dst is not None,
        "latest packet has src_ip and dst_ip",
    )
    ok &= check(
        isinstance(flow.get("features"), list) and len(flow["features"]) > 0,
        "flow has extracted features",
    )
    ok &= check(
        isinstance(device_snapshot.get("devices"), list),
        "device snapshot has devices list",
    )

    devices = device_snapshot.get("devices", [])
    bps_values = [
        float((d.get("bandwidth") or {}).get("bps") or 0.0)
        for d in devices
    ]
    ok &= check(
        bps_values == sorted(bps_values, reverse=True),
        "device snapshot is sorted by bandwidth.bps descending",
        f"bps order={bps_values}",
    )

    for idx, d in enumerate(devices):
        bw = d.get("bandwidth", {})
        ok &= check(
            "bps" in bw and "kbps" in bw and "mbps" in bw,
            f"device[{idx}] bandwidth has bps/kbps/mbps",
        )

    attack_labels = [
        str(x.get("label") or x.get("attack_type") or "").upper()
        for x in latest_attack
    ]
    if latest_event:
        latest_label = str(event.get("label") or "").upper()
        if is_benign(latest_label):
            ok &= check(
                latest_label not in attack_labels,
                "BENIGN event did not land in attack_logs.jsonl",
                f"label={latest_label}, attack_logs={attack_labels}",
            )
        else:
            ok &= check(
                latest_label in attack_labels,
                "attack event appears in attack_logs.jsonl",
                f"label={latest_label}, attack_logs={attack_labels}",
            )

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())