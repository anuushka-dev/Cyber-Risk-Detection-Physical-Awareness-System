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


"""import sys
from pathlib import Path

# add project root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from train.train_model import XGBoostPipelineWrapper
import joblib

# register class under __main__ so we can load old artifact
import __main__
__main__.XGBoostPipelineWrapper = XGBoostPipelineWrapper

model = joblib.load("models/intrusion_model.joblib")

# save again with correct module path
joblib.dump(model, "models/intrusion_model.joblib")

print("Model re-serialized successfully.")"""