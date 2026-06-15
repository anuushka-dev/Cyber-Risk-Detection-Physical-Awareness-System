# monitoring/config.py
from pathlib import Path
import os

# Capture
INTERFACE = os.getenv(
    "MONITOR_IFACE",
    "Wi-Fi"
)  # change to eth0 / en0 / Wi-Fi as needed
PROMISCUOUS = os.getenv("MONITOR_PROMISC", "true").lower() == "true"

# Flow lifecycle
FLOW_IDLE_TIMEOUT = float(os.getenv("FLOW_IDLE_TIMEOUT", "60.0"))
FLOW_MAX_PACKETS = int(os.getenv("FLOW_MAX_PACKETS", "10000"))
ACTIVE_GAP_THRESHOLD = float(os.getenv("ACTIVE_GAP_THRESHOLD", "1.0"))

# API / sending
API_URL = os.getenv("IDS_API_URL", "http://127.0.0.1:8000/predict")
BATCH_API_URL = os.getenv("IDS_BATCH_API_URL", "http://127.0.0.1:8000/predict/batch")
API_TIMEOUT = float(os.getenv("IDS_API_TIMEOUT", "5.0"))
API_RETRIES = int(os.getenv("IDS_API_RETRIES", "3"))
API_BACKOFF = float(os.getenv("IDS_API_BACKOFF", "0.5"))
BATCH_SIZE = int(os.getenv("IDS_BATCH_SIZE", "16"))

# Real-only mode
SIMULATE = os.getenv("SIMULATE_MONITOR", "false").lower() == "true"

# Logging
CLEANUP_INTERVAL = float(os.getenv("CLEANUP_INTERVAL", "5.0"))
LOG_DIR = Path(os.getenv("MONITOR_LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
ATTACK_LOG = LOG_DIR / "attack_logs.jsonl"
FLOW_LOG = LOG_DIR / "flow_logs.jsonl"
PACKET_LOG = LOG_DIR / "packet_logs.jsonl"

# Limits
MAX_MEMORY_FLOWS = int(os.getenv("MAX_MEMORY_FLOWS", "20000"))
SEND_QUEUE_MAXSIZE = int(os.getenv("SEND_QUEUE_MAXSIZE", "1024"))
SEND_QUEUE_PERSIST_DIR = Path(os.getenv("SEND_QUEUE_PERSIST_DIR", "queue_persist"))
SEND_QUEUE_PERSIST_DIR.mkdir(parents=True, exist_ok=True)

# Numeric safety
VALUE_CLAMP_MIN = float(os.getenv("VALUE_CLAMP_MIN", "-1e12"))
VALUE_CLAMP_MAX = float(os.getenv("VALUE_CLAMP_MAX", "1e12"))
EPSILON = float(os.getenv("NUMERIC_EPSILON", "1e-9"))