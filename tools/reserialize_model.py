import sys
from pathlib import Path

# add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# import wrapper class
from train.train_model import XGBoostPipelineWrapper

import joblib
import __main__

# map old pickle reference
__main__.XGBoostPipelineWrapper = XGBoostPipelineWrapper

model_path = Path("models") / "intrusion_model.joblib"

print("Loading model...")
model = joblib.load(model_path)

print("Re-saving model with correct module path...")
joblib.dump(model, model_path)

print("Done. Model is now portable.")