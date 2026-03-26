"""
Alerts package

Provides intrusion detection alert processing, logging, and notification utilities.
This module exposes the main entrypoints used by the API and monitoring layers.
"""

from .alert_engine import process_prediction, process_prediction_sync
from .event_logger import EventLogger
from .notifier import NotificationWorker
from .schemas import PredictionPayload, FlowMeta, AlertEvent

__all__ = [
    "process_prediction",
    "process_prediction_sync",
    "EventLogger",
    "NotificationWorker",
    "PredictionPayload",
    "FlowMeta",
    "AlertEvent",
]
