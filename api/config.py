# api/config.py
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MODEL_DIR = Path(os.getenv("MODEL_DIR", str(PROJECT_ROOT / "models")))
FEATURE_DIR = Path(os.getenv("FEATURE_DIR", str(PROJECT_ROOT / "model")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "256"))
REJECT_LOW_CONFIDENCE = os.getenv("REJECT_LOW_CONFIDENCE", "false").lower() == "true"
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))

# timeouts, limits
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
MAX_REQUEST_SIZE_BYTES = int(os.getenv("MAX_REQUEST_SIZE_BYTES", str(2 * 1024 * 1024)))  # 2 MB