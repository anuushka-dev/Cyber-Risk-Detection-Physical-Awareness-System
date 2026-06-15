# api/model_loader.py
import sys
import joblib
import json
from pathlib import Path
from typing import Tuple, List, Any
from .config import MODEL_DIR, FEATURE_DIR, PROJECT_ROOT
from .logging_config import logger

# Ensure project root is on sys.path so 'train' and other sibling packages are importable
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Try to import wrapper class so pickle can resolve it if artifact references it
try:
    # import the training wrapper so unpickling resolves class location train.train_model.XGBoostPipelineWrapper
    from train.train_model import XGBoostPipelineWrapper  # type: ignore
    logger.debug("Found train.train_model.XGBoostPipelineWrapper for unpickling")
except Exception:
    # If wrapper unavailable, continue; joblib may still work if artifact references stable module path.
    logger.debug("train.train_model.XGBoostPipelineWrapper not importable (may not be needed)")

def load_artifacts(model_dir: Path = MODEL_DIR, feature_dir: Path = FEATURE_DIR) -> Tuple[Any, List[str], Any]:
    model_path = model_dir / "intrusion_model.joblib"
    le_path = model_dir / "label_encoder.joblib"
    feature_path = feature_dir / "feature_list.json"

    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    if not le_path.exists():
        raise FileNotFoundError(f"Label encoder not found: {le_path}")

    if not feature_path.exists():
        raise FileNotFoundError(f"Feature list not found: {feature_path}")

    # load feature list first (so we can validate shape quickly)
    with open(feature_path, "r", encoding="utf-8") as f:
        feature_list = json.load(f)
    if not isinstance(feature_list, list):
        raise ValueError("feature_list.json must be a JSON array of feature names")

    # load label encoder
    label_encoder = joblib.load(le_path)

    # load model (joblib will use imported classes above if needed)
    model = joblib.load(model_path)

    # Basic validations
    if not hasattr(label_encoder, "classes_"):
        raise ValueError("Label encoder does not expose classes_ attribute")

    # If model exposes a stored feature list, check consistency (optional)
    try:
        stored = getattr(model, "feature_list", None)
        if stored is not None:
            if len(stored) != len(feature_list):
                logger.warning("Feature list length mismatch: artifact vs model.feature_list")
    except Exception:
        logger.debug("Model does not expose attribute 'feature_list'")

    logger.info("Loaded artifacts", extra={"model_path": str(model_path), "n_features": len(feature_list), "n_classes": len(label_encoder.classes_)})
    return model, feature_list, label_encoder