# monitoring/feature_extractor.py  (complete replacement of previous class and helpers)

from typing import List, Dict, Any, Optional
import numpy as np
import math
import logging
from pathlib import Path
import json
from . import config

logger = logging.getLogger("monitor.feature_extractor")

# Helper numeric guards
def safe_mean(x):
    return float(np.mean(x)) if len(x) else 0.0

def safe_std(x):
    return float(np.std(x, ddof=0)) if len(x) else 0.0

def safe_min(x):
    return float(min(x)) if len(x) else 0.0

def safe_max(x):
    return float(max(x)) if len(x) else 0.0

def clamp_value(v):
    # map non-finite to safe 0.0, clamp huge absolute values
    try:
        if v is None:
            return 0.0
        fv = float(v)
        if not np.isfinite(fv):
            return 0.0
        if fv > config.VALUE_CLAMP_MAX:
            return config.VALUE_CLAMP_MAX
        if fv < config.VALUE_CLAMP_MIN:
            return config.VALUE_CLAMP_MIN
        return fv
    except Exception:
        return 0.0

# Load canonical feature order from model/feature_list.json if present, otherwise fallback
FEATURE_ORDER = None
_model_feat = Path(__file__).resolve().parents[1] / "model" / "feature_list.json"
if _model_feat.exists():
    try:
        FEATURE_ORDER = json.loads(_model_feat.read_text(encoding="utf-8"))
    except Exception:
        FEATURE_ORDER = None

# fallback hardcoded order (must match your model packaging)
if not FEATURE_ORDER:
    FEATURE_ORDER = [
      "Destination Port",
      "Flow Duration",
      "Fwd Packet Length Max",
      "Fwd Packet Length Min",
      "Fwd Packet Length Std",
      "Bwd Packet Length Max",
      "Bwd Packet Length Min",
      "Flow Bytes/s",
      "Flow Packets/s",
      "Flow IAT Mean",
      "Flow IAT Std",
      "Flow IAT Min",
      "Fwd IAT Mean",
      "Fwd IAT Std",
      "Fwd IAT Max",
      "Fwd IAT Min",
      "Bwd IAT Total",
      "Bwd IAT Mean",
      "Bwd IAT Std",
      "Bwd IAT Max",
      "Bwd IAT Min",
      "Bwd Packets/s",
      "Min Packet Length",
      "Max Packet Length",
      "Packet Length Variance",
      "FIN Flag Count",
      "SYN Flag Count",
      "PSH Flag Count",
      "ACK Flag Count",
      "URG Flag Count",
      "Down/Up Ratio",
      "Average Packet Size",
      "Avg Fwd Segment Size",
      "Avg Bwd Segment Size",
      "Subflow Fwd Bytes",
      "Subflow Bwd Bytes",
      "Init_Win_bytes_forward",
      "Init_Win_bytes_backward",
      "act_data_pkt_fwd",
      "min_seg_size_forward",
      "Active Mean",
      "Active Std",
      "Active Max",
      "Active Min",
      "Idle Std"
    ]

# ensure canonical length
if len(FEATURE_ORDER) != 45:
    logger.warning("FEATURE_ORDER length != 45 (found %d). Using pad/truncate.", len(FEATURE_ORDER))

class FeatureExtractor:
    def __init__(self, active_gap_threshold: float = config.ACTIVE_GAP_THRESHOLD):
        self.active_gap = active_gap_threshold

    def extract(self, packets: List[Dict[str, Any]], initiator: Optional[tuple] = None) -> List[float]:
        """
        packets: list of packet dicts (same as before)
        initiator: optional tuple (src_ip, src_port) to explicitly define forward direction
                   if provided, it will be used instead of first packet inference.
        returns: list of 45 floats in EXACT order of FEATURE_ORDER
        """
        # quick zero-vector fallback
        if not packets:
            return [0.0] * 45

        # sort packets by timestamp for deterministic ordering
        packets = sorted(packets, key=lambda p: float(p.get("timestamp", 0.0)))

        # determine forward initiator (prefer provided initiator)
        if initiator and isinstance(initiator, (list, tuple)) and len(initiator) == 2:
            f_ip, f_port = initiator[0], initiator[1]
        else:
            first = packets[0]
            f_ip = first.get("src_ip")
            f_port = first.get("src_port")

        # collect direction-separated stats
        fwd_ts, bwd_ts = [], []
        fwd_lens, bwd_lens = [], []
        fwd_payloads, bwd_payloads = [], []
        fwd_windows, bwd_windows = [], []
        flags_counts = {"F":0,"S":0,"P":0,"A":0,"U":0}
        pkt_times, pkt_lengths = [], []

        for pkt in packets:
            ts = float(pkt.get("timestamp", 0.0))
            length = int(pkt.get("length", 0) or 0)
            payload_len = int(pkt.get("payload_len", 0) or 0)
            pkt_times.append(ts)
            pkt_lengths.append(length)

            same_dir = (pkt.get("src_ip") == f_ip and pkt.get("src_port") == f_port)
            if same_dir:
                fwd_ts.append(ts); fwd_lens.append(length); fwd_payloads.append(payload_len)
                if pkt.get("tcp_window") is not None:
                    fwd_windows.append(pkt.get("tcp_window"))
            else:
                bwd_ts.append(ts); bwd_lens.append(length); bwd_payloads.append(payload_len)
                if pkt.get("tcp_window") is not None:
                    bwd_windows.append(pkt.get("tcp_window"))

            fl = pkt.get("flags") or ""
            if "F" in fl: flags_counts["F"] += 1
            if "S" in fl: flags_counts["S"] += 1
            if "P" in fl: flags_counts["P"] += 1
            if "A" in fl: flags_counts["A"] += 1
            if "U" in fl: flags_counts["U"] += 1

        # basic metrics (guard duration)
        flow_duration = (pkt_times[-1] - pkt_times[0]) if len(pkt_times) >= 2 else 0.0
        total_packets = len(pkt_times)
        total_bytes = sum(pkt_lengths)

# Explicitly treat zero-duration flows as zero throughput (avoid huge values)
        if flow_duration <= 0.0:
            pps = 0.0
            bps = 0.0
            flow_duration_safe = config.EPSILON  # still useful later if needed
        else:
            flow_duration_safe = max(flow_duration, config.EPSILON)
            pps = total_packets / flow_duration_safe
            bps = total_bytes / flow_duration_safe

        # IAT calculations (safe)
        if len(pkt_times) >= 2:
            iats = np.diff(pkt_times)
            flow_iat_mean = float(np.mean(iats))
            flow_iat_std = float(np.std(iats, ddof=0))
            flow_iat_min = float(np.min(iats))
        else:
            flow_iat_mean = flow_iat_std = flow_iat_min = 0.0

        def iat_stats(ts_list):
            if len(ts_list) >= 2:
                arr = np.diff(ts_list)
                return float(np.mean(arr)), float(np.std(arr, ddof=0)), float(np.max(arr)), float(np.min(arr))
            else:
                return 0.0, 0.0, 0.0, 0.0

        fwd_iat_mean, fwd_iat_std, fwd_iat_max, fwd_iat_min = iat_stats(fwd_ts)
        bwd_iat_mean, bwd_iat_std, bwd_iat_max, bwd_iat_min = iat_stats(bwd_ts)

        # packet length stats
        fwd_pkt_len_max = safe_max(fwd_lens)
        fwd_pkt_len_min = safe_min(fwd_lens)
        fwd_pkt_len_std = safe_std(fwd_lens)

        bwd_pkt_len_max = safe_max(bwd_lens)
        bwd_pkt_len_min = safe_min(bwd_lens)
        bwd_pkt_len_std = safe_std(bwd_lens)

        min_pkt_len = safe_min(pkt_lengths)
        max_pkt_len = safe_max(pkt_lengths)
        pkt_len_var = float(np.var(pkt_lengths)) if len(pkt_lengths) else 0.0

        bytes_fwd = float(sum(fwd_lens)) if fwd_lens else 0.0
        bytes_bwd = float(sum(bwd_lens)) if bwd_lens else 0.0
        down_up_ratio = (bytes_bwd / (bytes_fwd if bytes_fwd > 0 else config.EPSILON)) if (bytes_fwd > 0 or bytes_bwd>0) else 0.0

        avg_pkt_size = (float(total_bytes) / total_packets) if total_packets > 0 else 0.0
        avg_fwd_segment = (float(safe_mean(fwd_payloads)) if len(fwd_payloads) else 0.0)
        avg_bwd_segment = (float(safe_mean(bwd_payloads)) if len(bwd_payloads) else 0.0)

        SUBFLOW_PKT_COUNT = 30
        subflow_fwd_bytes = float(sum([p for p in fwd_lens[:SUBFLOW_PKT_COUNT]]))
        subflow_bwd_bytes = float(sum([p for p in bwd_lens[:SUBFLOW_PKT_COUNT]]))

        init_win_fwd = float(fwd_windows[0]) if fwd_windows else 0.0
        init_win_bwd = float(bwd_windows[0]) if bwd_windows else 0.0

        act_data_pkt_fwd = float(sum(1 for v in fwd_payloads if v > 0))
        min_seg_forward = float(min([v for v in fwd_payloads if v > 0]) if any(v > 0 for v in fwd_payloads) else 0.0)

        # Active / Idle segments
        timestamps = pkt_times
        active_segments = []
        idle_segments = []
        if len(timestamps) >= 2:
            seg_start = timestamps[0]
            prev = timestamps[0]
            for t in timestamps[1:]:
                gap = t - prev
                if gap <= self.active_gap:
                    prev = t
                    continue
                else:
                    active_segments.append(prev - seg_start)
                    idle_segments.append(gap)
                    seg_start = t
                    prev = t
            active_segments.append(prev - seg_start)
        else:
            active_segments = []
            idle_segments = []

        act_mean = float(np.mean(active_segments)) if active_segments else 0.0
        act_std = float(np.std(active_segments, ddof=0)) if active_segments else 0.0
        act_max = float(np.max(active_segments)) if active_segments else 0.0
        act_min = float(np.min(active_segments)) if active_segments else 0.0
        idle_std = float(np.std(idle_segments, ddof=0)) if idle_segments else 0.0

        _forward_dst_port = next(
            (int(p.get("dst_port", 0)) for p in packets
            if p.get("src_ip") == f_ip and p.get("src_port") == f_port),
            int(packets[-1].get("dst_port", 0))
            )
        # Compose a mapping for every named feature
        feature_map = {
            "Destination Port": float(_forward_dst_port),
            "Flow Duration": float(flow_duration),
            "Fwd Packet Length Max": float(fwd_pkt_len_max),
            "Fwd Packet Length Min": float(fwd_pkt_len_min),
            "Fwd Packet Length Std": float(fwd_pkt_len_std),
            "Bwd Packet Length Max": float(bwd_pkt_len_max),
            "Bwd Packet Length Min": float(bwd_pkt_len_min),
            "Flow Bytes/s": float(bps),
            "Flow Packets/s": float(pps),
            "Flow IAT Mean": float(flow_iat_mean),
            "Flow IAT Std": float(flow_iat_std),
            "Flow IAT Min": float(flow_iat_min),
            "Fwd IAT Mean": float(fwd_iat_mean),
            "Fwd IAT Std": float(fwd_iat_std),
            "Fwd IAT Max": float(fwd_iat_max),
            "Fwd IAT Min": float(fwd_iat_min),
            "Bwd IAT Total": float(bwd_iat_mean * len(bwd_ts) if bwd_ts else 0.0),
            "Bwd IAT Mean": float(bwd_iat_mean),
            "Bwd IAT Std": float(bwd_iat_std),
            "Bwd IAT Max": float(bwd_iat_max),
            "Bwd IAT Min": float(bwd_iat_min),
            "Bwd Packets/s": float((len(bwd_lens) / flow_duration_safe) if flow_duration_safe > 0 else 0.0),
            "Min Packet Length": float(min_pkt_len),
            "Max Packet Length": float(max_pkt_len),
            "Packet Length Variance": float(pkt_len_var),
            "FIN Flag Count": float(flags_counts.get("F", 0)),
            "SYN Flag Count": float(flags_counts.get("S", 0)),
            "PSH Flag Count": float(flags_counts.get("P", 0)),
            "ACK Flag Count": float(flags_counts.get("A", 0)),
            "URG Flag Count": float(flags_counts.get("U", 0)),
            "Down/Up Ratio": float(down_up_ratio),
            "Average Packet Size": float(avg_pkt_size),
            "Avg Fwd Segment Size": float(avg_fwd_segment),
            "Avg Bwd Segment Size": float(avg_bwd_segment),
            "Subflow Fwd Bytes": float(subflow_fwd_bytes),
            "Subflow Bwd Bytes": float(subflow_bwd_bytes),
            "Init_Win_bytes_forward": float(init_win_fwd),
            "Init_Win_bytes_backward": float(init_win_bwd),
            "act_data_pkt_fwd": float(act_data_pkt_fwd),
            "min_seg_size_forward": float(min_seg_forward),
            "Active Mean": float(act_mean),
            "Active Std": float(act_std),
            "Active Max": float(act_max),
            "Active Min": float(act_min),
            "Idle Std": float(idle_std)
        }

        # Build feature vector in canonical order and clamp values
        features = []
        for name in FEATURE_ORDER:
            val = feature_map.get(name, 0.0)
            features.append(clamp_value(val))

        # Safety: ensure exact length 45
        if len(features) != 45:
            logger.error("Feature vector length mismatch: expected 45 got %d. Padding/truncating.", len(features))
            if len(features) < 45:
                features += [0.0] * (45 - len(features))
            else:
                features = features[:45]

        # final numeric sanitization
        features = [float(0.0) if (not np.isfinite(v)) else float(v) for v in features]
        return features