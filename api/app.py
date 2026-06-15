import inspect
import json
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import HOST, MAX_BATCH_SIZE, PROJECT_ROOT
from .logging_config import logger
from .model_loader import load_artifacts
from .predictor import predict_batch, predict_one
from .schemas import (
    BatchPredictResponse,
    HealthResponse,
    ModelInfoResponse,
    PredictResponse,
)
from alerts.alert_engine import process_prediction

try:
    from monitoring.human_context import (
        get_human_context,
        get_latest_frame,
        start_human_context,
        stop_human_context,
    )
except Exception:
    get_human_context = None
    get_latest_frame = None
    start_human_context = None
    stop_human_context = None

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

app = FastAPI(title="AI Intrusion Detection System API", version="1.0")
START_TIME = time.time()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL = None
FEATURE_LIST: List[str] = []
LABEL_ENCODER = None

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
EVENTS_LOG_PATH = LOG_DIR / "events.jsonl"
ATTACK_LOG_PATH = LOG_DIR / "attack_logs.jsonl"
DEVICE_SNAPSHOT_PATH = LOG_DIR / "device_snapshot.jsonl"
PACKET_LOG_PATH = LOG_DIR / "packet_logs.jsonl"


def _trim_jsonl(path: Path, max_lines: int = 1500, keep_lines: int = 1200) -> None:
    try:
        if not path.exists():
            return

        with open(path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            if len(lines) <= max_lines:
                return
            f.seek(0)
            f.writelines(lines[-keep_lines:])
            f.truncate()
    except Exception:
        logger.exception("Failed trimming JSONL", extra={"path": str(path)})


def _jsonl_append(path: Path, record: Dict[str, Any]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        _trim_jsonl(path)
    except Exception:
        logger.exception("log write failed", extra={"path": str(path)})


def _read_jsonl_tail(path: Path, limit: int = 100) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    try:
        out: deque = deque(maxlen=limit)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    out.append({"raw": line})
        return list(out)
    except Exception:
        logger.exception("Failed reading JSONL file", extra={"path": str(path)})
        return []


def _normalize_result_obj(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        return {
            "label": result.get("label"),
            "confidence": result.get("confidence"),
            "probabilities": result.get("probabilities", {}),
        }

    if hasattr(result, "model_dump"):
        d = result.model_dump()
        return {
            "label": d.get("label"),
            "confidence": d.get("confidence"),
            "probabilities": d.get("probabilities", {}),
        }

    if hasattr(result, "dict"):
        d = result.dict()
        return {
            "label": d.get("label"),
            "confidence": d.get("confidence"),
            "probabilities": d.get("probabilities", {}),
        }

    return {
        "label": getattr(result, "label", None),
        "confidence": getattr(result, "confidence", None),
        "probabilities": getattr(result, "probabilities", {}),
    }


def _infer_severity(label: str, confidence: float) -> str:
    label_u = str(label or "").upper()
    if label_u == "BENIGN":
        return "low"
    if confidence >= 0.95:
        return "high"
    if confidence >= 0.85:
        return "mid"
    return "low"


def _is_benign_label(label: Any) -> bool:
    return "BENIGN" in str(label or "").upper()


def _coerce_flow_meta(flow_meta: Any, request: Request, request_id: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = flow_meta if isinstance(flow_meta, dict) else {}
    meta = dict(meta)

    if request.client and "api_client_ip" not in meta:
        meta["api_client_ip"] = request.client.host

    meta.setdefault("flow_id", request_id)
    meta.setdefault("timestamp", time.time())
    meta.setdefault("protocol", meta.get("protocol", "TCP"))

    src_ip = meta.get("src_ip") or meta.get("source_ip") or meta.get("ip_src")
    dst_ip = meta.get("dst_ip") or meta.get("dest_ip") or meta.get("ip_dst")
    src_mac = meta.get("src_mac") or meta.get("source_mac")
    dst_mac = meta.get("dst_mac") or meta.get("dest_mac")

    # Required by alerts.schemas.FlowMeta
    meta["src_ip"] = src_ip or "0.0.0.0"
    meta["dst_ip"] = dst_ip or "0.0.0.0"

    # Backward compatibility for frontend / logs
    meta["source_ip"] = meta["src_ip"]
    meta["dest_ip"] = meta["dst_ip"]

    if src_mac is not None:
        meta["src_mac"] = src_mac
        meta["source_mac"] = src_mac

    if dst_mac is not None:
        meta["dst_mac"] = dst_mac
        meta["dest_mac"] = dst_mac

    return meta


def _store_prediction_event(
    *,
    request_id: str,
    result: Any,
    flow_meta: Dict[str, Any],
    origin: str,
) -> Dict[str, Any]:
    normalized = _normalize_result_obj(result)
    label = normalized["label"]
    confidence = float(normalized["confidence"] or 0.0)
    severity = _infer_severity(label, confidence)

    record = {
        "timestamp": flow_meta.get("timestamp", time.time()),
        "request_id": request_id,
        "origin": origin,
        "label": label,
        "confidence": confidence,
        "severity": severity,
        "probabilities": normalized["probabilities"],
        "source_ip": flow_meta.get("source_ip") or flow_meta.get("src_ip"),
        "dest_ip": flow_meta.get("dest_ip") or flow_meta.get("dst_ip"),
        "source_mac": flow_meta.get("source_mac") or flow_meta.get("src_mac"),
        "dest_mac": flow_meta.get("dest_mac") or flow_meta.get("dst_mac"),
        "protocol": flow_meta.get("protocol"),
        "ip_version": flow_meta.get("ip_version"),
        "packet_count": flow_meta.get("packet_count"),
        "bandwidth": flow_meta.get("bandwidth"),
        "src_host": flow_meta.get("src_host"),
        "dst_host": flow_meta.get("dst_host"),
        "flow_meta": flow_meta,
    }

    _jsonl_append(EVENTS_LOG_PATH, record)

    if not _is_benign_label(record["label"]):
        _jsonl_append(ATTACK_LOG_PATH, record)

    return record


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _dispatch_alert_if_needed(
    *,
    result: Any,
    flow_meta: Dict[str, Any],
    request_id: str,
    origin: str,
) -> None:
    normalized = _normalize_result_obj(result)
    label = normalized["label"]

    if _is_benign_label(label):
        return

    alert_payload = {
        "label": normalized["label"],
        "confidence": normalized["confidence"],
        "probabilities": normalized["probabilities"],
    }

    try:
        maybe = process_prediction(
            alert_payload,
            flow_meta,
            extra_metadata={"origin": origin},
            notify_async=True,
        )
        await _maybe_await(maybe)
    except Exception:
        logger.exception(
            "Alert processing failed",
            extra={"request_id": request_id, "label": normalized["label"]},
        )


@app.on_event("startup")
def startup_event():
    global MODEL, FEATURE_LIST, LABEL_ENCODER
    logger.info("Starting API, loading artifacts", extra={"project_root": str(PROJECT_ROOT)})
    try:
        MODEL, FEATURE_LIST, LABEL_ENCODER = load_artifacts()
        logger.info(
            "Loaded artifacts",
            extra={
                "model_path": str(PROJECT_ROOT / "models" / "intrusion_model.joblib"),
                "n_features": len(FEATURE_LIST),
                "n_classes": len(LABEL_ENCODER.classes_) if LABEL_ENCODER is not None else 0,
            },
        )
        if start_human_context is not None:
            start_human_context()
    except Exception as e:
        logger.critical("Failed to load artifacts at startup", exc_info=e)
        raise


@app.on_event("shutdown")
def shutdown_event():
    logger.info("Shutting down API")
    if stop_human_context is not None:
        stop_human_context()


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = uuid.uuid4().hex
    start = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_seconds": round(duration, 4),
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        duration = time.time() - start
        logger.exception(
            "Request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_seconds": round(duration, 4),
            },
        )
        raise


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "AI Intrusion Detection System API",
        "uptime_seconds": int(time.time() - START_TIME),
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok" if MODEL is not None else "error",
        model_loaded=MODEL is not None,
        uptime_seconds=int(time.time() - START_TIME),
    )


@app.get("/human-context")
async def human_context():
    if get_human_context is None:
        return {"enabled": False, "context": None, "image": None}
    payload = get_human_context()
    payload["image"] = get_latest_frame() if get_latest_frame is not None else None
    return payload


@app.get("/camera-frame")
def camera_frame():
    if get_latest_frame is None:
        return {"image": None}
    return {"image": get_latest_frame()}


@app.get("/model-info", response_model=ModelInfoResponse)
async def model_info():
    if MODEL is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded",
        )

    return ModelInfoResponse(
        features=FEATURE_LIST,
        classes=LABEL_ENCODER.classes_.tolist(),
        feature_count=len(FEATURE_LIST),
    )


@app.get("/events")
async def get_events(limit: int = 100):
    return _read_jsonl_tail(EVENTS_LOG_PATH, limit=max(1, min(limit, 500)))


@app.get("/recent-events")
async def get_recent_events(limit: int = 100):
    return _read_jsonl_tail(EVENTS_LOG_PATH, limit=max(1, min(limit, 500)))


@app.get("/logs")
async def get_logs(limit: int = 100):
    return _read_jsonl_tail(ATTACK_LOG_PATH, limit=max(1, min(limit, 500)))


@app.post("/demo/attack")
async def demo_attack():
    import random

    recent = _read_jsonl_tail(EVENTS_LOG_PATH, limit=5)

    if recent:
        base = recent[-1]
        src_ip = base.get("source_ip") or base.get("src_ip") or "192.168.5.96"
        dst_ip = base.get("dest_ip") or base.get("dst_ip") or "142.250.182.14"
        src_mac = base.get("source_mac") or base.get("src_mac") or "4c:23:38:93:6b:ad"
        dst_mac = base.get("dest_mac") or base.get("dst_mac") or "e8:65:d4:72:69:40"
    else:
        src_ip = "192.168.5.96"
        dst_ip = "142.250.182.14"
        src_mac = "4c:23:38:93:6b:ad"
        dst_mac = "e8:65:d4:72:69:40"

    attack_profiles = [
        ("DDoS", 5_000_000, 150),
        ("DoS Hulk", 3_000_000, 120),
        ("PortScan", 800_000, 60),
        ("Bot", 1_500_000, 90),
    ]

    label, bps, packets = random.choice(attack_profiles)

    fake_result = {
        "label": label,
        "confidence": round(random.uniform(0.93, 0.99), 4),
        "probabilities": {label: 0.95},
    }

    fake_flow = {
        "timestamp": time.time(),
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "source_ip": src_ip,
        "dest_ip": dst_ip,
        "src_mac": src_mac,
        "dst_mac": dst_mac,
        "source_mac": src_mac,
        "dest_mac": dst_mac,
        "protocol": "TCP",
        "packet_count": packets,
        "bandwidth": {"bps": bps},
    }

    record = _store_prediction_event(
        request_id=uuid.uuid4().hex,
        result=fake_result,
        flow_meta=fake_flow,
        origin="demo.attack",
    )

    await _dispatch_alert_if_needed(
        result=fake_result,
        flow_meta=fake_flow,
        request_id=record["request_id"],
        origin="demo.attack",
    )

    return {"status": "attack injected", "event": record}


@app.get("/devices")
async def get_devices(limit: int = 1):
    snaps = _read_jsonl_tail(DEVICE_SNAPSHOT_PATH, limit=max(1, min(limit, 5)))
    if not snaps:
        return {"timestamp": time.time(), "devices": []}
    return snaps[-1]


@app.get("/packets")
async def get_packets(limit: int = 100):
    return _read_jsonl_tail(PACKET_LOG_PATH, limit=max(1, min(limit, 500)))


@app.post("/predict", response_model=PredictResponse)
async def predict(body: Dict[str, Any], request: Request):
    if MODEL is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded",
        )

    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    features = body.get("features")
    flow_meta = _coerce_flow_meta(body.get("flow_meta"), request, request_id)

    if features is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing 'features' in request body",
        )

    try:
        result = predict_one(MODEL, LABEL_ENCODER, FEATURE_LIST, features)

        _store_prediction_event(
            request_id=request_id,
            result=result,
            flow_meta=flow_meta,
            origin="api.predict",
        )

        await _dispatch_alert_if_needed(
            result=result,
            flow_meta=flow_meta,
            request_id=request_id,
            origin="api.predict",
        )

        logger.info(
            "Prediction successful",
            extra={
                "request_id": request_id,
                "label": getattr(result, "label", None),
                "confidence": getattr(result, "confidence", None),
            },
        )

        return PredictResponse(result=result, request_id=request_id)

    except ValueError as e:
        logger.warning(
            "Validation or low-confidence",
            extra={"error": str(e), "request_id": request_id},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Prediction error", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch_endpoint(body: Dict[str, Any], request: Request):
    if MODEL is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded",
        )

    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    instances = body.get("instances")
    flow_meta_body = body.get("flow_meta")

    if not isinstance(instances, list) or not instances:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing 'instances' list in request body",
        )

    if len(instances) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch size {len(instances)} exceeds limit {MAX_BATCH_SIZE}",
        )

    if isinstance(flow_meta_body, list):
        flow_metas = [
            _coerce_flow_meta(m, request, f"{request_id}-{idx}")
            for idx, m in enumerate(flow_meta_body)
        ]
        if len(flow_metas) != len(instances):
            flow_metas = [
                _coerce_flow_meta({}, request, f"{request_id}-{idx}")
                for idx in range(len(instances))
            ]
    else:
        shared_meta = _coerce_flow_meta(flow_meta_body, request, request_id)
        flow_metas = [dict(shared_meta) for _ in range(len(instances))]

    try:
        results = predict_batch(MODEL, LABEL_ENCODER, FEATURE_LIST, instances)

        for idx, result in enumerate(results):
            _store_prediction_event(
                request_id=f"{request_id}-{idx}",
                result=result,
                flow_meta=flow_metas[idx],
                origin="api.predict_batch",
            )

            await _dispatch_alert_if_needed(
                result=result,
                flow_meta=flow_metas[idx],
                request_id=f"{request_id}-{idx}",
                origin="api.predict_batch",
            )

        logger.info(
            "Batch prediction successful",
            extra={"request_id": request_id, "batch_size": len(results)},
        )
        return BatchPredictResponse(results=results, request_id=request_id)

    except ValueError as e:
        logger.warning(
            "Batch validation error",
            extra={"error": str(e), "request_id": request_id},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception:
        logger.exception("Batch prediction error", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", extra={"path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.app:app", host=HOST, port=PORT, reload=True)
