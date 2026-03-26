# tools/env_check.py
import sys, importlib, json, os
from pathlib import Path
import shutil

try:
    import psutil
except Exception:
    psutil = None

REQUIRED_PYTHON_MIN = (3,9)
REQUIRED_PACKAGES = [
    ("pandas","pandas"),
    ("numpy","numpy"),
    ("sklearn","scikit-learn"),
    ("xgboost","xgboost"),
    ("joblib","joblib"),
    ("pyarrow","pyarrow"),
    ("psutil","psutil"),
]

def check_python():
    v = sys.version_info
    ok = v[:2] >= REQUIRED_PYTHON_MIN
    return ok, f"{v.major}.{v.minor}.{v.micro}"

def check_packages():
    results = {}
    for mod_name, pkg in REQUIRED_PACKAGES:
        try:
            m = importlib.import_module(mod_name)
            ver = getattr(m, "__version__", "unknown")
            results[pkg] = ver
        except Exception as e:
            results[pkg] = f"missing: {e}"
    return results

def disk_and_mem():
    du = shutil.disk_usage(".")
    mem_info = {}
    if psutil:
        mem = psutil.virtual_memory()
        mem_info = {
            "mem_total_gb": int(mem.total // (1024**3)),
            "mem_available_gb": int(mem.available // (1024**3)),
            "cpu_count_logical": psutil.cpu_count(),
            "cpu_count_physical": psutil.cpu_count(logical=False) or psutil.cpu_count()
        }
    return {
        "disk_total_gb": du.total // (1024**3),
        "disk_free_gb": du.free // (1024**3),
        **mem_info
    }

def main():
    base = Path.cwd()
    raw = base / "Raw_Dataset"
    env = {
        "python_ok": None,
        "python_version": None,
        "packages": {},
        "hardware": {},
        "raw_dataset_exists": raw.exists()
    }
    ok, pyver = check_python()
    env["python_ok"] = ok
    env["python_version"] = pyver
    env["packages"] = check_packages()
    env["hardware"] = disk_and_mem()
    env["env_vars"] = {
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
        "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS"),
    }

    print(json.dumps(env, indent=2))
    if not ok:
        print(f"ERROR: Python >= {REQUIRED_PYTHON_MIN} required.")
        sys.exit(2)
    missing = [p for p,v in env["packages"].items() if str(v).startswith("missing")]
    if missing:
        print("MISSING packages:", missing)
        print("Install them: pip install -r requirements.txt")
        sys.exit(3)
    if not env["raw_dataset_exists"]:
        print("WARNING: Raw_Dataset not found in project root. Place the CSV files in Raw_Dataset/")
    #print("Environment check complete.")

if __name__ == "__main__":
    main()