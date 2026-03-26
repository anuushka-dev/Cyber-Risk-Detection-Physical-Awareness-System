# alerts/event_logger.py  (OVERWRITE this file with the content below)

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Local imports (expects alerts/config.py to define sensible defaults)
from . import config
# keep import of AlertEvent if you want type-checking, but do not require it at runtime
try:
    from .schemas import AlertEvent  # type: ignore
except Exception:
    AlertEvent = None  # pragma: no cover

# Schema used to initialise DB; kept small and stable for tests and production use.
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS failed_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS deduper_state (
    key TEXT PRIMARY KEY,
    count INTEGER NOT NULL,
    last_seen REAL NOT NULL
);
"""


class EventLogger:
    """
    Lightweight JSONL + SQLite event logger used by the alerts subsystem.

    Constructor is intentionally forgiving for test compatibility:
      - jsonl_path: path to JSONL file (preferred)
      - db_path: path to sqlite DB file for persisted notifications
      - log_file: legacy alias for jsonl_path (tests use this)
    """

    def __init__(self, jsonl_path: Optional[str] = None, db_path: Optional[str] = None, *, log_file: Optional[str] = None):
        # Backwards compatibility: accept log_file as alias
        if jsonl_path is None and log_file is not None:
            jsonl_path = log_file

        # Resolve paths using config defaults if not provided
        self.jsonl_path: Path = Path(jsonl_path) if jsonl_path else Path(getattr(config, "EVENTS_FILE", "logs/events.jsonl"))
        self.db_path: Path = Path(db_path) if db_path else Path(getattr(config, "DB_PATH", "alerts/alerts.db"))

        # Ensure directories exist
        try:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            # best-effort: ignore permission issues here; file writes will raise later
            pass

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        # Ensure DB schema exists
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Ensure sqlite DB exists with expected tables (idempotent)."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.executescript(DB_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def append(self, event: Dict[str, Any]) -> None:
        """
        Append an event to the JSONL file. Accepts:
          - pydantic model (has .dict())
          - plain dict
        Writes atomically with flush + fsync when possible.
        """
        # Normalize pydantic / dataclass objects
        try:
            if hasattr(event, "dict") and callable(getattr(event, "dict")):
                payload = event.dict()
            else:
                payload = event
            text = json.dumps(payload, ensure_ascii=False)
        except Exception:
            # Last resort: try to dump something sensible
            try:
                text = json.dumps(dict(event), ensure_ascii=False)
            except Exception:
                text = json.dumps({"error": "unserializable_event"}, ensure_ascii=False)

        # Atomic append (best-effort)
        try:
            with open(self.jsonl_path, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except Exception:
                    # fsync can fail on some platforms/permissions; ignore but keep flush
                    pass
        except Exception:
            # If writing fails, persist the event into sqlite failed_notifications as fallback
            try:
                self.persist_failed_notification(payload if isinstance(payload, dict) else {"payload": str(payload)})
            except Exception:
                # swallow to avoid raising during logging step; real system would surface this
                pass

    def persist_failed_notification(self, payload: Dict[str, Any]) -> None:
        """
        Persist a failed outgoing notification into sqlite for later retry.
        Payload is stored as JSON text.
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO failed_notifications (created_at, payload, attempts) VALUES (?, ?, 0)",
                (time.time(), json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    def fetch_failed_notifications(self, limit: int = 100) -> List[Tuple[int, float, str, int]]:
        """
        Fetch up to `limit` failed notifications as rows:
        (id, created_at, payload_text, attempts)
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, created_at, payload, attempts FROM failed_notifications ORDER BY id LIMIT ?", (limit,))
            rows = cur.fetchall()
            return rows
        finally:
            conn.close()

    def remove_failed_notification(self, notif_id: int) -> None:
        """Remove a persisted notification after successful delivery."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM failed_notifications WHERE id = ?", (notif_id,))
            conn.commit()
        finally:
            conn.close()

    def increment_attempts(self, notif_id: int) -> None:
        """Increment attempts counter for a persisted notification."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("UPDATE failed_notifications SET attempts = attempts + 1 WHERE id = ?", (notif_id,))
            conn.commit()
        finally:
            conn.close()