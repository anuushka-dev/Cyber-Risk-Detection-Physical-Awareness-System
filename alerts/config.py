# alerts/config.py
from pathlib import Path
import os

# Logging / persistence
ALERT_LOG_DIR = Path(os.getenv("ALERT_LOG_DIR", "logs")).resolve()
ALERT_LOG_DIR.mkdir(parents=True, exist_ok=True)
SECURITY_LOG_FILE = ALERT_LOG_DIR / os.getenv("SECURITY_LOG_FILE", "security_events.jsonl")
SYSTEM_LOG_FILE = ALERT_LOG_DIR / os.getenv("SYSTEM_LOG_FILE", "system_events.log")

# SQLite-backed persistent queue (recommended)
USE_SQLITE = os.getenv("ALERT_USE_SQLITE", "true").lower() == "true"
SQLITE_DB_PATH = ALERT_LOG_DIR / os.getenv("ALERT_SQLITE_DB", "alerts.db")

# Notification settings
NOTIFY_CONSOLE = os.getenv("ALERT_NOTIFY_CONSOLE", "true").lower() == "true"
NOTIFY_WEBHOOK_URL = os.getenv("ALERT_NOTIFY_WEBHOOK_URL")  # e.g. Slack/Teams webhook
NOTIFY_TWILIO_ENABLED = os.getenv("ALERT_NOTIFY_TWILIO", "false").lower() == "true"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER")

# Delivery retries and backoff
NOTIFY_RETRIES = int(os.getenv("ALERT_NOTIFY_RETRIES", "3"))
NOTIFY_BACKOFF_BASE = float(os.getenv("ALERT_NOTIFY_BACKOFF_BASE", "0.5"))  # seconds

# Executor settings (thread pool)
NOTIFY_WORKER_THREADS = int(os.getenv("ALERT_NOTIFY_WORKER_THREADS", "4"))
NOTIFY_QUEUE_MAXSIZE = int(os.getenv("ALERT_NOTIFY_QUEUE_MAXSIZE", "1000"))

# Severity threshold to trigger notifications
NOTIFY_SEVERITY_MIN = os.getenv("ALERT_NOTIFY_SEVERITY_MIN", "medium").lower()
SEVERITY_LEVELS = {"low": 10, "medium": 20, "high": 30, "critical": 40}

# Mapping from label to severity (customize)
LABEL_SEVERITY_MAP = {
    "BENIGN": "low",
    "PortScan": "medium",
    "DDoS": "critical",
    "Bot": "high",
    "FTP-Patator": "high",
    "SSH-Patator": "high",
    "Web Attack \ufffd Brute Force": "high",
    "Web Attack \ufffd XSS": "high",
}

# Numeric guards
VALUE_CLAMP_MIN = -1e12
VALUE_CLAMP_MAX = 1e12
EPSILON = 1e-9
ACTIVE_GAP_THRESHOLD = float(os.getenv("ACTIVE_GAP_THRESHOLD", "1.0"))

def validate_config():
    """
    Ensure required settings are present when certain features enabled.
    Raises RuntimeError with an actionable message if misconfigured.
    """
    errors = []
    if NOTIFY_TWILIO_ENABLED:
        if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER and TWILIO_TO_NUMBER):
            errors.append("Twilio notification enabled but TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM/TO are not all set.")
    if NOTIFY_WEBHOOK_URL:
        if not NOTIFY_WEBHOOK_URL.startswith(("http://","https://")):
            errors.append("NOTIFY_WEBHOOK_URL must be a valid http(s) URL.")
    if USE_SQLITE:
        # attempt permission check on path
        try:
            SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            # try write access
            p = SQLITE_DB_PATH.parent / ".alerts_write_test"
            with open(p, "w") as f:
                f.write("ok")
            p.unlink()
        except Exception as e:
            errors.append(f"SQLite DB path not writable: {SQLITE_DB_PATH} ({e})")
    if errors:
        raise RuntimeError("Alert config validation failed: " + "; ".join(errors))