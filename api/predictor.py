# api/predictor.py
from typing import List, Dict, Any
import numpy as np
import pandas as pd
from .logging_config import logger
from .config import CONFIDENCE_THRESHOLD, REJECT_LOW_CONFIDENCE
from .schemas import PredictionResult

def validate_features_list(features: List[float], feature_list: List[str]) -> pd.DataFrame:
    if not isinstance(features, list):
        raise ValueError("features must be a list")
    if len(features) != len(feature_list):
        raise ValueError(f"Expected {len(feature_list)} features, got {len(features)}")
    # check finite numbers
    arr = np.asarray(features, dtype=float)
    if not np.isfinite(arr).all():
        raise ValueError("features contain NaN or infinite values")
    return pd.DataFrame([arr.tolist()], columns=feature_list)

def build_prediction_from_proba(probs: np.ndarray, label_encoder: Any) -> PredictionResult:
    classes = list(label_encoder.classes_)
    idx = int(np.argmax(probs))
    confidence = float(probs[idx])
    label = str(classes[idx])
    prob_map = {str(c): float(p) for c, p in zip(classes, probs)}
    return PredictionResult(label=label, confidence=confidence, probabilities=prob_map)

def predict_one(model: Any, label_encoder: Any, feature_list: List[str], features: List[float]) -> PredictionResult:
    df = validate_features_list(features, feature_list)
    try:
        probs = model.predict_proba(df)[0]
    except AttributeError:
        # sometimes wrapper uses predict returning labels — attempt to return a best-effort result
        pred = model.predict(df)
        label = pred[0] if isinstance(pred, (list, tuple)) else pred
        return PredictionResult(label=str(label), confidence=1.0, probabilities={str(label): 1.0})
    except Exception as e:
        logger.exception("Model predict_proba failed", exc_info=e)
        raise

    result = build_prediction_from_proba(probs, label_encoder)
    if REJECT_LOW_CONFIDENCE and result.confidence < CONFIDENCE_THRESHOLD:
        raise ValueError(f"Confidence {result.confidence:.4f} below threshold {CONFIDENCE_THRESHOLD}")
    return result

def predict_batch(model: Any, label_encoder: Any, feature_list: List[str], instances: List[List[float]]):
    # convert to DataFrame in vectorized way (validate shapes)
    import numpy as _np
    arr = _np.array(instances, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != len(feature_list):
        raise ValueError(f"Instances matrix must be shape (N, {len(feature_list)})")
    df = pd.DataFrame(arr, columns=feature_list)
    probs = model.predict_proba(df)
    results = []
    for p in probs:
        res = build_prediction_from_proba(p, label_encoder)
        if REJECT_LOW_CONFIDENCE and res.confidence < CONFIDENCE_THRESHOLD:
            raise ValueError(f"An instance confidence {res.confidence:.4f} below threshold {CONFIDENCE_THRESHOLD}")
        results.append(res)
    return results