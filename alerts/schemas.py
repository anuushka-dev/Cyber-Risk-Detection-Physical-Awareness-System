# alerts/schemas.py
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

class FlowMeta(BaseModel):
    src_ip: str
    dst_ip: str
    src_port: Optional[int] = None
    dst_port: Optional[int] = None
    protocol: Optional[str] = None
    flow_id: Optional[str] = None
    timestamp: Optional[float] = None  # epoch seconds

    @validator("flow_id", pre=True, always=True)
    def ensure_flow_id(cls, v):
        return v or uuid.uuid4().hex

    @validator("timestamp", pre=True, always=True)
    def ensure_timestamp(cls, v):
        import time
        return float(v) if v else time.time()

class PredictionPayload(BaseModel):
    label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    probabilities: Optional[Dict[str, float]] = None

class AlertEvent(BaseModel):
    event_id: str
    created_at: float
    human_time: str
    src_ip: str
    dst_ip: str
    src_port: Optional[int]
    dst_port: Optional[int]
    protocol: Optional[str]
    flow_id: str
    attack_type: str
    confidence: float
    severity: str
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def from_prediction(cls, pred: PredictionPayload, meta: FlowMeta, severity: str, extra: Optional[Dict[str, Any]] = None):
        import time, datetime as _dt, uuid
        now = time.time()
        human_time = _dt.datetime.utcfromtimestamp(now).isoformat() + "Z"
        return cls(
            event_id = uuid.uuid4().hex,
            created_at = now,
            human_time = human_time,
            src_ip = meta.src_ip,
            dst_ip = meta.dst_ip,
            src_port = meta.src_port,
            dst_port = meta.dst_port,
            protocol = meta.protocol,
            flow_id = meta.flow_id,
            attack_type = pred.label,
            confidence = float(pred.confidence),
            severity = severity,
            metadata = extra or {}
        )