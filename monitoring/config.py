# monitoring/config.py
from pathlib import Path
import os

# Network / capture
INTERFACE ="Wi-Fi" 
#INTERFACE = os.getenv("MONITOR_IFACE", None)  # None -> scapy sniff default (requires privileges)
PROMISCUOUS = os.getenv("MONITOR_PROMISC", "true").lower() == "true"

# Flow lifecycle
FLOW_IDLE_TIMEOUT = float(os.getenv("FLOW_IDLE_TIMEOUT", "60.0"))  # seconds of inactivity -> close flow
FLOW_MAX_PACKETS = int(os.getenv("FLOW_MAX_PACKETS", "10000"))     # safety cap per flow

# Active/idle threshold used for "active" period segmentation (seconds)
ACTIVE_GAP_THRESHOLD = float(os.getenv("ACTIVE_GAP_THRESHOLD", "1.0"))

# API / sending
API_URL = os.getenv("IDS_API_URL", "http://127.0.0.1:8000/predict")
BATCH_API_URL = os.getenv("IDS_BATCH_API_URL", "http://127.0.0.1:8000/predict/batch")
API_TIMEOUT = float(os.getenv("IDS_API_TIMEOUT", "5.0"))  # seconds
API_RETRIES = int(os.getenv("IDS_API_RETRIES", "3"))
API_BACKOFF = float(os.getenv("IDS_API_BACKOFF", "0.5"))  # base backoff seconds
BATCH_SIZE = int(os.getenv("IDS_BATCH_SIZE", "16"))      # send multiple flows in one POST

# Operational
SIMULATE = True
#SIMULATE = os.getenv("SIMULATE_MONITOR", "false").lower() == "true"  # if true, do not capture live packets
CLEANUP_INTERVAL = float(os.getenv("CLEANUP_INTERVAL", "5.0"))  # seconds
LOG_DIR = Path(os.getenv("MONITOR_LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
ATTACK_LOG = LOG_DIR / "attack_logs.jsonl"
FLOW_LOG = LOG_DIR / "flow_logs.jsonl"

# Safety and limits
MAX_MEMORY_FLOWS = int(os.getenv("MAX_MEMORY_FLOWS", "20000"))  # max flows to keep in memory

 #Sender queue limits & persistence
SEND_QUEUE_MAXSIZE = int(os.getenv("SEND_QUEUE_MAXSIZE", "1024"))   # bounded queue size
SEND_QUEUE_PERSIST_DIR = Path(os.getenv("SEND_QUEUE_PERSIST_DIR", "queue_persist"))
SEND_QUEUE_PERSIST_DIR.mkdir(parents=True, exist_ok=True)

# Value clamping for feature extractor to avoid huge numbers (prevent Inf/Nan)
VALUE_CLAMP_MIN = float(os.getenv("VALUE_CLAMP_MIN", "-1e12"))
VALUE_CLAMP_MAX = float(os.getenv("VALUE_CLAMP_MAX", "1e12"))

# Small epsilon to avoid divide-by-zero
EPSILON = float(os.getenv("NUMERIC_EPSILON", "1e-9"))