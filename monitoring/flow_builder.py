import threading
import time
import logging
import queue
from collections import OrderedDict
from typing import Dict, Tuple, List, Any
from . import config

logger = logging.getLogger("monitor.flow_builder")


class FlowRecord:
    def __init__(self, key: Tuple[str, str, int, int, str], first_packet: Dict[str, Any]):
        self.key = key
        self.packets: List[Dict[str, Any]] = []
        # set basic timestamps before adding the first packet
        self.first_seen = first_packet.get("timestamp", time.time())
        self.last_seen = first_packet.get("timestamp", time.time())
        # initiator (src_ip, src_port) -- define forward direction explicitly
        self.initiator = (first_packet.get("src_ip"), first_packet.get("src_port"))
        # closed flag
        self.closed = False
        # thread lock MUST be created before any packet handling that uses it
        self.lock = threading.RLock()
        # track first-seen window sizes in each direction (None => unknown)
        self.init_win_fwd = None
        self.init_win_bwd = None
        # now add the first packet safely
        self._add_packet(first_packet)

    def _add_packet(self, pkt):
        with self.lock:
            if len(self.packets) >= config.FLOW_MAX_PACKETS:
                # drop further packets but update last_seen
                self.last_seen = pkt["timestamp"]
                return
            self.packets.append(pkt)
            self.last_seen = pkt["timestamp"]
            # record initial window bytes for forward/backward when first packet in that dir seen
            if pkt["src_ip"] == self.key[0] and self.init_win_fwd is None:
                self.init_win_fwd = pkt.get("tcp_window", None)
            if pkt["src_ip"] == self.key[1] and self.init_win_bwd is None:
                self.init_win_bwd = pkt.get("tcp_window", None)

    def add_packet(self, pkt):
        self._add_packet(pkt)

    def is_expired(self, now=None):
        now = now or time.time()
        return (now - self.last_seen) > config.FLOW_IDLE_TIMEOUT

    def close(self):
        with self.lock:
            self.closed = True

    def get_packets(self):
        with self.lock:
            return list(self.packets)


class FlowTable:

    def __init__(self):
        self.flows: Dict[Tuple[str, str, int, int, str], FlowRecord] = OrderedDict()
        self.lock = threading.RLock()
        self._stop = False
        # Queue for flows that have been closed (idle timeout, max packets, FIN/RST, eviction)
        self.closed_queue = queue.Queue()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _make_key(self, src_ip, dst_ip, src_port, dst_port, proto):
        # Keep key direction as seen (no normalization here) — we'll treat fwd/back based on first packet.
        return (src_ip, dst_ip, int(src_port), int(dst_port), proto)

    def add_packet(self, pkt: Dict[str, Any]):
        key = self._make_key(pkt["src_ip"], pkt["dst_ip"], pkt["src_port"], pkt["dst_port"], pkt["protocol"])
        with self.lock:
            if key in self.flows:
                rec = self.flows[key]
                rec.add_packet(pkt)
                # move to end to mark as recently used
                self.flows.move_to_end(key)
                return key, rec
            # new flow
            rec = FlowRecord(key, pkt)
            self.flows[key] = rec
            self.flows.move_to_end(key)
            # eviction if too many flows
            if len(self.flows) > config.MAX_MEMORY_FLOWS:
                old_key, old_rec = self.flows.popitem(last=False)
                # Close and queue the evicted flow so it gets processed
                old_rec.close()
                self.closed_queue.put(old_rec)
                logger.warning("Evicted oldest flow %s due to memory cap", old_key)
            return key, rec

    def get_flow(self, key):
        with self.lock:
            return self.flows.get(key)

    def close_flow(self, key):
        with self.lock:
            rec = self.flows.pop(key, None)
            if rec:
                rec.close()
                self.closed_queue.put(rec)
            return rec

    def _cleanup_loop(self):
        import time
        while not self._stop:
            try:
                now = time.time()
                to_close = []
                with self.lock:
                    for k, rec in list(self.flows.items()):
                        if rec.is_expired(now):
                            to_close.append(k)
                for k in to_close:
                    rec = self.close_flow(k)   # This will push to queue
                    if rec:
                        logger.info("Auto-closed flow %s due to idle timeout (packets=%d)", k, len(rec.packets))
                time.sleep(config.CLEANUP_INTERVAL)
            except Exception:
                logger.exception("Error in flow cleanup loop")

    def stop(self):
        self._stop = True
        self._cleanup_thread.join(timeout=1)