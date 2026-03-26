import os
import random
import threading
import inspect
import json
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import HOST, PORT, MAX_BATCH_SIZE, PROJECT_ROOT
from .logging_config import logger
from .model_loader import load_artifacts
from .predictor import predict_one, predict_batch
from monitoring.human_context import (
    start_human_context,
    stop_human_context,
    get_human_context,
    get_latest_frame,
)


from .schemas import (
    PredictRequest,
    BatchPredictRequest,
    PredictResponse,
    BatchPredictResponse,
    HealthResponse,
    ModelInfoResponse,
)
from alerts.alert_engine import process_prediction
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = FastAPI(title="AI Intrusion Detection System API", version="1.0")
START_TIME = time.time()

# CORS for React / Streamlit / local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global placeholders populated at startup
MODEL = None
FEATURE_LIST: List[str] = []
LABEL_ENCODER = None

# Log files for frontend + observability
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
EVENTS_LOG_PATH = LOG_DIR / "events.jsonl"
ATTACK_LOG_PATH = LOG_DIR / "attack_logs.jsonl"

# Demo controls
DEMO_AUTO_ATTACK = os.getenv("DEMO_AUTO_ATTACK", "true").lower() == "true"
DEMO_ATTACK_INTERVAL = float(os.getenv("DEMO_ATTACK_INTERVAL", "18"))
DEMO_THREAD: Optional[threading.Thread] = None
DEMO_STOP_EVENT: Optional[threading.Event] = None


# ---------------- helpers ----------------
def _jsonl_append(path: Path, record: Dict[str, Any]):

    MAX_LINES = 1500   # keeps dashboard fast
    TRIM_TO = 1200     # shrink when overflow

    try:

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        # only check size occasionally (faster)
        if random.random() < 0.02:

            with open(path, "r+", encoding="utf-8") as f:

                lines = f.readlines()

                if len(lines) > MAX_LINES:

                    f.seek(0)
                    f.writelines(lines[-TRIM_TO:])
                    f.truncate()

    except Exception:

        logger.exception("log write failed")

"""
def _jsonl_append(path: Path, record: Dict[str, Any]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed writing JSONL record", extra={"path": str(path)})
"""

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
    """
    Accepts a Pydantic model, dataclass-like object, or plain dict.
    """
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
        "timestamp": time.time(),
        "request_id": request_id,
        "origin": origin,
        "label": label,
        "confidence": confidence,
        "severity": severity,
        "probabilities": normalized["probabilities"],
        "flow_meta": flow_meta,
    }

    # Full event stream for dashboard
    _jsonl_append(EVENTS_LOG_PATH, record)

    # Attack-only log
    if str(record["label"]).upper() != "BENIGN":
        _jsonl_append(ATTACK_LOG_PATH, record)

    return record


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _demo_attack_profile():
    """
    Returns: severity, label, confidence, burst_size
    """
    roll = random.random()

    if roll < 0.55:
        return "low", "PortScan", 0.88, 3
    elif roll < 0.85:
        return "mid", "DoS Slowhttptest", 0.93, 5
    else:
        return "high", "DoS Hulk", 0.98, 9


def _inject_demo_attack(severity: Optional[str] = None, origin: str = "demo.auto") -> Dict[str, Any]:
    sev = str(severity or "").strip().lower()

    if sev not in {"low", "mid", "high"}:
        sev, label, confidence, burst = _demo_attack_profile()
    else:
        if sev == "low":
            label, confidence, burst = "PortScan", 0.88, 3
        elif sev == "mid":
            label, confidence, burst = "DoS Slowhttptest", 0.93, 5
        else:
            label, confidence, burst = "DoS Hulk", 0.98, 9

    base_ts = time.time()
    request_id = f"demo-{uuid.uuid4().hex}"

    flow_meta = {
        "src_ip": "185.23.54.1",
        "dst_ip": "10.0.0.5",
        "src_port": 44444,
        "dst_port": 80,
        "protocol": "TCP",
        "flow_id": request_id,
    }

    for i in range(burst):
        record = {
            "timestamp": base_ts + (i * 0.08),
            "request_id": f"{request_id}-{i}",
            "origin": origin,
            "label": label,
            "confidence": max(0.01, confidence - (i * 0.01)),
            "severity": sev,
            "probabilities": {
                "BENIGN": 0.01 if label != "BENIGN" else 0.99,
                label: confidence,
            },
            "flow_meta": flow_meta,
            "demo": True,
        }
        _jsonl_append(EVENTS_LOG_PATH, record)
        _jsonl_append(ATTACK_LOG_PATH, record)

    return {
        "severity": sev,
        "label": label,
        "burst": burst,
        "request_id": request_id,
    }


def _demo_attack_loop(stop_event: threading.Event):
    while not stop_event.is_set():
        if stop_event.wait(DEMO_ATTACK_INTERVAL):
            break
        try:
            _inject_demo_attack(origin="demo.auto")
            logger.info("Injected demo attack burst")
        except Exception:
            logger.exception("Failed injecting demo attack burst")


# ---------------- startup/shutdown ----------------
@app.on_event("startup")
def startup_event():
    global MODEL, FEATURE_LIST, LABEL_ENCODER, DEMO_THREAD, DEMO_STOP_EVENT
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
        start_human_context()

        if DEMO_AUTO_ATTACK and DEMO_THREAD is None:
            DEMO_STOP_EVENT = threading.Event()
            DEMO_THREAD = threading.Thread(
                target=_demo_attack_loop,
                args=(DEMO_STOP_EVENT,),
                daemon=True,
            )
            DEMO_THREAD.start()
            logger.info(
                "Demo attack loop started",
                extra={"interval_seconds": DEMO_ATTACK_INTERVAL},
            )

    except Exception as e:
        logger.critical("Failed to load artifacts at startup", exc_info=e)
        raise


@app.on_event("shutdown")
def shutdown_event():
    global DEMO_STOP_EVENT, DEMO_THREAD
    logger.info("Shutting down API")
    stop_human_context()
    if DEMO_STOP_EVENT is not None:
        DEMO_STOP_EVENT.set()
    DEMO_THREAD = None
    DEMO_STOP_EVENT = None


# ---------------- middleware ----------------
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


# ---------------- endpoints ----------------
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok" if MODEL is not None else "error",
        model_loaded=MODEL is not None,
        uptime_seconds=int(time.time() - START_TIME),
    )

@app.get("/human-context")
async def human_context():
    payload = get_human_context()
    payload["image"] = get_latest_frame()
    return payload

@app.get("/camera-frame")
def camera_frame():

    frame = get_latest_frame()

    if frame is None:
        return {"image": None}

    return {
        "image": frame
    }

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
async def demo_attack(severity: str = "mid"):
    result = _inject_demo_attack(severity=severity, origin="demo.manual")
    return {"status": "ok", **result}


@app.post("/predict", response_model=PredictResponse)
async def predict(payload: PredictRequest, request: Request):
    if MODEL is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded",
        )

    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)

    try:
        result = predict_one(MODEL, LABEL_ENCODER, FEATURE_LIST, payload.features)

        flow_meta = {
            "src_ip": request.client.host if request.client else "unknown",
            "dst_ip": "ids-server",
            "src_port": None,
            "dst_port": None,
            "protocol": "TCP",
            "flow_id": request_id,
        }

        alert_payload = {
            "label": result.label,
            "confidence": result.confidence,
            "probabilities": result.probabilities,
        }

        # Layer 8 alert integration
        try:
            maybe = process_prediction(
                alert_payload,
                flow_meta,
                extra_metadata={"origin": "api.predict"},
                notify_async=True,
            )
            await _maybe_await(maybe)
        except Exception:
            # alerting must never break prediction
            logger.exception(
                "Alert processing failed",
                extra={"request_id": request_id, "label": result.label},
            )

        # Persist for frontend/dashboard
        _store_prediction_event(
            request_id=request_id,
            result=result,
            flow_meta=flow_meta,
            origin="api.predict",
        )

        logger.info(
            "Prediction successful",
            extra={
                "request_id": request_id,
                "label": result.label,
                "confidence": result.confidence,
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
async def predict_batch_endpoint(payload: BatchPredictRequest, request: Request):
    if MODEL is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded",
        )

    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)

    if len(payload.instances) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch size {len(payload.instances)} exceeds limit {MAX_BATCH_SIZE}",
        )

    try:
        results = predict_batch(MODEL, LABEL_ENCODER, FEATURE_LIST, payload.instances)

        flow_meta = {
            "src_ip": request.client.host if request.client else "unknown",
            "dst_ip": "ids-server",
            "src_port": None,
            "dst_port": None,
            "protocol": "TCP",
            "flow_id": request_id,
        }

        for idx, result in enumerate(results):
            _store_prediction_event(
                request_id=f"{request_id}-{idx}",
                result=result,
                flow_meta=flow_meta,
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


# ---------------- global exception handler ----------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", extra={"path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ---------------- local dev run ----------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.app:app", host=HOST, port=PORT, reload=True)
