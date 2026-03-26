# alerts/alert_engine.py

import logging
from pydantic import ValidationError

from .schemas import PredictionPayload, FlowMeta, AlertEvent
from .event_logger import EventLogger
from .notifier import NotificationWorker
from . import config
from monitoring.human_context import get_human_context
from alerts.context_fusion import attack_base_severity, fuse_severity_with_humans

logger = logging.getLogger("alerts.engine")
logger.setLevel(logging.INFO)

# validate configuration early
try:
    config.validate_config()
except Exception:
    raise

# singletons
_event_logger = EventLogger()
_notifier_worker = NotificationWorker(
    max_workers=config.NOTIFY_WORKER_THREADS,
    max_queue=config.NOTIFY_QUEUE_MAXSIZE,
)


def _label_to_severity(label: str) -> str:
    sev = config.LABEL_SEVERITY_MAP.get(label)
    if sev:
        return sev

    l = (label or "").lower()
    if "ddos" in l or "dos" in l or "attack" in l or "bot" in l:
        return "high"
    return "medium"


def _should_notify(sev: str) -> bool:
    sev_key = str(sev or "").strip().lower()
    return config.SEVERITY_LEVELS.get(sev_key, 0) >= config.SEVERITY_LEVELS.get(
        config.NOTIFY_SEVERITY_MIN, 20
    )


def process_prediction_sync(
    prediction: dict,
    flow_meta: dict,
    extra_metadata: dict = None,
    notify_enqueue: bool = False,
):
    pred = PredictionPayload(**prediction)
    meta = FlowMeta(**flow_meta)

    # ---------------- human + motion context ----------------
    context = get_human_context() or {}

    people_detected = int(context.get("people_detected") or 0)
    motion_score = float(context.get("motion_score") or 0.0)
    camera_ok = bool(context.get("camera_ok") or False)

    base_severity = attack_base_severity(
        pred.label,
        pred.confidence,
    )

    final_severity, reason = fuse_severity_with_humans(
        base_severity=base_severity,
        label=pred.label,
        people_detected=people_detected,
        motion_score=motion_score,
    )

    final_severity = str(final_severity or base_severity).strip().lower()
    reason = str(reason or "").strip()

    metadata = dict(extra_metadata or {})
    metadata.update(
        {
            "people_detected": people_detected,
            "motion_score": motion_score,
            "camera_ok": camera_ok,
            "severity_reason": reason,
        }
    )

    ev = AlertEvent.from_prediction(
        pred,
        meta,
        final_severity,
        metadata,
    )

    from alerts.notifier_telegram import send_telegram_notification

    try:
        send_telegram_notification(ev.dict())
    except Exception as e:
        print("telegram direct error:", e)

    try:
        _event_logger.append(ev)
    except Exception:
        logger.exception("Failed to append event")

    if _should_notify(final_severity):
        event_dict = ev.dict()

        if notify_enqueue:
            enqueued = _notifier_worker.submit(event_dict)
            if not enqueued:
                try:
                    _event_logger.persist_failed_notification_db(event_dict)
                except Exception:
                    logger.exception("Persist failed notification failed")
        else:
            try:
                _notifier_worker._send_with_retries(event_dict)
            except Exception:
                logger.exception("Synchronous notify failed; persisting")
                try:
                    _event_logger.persist_failed_notification_db(event_dict)
                except Exception:
                    pass

    return ev


def process_prediction(
    prediction: dict,
    flow_meta: dict,
    extra_metadata: dict = None,
    notify_async: bool = True,
):
    """
    Public entrypoint: validate and persist event; notifications are enqueued for background sending.
    notify_async=True -> enqueue to bounded in-memory queue (with sqlite-persistence fallback)
    notify_async=False -> attempt synchronous send (falls back to DB persist)
    """
    try:
        return process_prediction_sync(
            prediction,
            flow_meta,
            extra_metadata,
            notify_enqueue=notify_async,
        )
    except ValidationError as e:
        logger.warning("Validation error in alert_engine: %s", e)
        raise
    except Exception:
        logger.exception("Unexpected error in alert_engine")
        raise


def retry_persisted_notifications(limit: int = 100):
    """
    Utility: attempt to resend persisted failed notifications from DB.
    """
    def handler(payload):
        try:
            return _notifier_worker._send_with_retries(payload)
        except Exception:
            return False

    _event_logger.retry_failed_notifications_from_db(handler, limit)