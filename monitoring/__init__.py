# monitoring/__init__.py
"""
Package initializer for monitoring.
Exports the core public objects so tests can import `monitoring` as a package.
"""

# Re-export config and main components for easy imports in tests:
from . import config  # monitoring.config
from .packet_capture import start_packet_capture  # function to begin capture
from .flow_builder import FlowTable, FlowRecord
from .feature_extractor import FeatureExtractor, FEATURE_ORDER
from .realtime_monitor import run_monitor, sender_loop, send_queue

# Backwards compatibility aliases (if anything expects older names)
PacketCapture = start_packet_capture

__all__ = [
    "config",
    "start_packet_capture",
    "PacketCapture",
    "FlowTable",
    "FlowRecord",
    "FeatureExtractor",
    "FEATURE_ORDER",
    "run_monitor",
    "sender_loop",
    "send_queue",
]