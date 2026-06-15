# alerts/notifier.py

import json
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

from . import config
from .event_logger import EventLogger
from .notifier_telegram import send_telegram_notification

try:
    import requests
except Exception:
    requests = None


class NotificationWorker:

    def __init__(
        self,
        max_workers: int = config.NOTIFY_WORKER_THREADS,
        max_queue: int = config.NOTIFY_QUEUE_MAXSIZE,
    ):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.q = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._drain_queue_loop,
            daemon=True
        )
        self._worker_thread.start()
        self._logger = EventLogger()

    def submit(self, event: Dict[str, Any]) -> bool:
        try:
            self.q.put_nowait(event)
            return True
        except queue.Full:
            try:
                self._logger.persist_failed_notification_db(event)
            except Exception:
                pass
            return False

    def _drain_queue_loop(self):
        while not self._stop.is_set():
            try:
                event = self.q.get(timeout=0.5)
            except queue.Empty:
                continue

            self.executor.submit(self._send_with_retries, event)
            self.q.task_done()

    def shutdown(self, wait: bool = True):
        self._stop.set()
        if wait:
            self._worker_thread.join(timeout=2.0)
            self.executor.shutdown(wait=True)

    def _send_with_retries(self, event: Dict[str, Any]) -> bool:
        ok_overall = True

        # Console always best-effort
        if config.NOTIFY_CONSOLE:
            try:
                self._send_console(event)
            except Exception:
                ok_overall = False

        # Webhook
        if config.NOTIFY_WEBHOOK_URL:
            ok = self._try_webhook(event)
            ok_overall = ok_overall and ok

        # Twilio optional
        if config.NOTIFY_TWILIO_ENABLED:
            ok = self._try_twilio(event)
            ok_overall = ok_overall and ok

        # Telegram: medium / high / critical only, with cooldown
        ok = self._try_telegram(event)
        ok_overall = ok_overall and ok

        if not ok_overall:
            try:
                self._logger.persist_failed_notification_db(event)
            except Exception:
                pass

        return ok_overall

    def _send_console(self, event: Dict[str, Any]):
        try:
            print(
                f"[ALERT] {event.get('attack_type') or event.get('label')} "
                f"{event.get('src_ip')} -> {event.get('dst_ip')} "
                f"conf={float(event.get('confidence') or 0.0):.3f} "
                f"sev={event.get('severity')}"
            )
        except Exception:
            print("[ALERT] (malformed event)")

    def _try_webhook(self, event: Dict[str, Any]) -> bool:
        if not requests:
            return False

        payload = self.format_for_webhook(event)
        headers = {"Content-Type": "application/json"}
        backoff = config.NOTIFY_BACKOFF_BASE

        for attempt in range(config.NOTIFY_RETRIES):
            try:
                resp = requests.post(
                    config.NOTIFY_WEBHOOK_URL,
                    json=payload,
                    headers=headers,
                    timeout=5,
                )
                if 200 <= resp.status_code < 300:
                    return True
            except Exception:
                pass
            time.sleep(backoff * (2 ** attempt))

        return False

    def _try_twilio(self, event: Dict[str, Any]) -> bool:
        if not requests:
            return False

        sid = config.TWILIO_ACCOUNT_SID
        token = config.TWILIO_AUTH_TOKEN
        fromn = config.TWILIO_FROM_NUMBER
        ton = config.TWILIO_TO_NUMBER

        if not (sid and token and fromn and ton):
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        body = {
            "From": fromn,
            "To": ton,
            "Body": (
                f"ALERT {event.get('attack_type') or event.get('label')} "
                f"from {event.get('src_ip')} to {event.get('dst_ip')} "
                f"conf={float(event.get('confidence') or 0.0):.2f} "
                f"sev={event.get('severity')}"
            ),
        }

        backoff = config.NOTIFY_BACKOFF_BASE
        for attempt in range(config.NOTIFY_RETRIES):
            try:
                resp = requests.post(url, data=body, auth=(sid, token), timeout=5)
                if 200 <= resp.status_code < 300:
                    return True
            except Exception:
                pass
            time.sleep(backoff * (2 ** attempt))

        return False

    def _try_telegram(self, event: Dict[str, Any]) -> bool:
        try:
            return send_telegram_notification(event)
        except Exception:
            return False

    def format_for_webhook(self, event: Dict[str, Any]) -> Dict[str, Any]:
        text = (
            f"ALERT: {event.get('attack_type') or event.get('label')} "
            f"from {event.get('src_ip')} to {event.get('dst_ip')} "
            f"(conf={float(event.get('confidence') or 0.0):.3f}, "
            f"sev={event.get('severity')})"
        )
        return {
            "text": text,
            "event": event,
        }