# monitoring/realtime_monitor.py

import json
import logging
import queue
import socket
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import ipaddress

import requests
from scapy.all import ARP, Ether, ICMP, IP, IPv6, Raw, TCP, UDP, sniff

from . import config
from .flow_builder import FlowTable
from .feature_extractor import FeatureExtractor

logger = logging.getLogger("monitor.realtime")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.handlers.clear()
logger.addHandler(handler)
logger.propagate = False

flow_table = FlowTable()
extractor = FeatureExtractor()

send_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=config.SEND_QUEUE_MAXSIZE)

device_table: Dict[str, Dict[str, Any]] = {}
device_lock = threading.Lock()


def _safe_jsonl_write(path: Path, record: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed writing JSONL: %s", path)


def _resolve_hostname(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        return host
    except Exception:
        return None

def _is_private_ip(ip: Optional[str]) -> bool:
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False

def _host_scope(ip: Optional[str]) -> str:
    return "local" if _is_private_ip(ip) else "external"

def _proto_name(pkt: Any) -> str:
    if ARP in pkt:
        return "ARP"
    if TCP in pkt:
        return "TCP"
    if UDP in pkt:
        return "UDP"
    if ICMP in pkt:
        return "ICMP"
    if IP in pkt:
        return "IP"
    if IPv6 in pkt:
        return "IPv6"
    return "UNKNOWN"


def _ip_version(pkt: Any) -> str:
    if IPv6 in pkt:
        return "IPv6"
    if IP in pkt:
        return "IPv4"
    return "L2/OTHER"


def _extract_packet(pkt: Any) -> Dict[str, Any]:
    ts = time.time()

    src_mac = pkt[Ether].src if Ether in pkt else None
    dst_mac = pkt[Ether].dst if Ether in pkt else None

    src_ip = None
    dst_ip = None
    src_port = None
    dst_port = None
    flags = None
    tcp_window = None
    payload_len = 0

    if IP in pkt:
        src_ip = pkt[IP].src
        dst_ip = pkt[IP].dst
    elif IPv6 in pkt:
        src_ip = pkt[IPv6].src
        dst_ip = pkt[IPv6].dst
    elif ARP in pkt:
        src_ip = pkt[ARP].psrc
        dst_ip = pkt[ARP].pdst

    if TCP in pkt:
        src_port = int(pkt[TCP].sport)
        dst_port = int(pkt[TCP].dport)
        flags = str(pkt[TCP].flags)
        tcp_window = int(pkt[TCP].window)
        if Raw in pkt:
            payload_len = len(bytes(pkt[Raw].load))
    elif UDP in pkt:
        src_port = int(pkt[UDP].sport)
        dst_port = int(pkt[UDP].dport)
        if Raw in pkt:
            payload_len = len(bytes(pkt[Raw].load))
    elif ICMP in pkt:
        if Raw in pkt:
            payload_len = len(bytes(pkt[Raw].load))

    packet_len = int(len(pkt))

    return {
        "timestamp": ts,
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "src_mac": src_mac,
        "dst_mac": dst_mac,
        "src_port": src_port,
        "dst_port": dst_port,
        "protocol": _proto_name(pkt),
        "ip_version": _ip_version(pkt),
        "length": packet_len,
        "flags": flags,
        "tcp_window": tcp_window,
        "payload_len": payload_len,
    }


def _device_key(ip: Optional[str], mac: Optional[str]) -> str:
    return ip or mac or "unknown"


def _update_device_table(pkt: Dict[str, Any]) -> None:
    ts = float(pkt.get("timestamp", time.time()))
    src_ip = pkt.get("src_ip")
    dst_ip = pkt.get("dst_ip")
    src_mac = pkt.get("src_mac")
    dst_mac = pkt.get("dst_mac")
    proto = str(pkt.get("protocol", "UNKNOWN")).upper()
    length = int(pkt.get("length", 0) or 0)

    with device_lock:
        if src_ip:
            key = _device_key(src_ip, src_mac)
            rec = device_table.setdefault(
                key,
                {
                    "id": key,
                    "ip": src_ip,
                    "mac": src_mac,
                    "name": _resolve_hostname(src_ip),
                    "scope": _host_scope(src_ip),
                    "first_seen": ts,
                    "last_seen": ts,
                    "packets_out": 0,
                    "packets_in": 0,
                    "bytes_out": 0,
                    "bytes_in": 0,
                    "protocols": defaultdict(int),
                },
            )
            rec["last_seen"] = ts
            rec["scope"] = _host_scope(src_ip)
            if src_mac and not rec.get("mac"):
                rec["mac"] = src_mac
            if not rec.get("name") and src_ip:
                rec["name"] = _resolve_hostname(src_ip)
            rec["packets_out"] += 1
            rec["bytes_out"] += length
            rec["bytes_in"] += int(length * 0.3)  # simulate return traffic
            rec["protocols"][proto] += 1


        if dst_ip:
            key = _device_key(dst_ip, dst_mac)
            rec = device_table.setdefault(
                key,
                {
                    "id": key,
                    "ip": dst_ip,
                    "mac": dst_mac,
                    "name": _resolve_hostname(dst_ip),
                    "scope": _host_scope(dst_ip),
                    "first_seen": ts,
                    "last_seen": ts,
                    "packets_out": 0,
                    "packets_in": 0,
                    "bytes_out": 0,
                    "bytes_in": 0,
                    "protocols": defaultdict(int),
                },
            )
            rec["last_seen"] = ts
            rec["scope"] = _host_scope(dst_ip)
            if dst_mac and not rec.get("mac"):
                rec["mac"] = dst_mac
            if not rec.get("name") and dst_ip:
                rec["name"] = _resolve_hostname(dst_ip)
            rec["packets_in"] += 1
            rec["bytes_in"] += length
            rec["bytes_out"] += int(length * 0.3)
            rec["protocols"][proto] += 1


def _device_bandwidth(rec):
    now = time.time()

    total_bytes = int(rec.get("bytes_in", 0)) + int(rec.get("bytes_out", 0))

    prev_bytes = rec.get("_prev_bytes")
    prev_ts = rec.get("_prev_ts")

    if prev_bytes is None or prev_ts is None:
        rec["_prev_bytes"] = total_bytes
        rec["_prev_ts"] = now
        return {
            "duration_s": 1.0,
            "bytes": 0,
            "bps": 0.0,
            "pps": 0.0,
        }

    delta_bytes = total_bytes - prev_bytes
    delta_time = max(now - prev_ts, 0.5)

    print("DELTA:", delta_bytes, "TIME:", delta_time)

    bps = (delta_bytes * 8.0) / delta_time

    rec["_prev_bytes"] = total_bytes
    rec["_prev_ts"] = now

    return {
        "duration_s": delta_time,
        "bytes": delta_bytes,
        "bps": min(bps, 1_000_000_000),
        "pps": 0,
    }

def _flow_bandwidth(pkts: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not pkts:
        return {"duration_s": 0.0, "bytes": 0, "bps": 0.0, "pps": 0.0}

    start_ts = float(pkts[0].get("timestamp", time.time()))
    end_ts = float(pkts[-1].get("timestamp", start_ts))
    duration = max(end_ts - start_ts, 0.25)

    total_bytes = sum(int(p.get("length", 0) or 0) for p in pkts)
    total_packets = len(pkts)

    bps = (total_bytes * 8.0) / duration
    pps = total_packets / duration

    return {
        "duration_s": duration,
        "bytes": total_bytes,
        "bps": min(bps, 100_000_000.0),
        "pps": min(pps, 100_000.0),
    }


def _log_packet(pkt: Dict[str, Any]) -> None:
    _safe_jsonl_write(
        config.LOG_DIR / "packet_logs.jsonl",
        {
            "timestamp": pkt.get("timestamp"),
            "src_ip": pkt.get("src_ip"),
            "dst_ip": pkt.get("dst_ip"),
            "src_mac": pkt.get("src_mac"),
            "dst_mac": pkt.get("dst_mac"),
            "protocol": pkt.get("protocol"),
            "ip_version": pkt.get("ip_version"),
            "src_port": pkt.get("src_port"),
            "dst_port": pkt.get("dst_port"),
            "length": pkt.get("length"),
            "flags": pkt.get("flags"),
            "tcp_window": pkt.get("tcp_window"),
            "payload_len": pkt.get("payload_len"),
        },
    )


def _log_device_snapshot() -> None:
    with device_lock:
        snapshot = []
        for rec in device_table.values():
            item = dict(rec)
            item["protocols"] = dict(item.get("protocols", {}))
            item["bandwidth"] = _device_bandwidth(rec)
            item["scope"] = _host_scope(item.get("ip"))
            snapshot.append(item)

        snapshot.sort(
            key=lambda x: float(x.get("bandwidth", {}).get("bps", 0.0)),
            reverse=True,
        )

        snapshot = snapshot[:25]

    _safe_jsonl_write(
        config.LOG_DIR / "device_snapshot.jsonl",
        {
            "timestamp": time.time(),
            "devices": snapshot,
            "connected_devices": len(snapshot),
        },
    )


def _log_flow(flow_rec: Any, features: Any, flow_meta: Dict[str, Any]) -> None:
    try:
        rec = {
            "key": list(flow_rec.key),
            "first_seen": flow_rec.first_seen,
            "last_seen": flow_rec.last_seen,
            "n_packets": len(flow_rec.packets),
            "flow_meta": flow_meta,
            "features": features,
        }
        _safe_jsonl_write(config.FLOW_LOG, rec)
    except Exception:
        logger.exception("Failed to log flow record")


def _safe_put(q: "queue.Queue[Dict[str, Any]]", item: Dict[str, Any]) -> None:
    try:
        q.put_nowait(item)
    except queue.Full:
        logger.warning("send_queue full; dropping feature vector")


def _has_network_connectivity(timeout: float = 1.5) -> bool:
    targets = [("1.1.1.1", 53), ("8.8.8.8", 53)]
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            continue
    return False


def sender_loop(stop_event: threading.Event) -> None:
    session = requests.Session()
    batch: List[Dict[str, Any]] = []

    try:
        while not stop_event.is_set():
            try:
                item = send_queue.get(timeout=1.0)
            except queue.Empty:
                item = None

            if item is not None:
                batch.append(item)

            if not batch:
                continue

            if len(batch) < config.BATCH_SIZE and item is not None:
                continue

            payload_instances = [b["features"] for b in batch]
            payload_flow_meta = [b["flow_meta"] for b in batch]

            url = config.BATCH_API_URL if len(payload_instances) > 1 else config.API_URL
            payload = (
                {"instances": payload_instances, "flow_meta": payload_flow_meta}
                if len(payload_instances) > 1
                else {"features": payload_instances[0], "flow_meta": payload_flow_meta[0]}
            )

            success = False
            for attempt in range(config.API_RETRIES):
                try:
                    resp = session.post(url, json=payload, timeout=config.API_TIMEOUT)
                    if resp.status_code in (200, 201):
                        success = True
                        logger.info("Sent %d flow(s) to API", len(batch))
                        break
                    logger.warning("API returned %s: %s", resp.status_code, resp.text)
                except Exception:
                    logger.exception("Error sending request attempt %d", attempt + 1)

                time.sleep(config.API_BACKOFF * (2**attempt))

            if not success:
                logger.error("Failed to send batch after retries")
                failed_path = config.SEND_QUEUE_PERSIST_DIR / f"failed_batch_{int(time.time())}.jsonl"
                for obj in batch:
                    _safe_jsonl_write(failed_path, obj)

            batch = []

    finally:
        if batch:
            failed_path = config.SEND_QUEUE_PERSIST_DIR / f"failed_batch_{int(time.time())}.jsonl"
            for obj in batch:
                _safe_jsonl_write(failed_path, obj)
        session.close()

def process_closed_flow(flow_rec: Any) -> None:
    try:
        pkts = flow_rec.get_packets()
        if not pkts:
            return

        first = pkts[0]
        last = pkts[-1]

        src_ip = first.get("src_ip")
        dst_ip = first.get("dst_ip")

        if not src_ip or not dst_ip:
            return

        protocol = str(first.get("protocol", "")).upper()

        if protocol not in {"TCP", "UDP"}:
            return

        src_port = first.get("src_port")
        dst_port = first.get("dst_port")

        if src_port is None or dst_port is None:
            return

        flow_meta = {
            "timestamp": last.get("timestamp", time.time()),
            "first_seen": first.get("timestamp", time.time()),
            "last_seen": last.get("timestamp", time.time()),

            "source_ip": src_ip,
            "dest_ip": dst_ip,

            "src_ip": src_ip,
            "dst_ip": dst_ip,

            "source_mac": first.get("src_mac"),
            "dest_mac": first.get("dst_mac"),
            "src_mac": first.get("src_mac"),
            "dst_mac": first.get("dst_mac"),

            "protocol": protocol,
            "ip_version": first.get("ip_version", "UNKNOWN"),

            "src_host": _resolve_hostname(src_ip),
            "dst_host": _resolve_hostname(dst_ip),

            "packet_count": len(pkts),
            "bandwidth": _flow_bandwidth(pkts),
        }

        features = extractor.extract(pkts)

        _safe_put(send_queue, {
            "features": features,
            "flow_meta": flow_meta
        })

        _log_flow(flow_rec, features, flow_meta)

    except Exception:
        logger.exception("Error processing closed flow")


def process_closed_flows_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            flow_rec = flow_table.closed_queue.get(timeout=1.0)
            process_closed_flow(flow_rec)
        except queue.Empty:
            continue
        except Exception:
            logger.exception("Error in process_closed_flows_loop")

def flush_active_flows_loop(stop_event):
    while not stop_event.is_set():
        now = time.time()

        for key, flow in list(flow_table.flows.items()):
            if len(flow.packets) < 2:
                continue

            last_seen = flow.packets[-1]["timestamp"]

            # flush after 1 second of inactivity for a more live feel
            if now - last_seen > 1:
                process_closed_flow(flow)
                flow_table.close_flow(key)

        stop_event.wait(0.5)


def packet_callback(pkt: Any) -> None:
    try:
        pkt_data = _extract_packet(pkt)

        _update_device_table(pkt_data)
        _log_packet(pkt_data)

        protocol = str(pkt_data.get("protocol", "")).upper()
        src_ip = pkt_data.get("src_ip")
        dst_ip = pkt_data.get("dst_ip")
        src_port = pkt_data.get("src_port")
        dst_port = pkt_data.get("dst_port")

        is_transport_flow = (
            protocol in {"TCP", "UDP"}
            and src_ip is not None
            and dst_ip is not None
            and src_port is not None
            and dst_port is not None
        )

        if not is_transport_flow:
            return

        key, rec = flow_table.add_packet(pkt_data)

        flags = pkt_data.get("flags") or ""
        if "F" in flags or "R" in flags:
            flow_table.close_flow(key)
        elif len(rec.packets) >= config.FLOW_MAX_PACKETS:
            flow_table.close_flow(key)

    except Exception:
        logger.exception("Error in packet_callback")

def _device_heartbeat_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            _log_device_snapshot()
        except Exception:
            logger.exception("Error in device heartbeat loop")

        time.sleep(1)   #  FORCE 1 SECOND (NO CONFIG)
        
def run_monitor() -> None:
    stop_event = threading.Event()

    if not _has_network_connectivity():
        print("I'm offline — no capturing")
        logger.warning("I'm offline — no capturing")
        return

    sender_thread = threading.Thread(target=sender_loop, args=(stop_event,), daemon=True)
    consumer_thread = threading.Thread(target=process_closed_flows_loop, args=(stop_event,), daemon=True)
    device_thread = threading.Thread(target=_device_heartbeat_loop, args=(stop_event,), daemon=True)

    sender_thread.start()
    consumer_thread.start()
    device_thread.start()

    flush_thread = threading.Thread(
        target=flush_active_flows_loop,
        args=(stop_event,),
        daemon=True
    )

    flush_thread.start()
    time.sleep(2)
    _log_device_snapshot()
    try:
        logger.info(
            "Starting live capture on interface=%s promisc=%s",
            config.INTERFACE,
            config.PROMISCUOUS,
        )
        sniff(
            iface=config.INTERFACE,
            prn=packet_callback,
            store=False,
            promisc=config.PROMISCUOUS,
        )
    except KeyboardInterrupt:
        logger.info("Shutting down monitor due to KeyboardInterrupt")
    finally:
        stop_event.set()
        sender_thread.join(timeout=3)
        consumer_thread.join(timeout=3)
        device_thread.join(timeout=3)
        flow_table.stop()
        logger.info("Monitor stopped")


if __name__ == "__main__":
    run_monitor()