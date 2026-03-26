# monitoring/realtime_monitor.py

import logging
import threading
import time
import json
import queue
from typing import Dict, Any, List
import requests

from . import config
from .packet_capture import start_packet_capture
from .flow_builder import FlowTable
from .feature_extractor import FeatureExtractor
from pathlib import Path

logger = logging.getLogger("monitor.realtime")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
logger.addHandler(handler)

flow_table = FlowTable()
extractor = FeatureExtractor()
send_queue: "queue.Queue[List[float]]" = queue.Queue()

# Background sender thread collects feature vectors and posts in batches
def sender_loop(stop_event: threading.Event):
    session = requests.Session()
    batch: List[Dict[str, Any]] = []
    while not stop_event.is_set():
        try:
            # wait for one item with timeout so we can check stop_event periodically
            try:
                item = send_queue.get(timeout=1.0)
            except queue.Empty:
                item = None

            if item:
                batch.append(item)

            # send if batch size reached or if queue empty for a short time
            if batch and (len(batch) >= config.BATCH_SIZE or (item is None and len(batch) > 0)):
                payload_instances = [b["features"] for b in batch]
                url = config.BATCH_API_URL if len(payload_instances) > 1 else config.API_URL
                # attempt with retries
                success = False
                for attempt in range(config.API_RETRIES):
                    try:
                        resp = session.post(url, json={"instances": payload_instances} if url.endswith("/batch") else {"features": payload_instances[0]}, timeout=config.API_TIMEOUT)
                        if resp.status_code in (200, 201):
                            logger.info("Sent %d flows to API (status=%d)", len(batch), resp.status_code)
                            success = True
                            break
                        else:
                            logger.warning("API returned status=%d body=%s", resp.status_code, resp.text)
                    except Exception as e:
                        logger.exception("Error sending request attempt %d", attempt+1)
                    time.sleep(config.API_BACKOFF * (2 ** attempt))
                if not success:
                    logger.error("Failed to send batch of %d flows after retries", len(batch))
                    # optionally persist to disk for later retry
                    _persist_failed_batch(batch)
                batch = []
        except Exception:
            logger.exception("Unexpected error in sender_loop")
    # flush remaining
    if batch:
        _persist_failed_batch(batch)
    session.close()

def _persist_failed_batch(batch):
    try:
        p = config.LOG_DIR / f"failed_batch_{int(time.time())}.jsonl"
        with open(p, "a", encoding="utf-8") as f:
            for obj in batch:
                f.write(json.dumps(obj) + "\n")
        logger.info("Persisted failed batch to %s", p)
    except Exception:
        logger.exception("Failed persisting failed batch")

# When flows are closed we push features to send_queue
def process_closed_flow(flow_rec):
    try:
        pkts = flow_rec.get_packets()

        # 🔍 DEBUG START
        if pkts:
            print("FLOW LENGTH:", len(pkts))
            print("FIRST TS:", pkts[0]["timestamp"])
            print("LAST TS:", pkts[-1]["timestamp"])
            print("DURATION:", pkts[-1]["timestamp"] - pkts[0]["timestamp"])
            print("-"*40)
        # 🔍 DEBUG END

        features = extractor.extract(pkts)

        payload = {"features": features}
        send_queue.put(payload)

        _log_flow(flow_rec, features)

    except Exception:
        logger.exception("Error processing closed flow")
"""
def process_closed_flow(flow_rec):
    try:
        pkts = flow_rec.get_packets()
        features = extractor.extract(pkts)
        payload = {"features": features}
        send_queue.put(payload)
        # also write flow log
        _log_flow(flow_rec, features)
    except Exception:
        logger.exception("Error processing closed flow")"""

def _log_flow(flow_rec, features):
    try:
        rec = {
            "key": list(flow_rec.key),
            "first_seen": flow_rec.first_seen,
            "last_seen": flow_rec.last_seen,
            "n_packets": len(flow_rec.packets),
            "features": features
        }
        with open(config.FLOW_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        logger.exception("Failed to log flow record")

# NEW: Consumer thread that processes flows from flow_table.closed_queue

def process_closed_flows_loop(stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            flow_rec = flow_table.closed_queue.get(timeout=1.0)
            process_closed_flow(flow_rec)
        except queue.Empty:
            continue
        except Exception:
            logger.exception("Error in process_closed_flows_loop")

# Packet callback invoked per packet captured
def packet_callback(**pkt):
    try:
        key, rec = flow_table.add_packet(pkt)
        # conditions to close:
        # - TCP FIN or RST seen (we detect via flags)
        if pkt.get("flags") and ("F" in pkt.get("flags") or "R" in pkt.get("flags")):
            # close flow – it will be queued automatically
            flow_table.close_flow(key)          # <-- just close, no direct processing
        else:
            # optionally close if flow too big (safety) or other heuristics
            if len(rec.packets) >= config.FLOW_MAX_PACKETS:
                flow_table.close_flow(key)      # <-- just close
    except Exception:
        logger.exception("Error in packet_callback")

# Simulation mode: generates synthetic flows (useful for testing without root)
def _simulate_traffic(stop_event):

    import random
    import time

    users = [f"192.168.1.{i}" for i in range(2,40)]

    while not stop_event.is_set():

        now = time.time()

        src = random.choice(users)

        dst = f"10.0.0.{random.randint(2,20)}"

        sport = random.randint(1024,65535)

        behaviour = random.random()

        # ---------------- normal user behaviour ----------------
        if behaviour < 0.80:

            service = random.choice([
                ("web",80),
                ("https",443),
                ("ssh",22)
            ])

            dport = service[1]

            session_length = random.randint(6,25)

            current_time = now

            # SYN
            packet_callback(
                src_ip=src,
                dst_ip=dst,
                src_port=sport,
                dst_port=dport,
                protocol="TCP",
                length=60,
                flags="S",
                timestamp=current_time,
                tcp_window=60000,
                payload_len=0
            )

            for _ in range(session_length):

                gap=random.uniform(0.05,0.4)

                current_time+=gap

                packet_callback(
                    src_ip=src,
                    dst_ip=dst,
                    src_port=sport,
                    dst_port=dport,
                    protocol="TCP",

                    length=random.randint(300,1400),

                    flags="PA",

                    timestamp=current_time,

                    tcp_window=random.randint(20000,65000),

                    payload_len=random.randint(200,1100)
                )

            # FIN
            current_time+=random.uniform(0.05,0.2)

            packet_callback(
                src_ip=src,
                dst_ip=dst,
                src_port=sport,
                dst_port=dport,
                protocol="TCP",

                length=40,

                flags="F",

                timestamp=current_time,

                tcp_window=0,
                payload_len=0
            )

            time.sleep(random.uniform(0.4,1.2))


        # ---------------- occasional scan ----------------
        elif behaviour < 0.95:

            ports=[22,80,443,8080,3306]

            for port in random.sample(ports,random.randint(2,3)):

                current_time=time.time()

                packet_callback(
                    src_ip=src,
                    dst_ip=dst,
                    src_port=random.randint(1024,65535),
                    dst_port=port,
                    protocol="TCP",
                    length=60,
                    flags="S",
                    timestamp=current_time,
                    tcp_window=2000,
                    payload_len=0
                )

                current_time+=random.uniform(0.02,0.06)

                packet_callback(
                    src_ip=src,
                    dst_ip=dst,
                    src_port=random.randint(1024,65535),
                    dst_port=port,
                    protocol="TCP",
                    length=40,
                    flags="F",
                    timestamp=current_time,
                    tcp_window=0,
                    payload_len=0
                )

            time.sleep(random.uniform(0.5,1.5))


        # ---------------- rare abnormal spike ----------------
        else:

            attack_target="10.0.0.5"

            current_time=now

            packet_callback(
                src_ip=src,
                dst_ip=attack_target,
                src_port=sport,
                dst_port=80,
                protocol="TCP",
                length=60,
                flags="S",
                timestamp=current_time,
                tcp_window=2000,
                payload_len=0
            )

            for _ in range(random.randint(15,30)):

                current_time+=random.uniform(0.002,0.015)

                packet_callback(
                    src_ip=src,
                    dst_ip=attack_target,
                    src_port=sport,
                    dst_port=80,
                    protocol="TCP",

                    length=random.randint(500,1500),

                    flags="PA",

                    timestamp=current_time,

                    tcp_window=1500,

                    payload_len=random.randint(400,1300)
                )

            current_time+=0.02

            packet_callback(
                src_ip=src,
                dst_ip=attack_target,
                src_port=sport,
                dst_port=80,
                protocol="TCP",

                length=40,

                flags="F",

                timestamp=current_time,

                tcp_window=0,
                payload_len=0
            )

            time.sleep(0.2)

def run_monitor():
    stop_event = threading.Event()
    sender_thread = threading.Thread(target=sender_loop, args=(stop_event,), daemon=True)
    sender_thread.start()

    # NEW: closed flow consumer thread
    consumer_thread = threading.Thread(target=process_closed_flows_loop, args=(stop_event,), daemon=True)
    consumer_thread.start()

    try:
        if config.SIMULATE:
            logger.info("SIMULATE mode enabled: generating synthetic traffic")
            _simulate_traffic(stop_event)
        else:
            # attempt live capture; if scapy raises permission/import errors, caller should set SIMULATE true
            try:
                start_packet_capture(packet_callback, interface=config.INTERFACE, promisc=config.PROMISCUOUS)
            except Exception as e:
                logger.exception("Live capture failed; falling back to simulation mode: %s", e)
                # fallback to simulation mode
                _simulate_traffic(stop_event)
    except KeyboardInterrupt:
        logger.info("Shutting down monitor due to KeyboardInterrupt")
    finally:
        stop_event.set()
        sender_thread.join(timeout=3)
        consumer_thread.join(timeout=1)
        flow_table.stop()
        logger.info("Monitor stopped")

if __name__ == "__main__":
    run_monitor()

    