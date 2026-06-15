# utils/data_utils.py
from pathlib import Path
import json
import pandas as pd
import psutil
import os
from typing import Tuple


def available_memory_gb() -> float:
    try:
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        return 2.0


def load_combined(processed_dir: Path or str = "data/processed", prefer_sample_threshold_gb: float = 6.0) -> pd.DataFrame:
    processed_dir = Path(processed_dir)
    combined = processed_dir / "combined_cleaned.parquet"
    sample_csv = processed_dir / "sample_cleaned.csv.gz"

    if not combined.exists():
        raise FileNotFoundError(f"{combined} not found. Run prepare_dataset first.")

    mem = available_memory_gb()
    if mem < prefer_sample_threshold_gb:
        # low memory: prefer using sample CSV if available
        if sample_csv.exists():
            df = pd.read_csv(sample_csv, compression="gzip", low_memory=False)
            df.columns = df.columns.str.strip()
            return df
        # as last resort try an in-file row-sample using pyarrow/dask (not used here) — fallback to read parquet
    # normal path: read parquet
    df = pd.read_parquet(combined)
    df.columns = df.columns.str.strip()
    return df


def validate_schema_matches_df(schema: dict, df: pd.DataFrame) -> Tuple[bool, str]:
    schema_cols = schema.get("feature_columns") or schema.get("feature_columns", None)
    if schema_cols is None:
        return False, "schema.feature_columns not present"
    # strip schema entries too
    schema_cols = [s.strip() for s in schema_cols]
    df_cols = [c.strip() for c in df.columns.tolist()]
    if len(schema_cols) != len(df_cols):
        return False, f"column count mismatch: schema {len(schema_cols)} vs df {len(df_cols)}"
    for i, (a, b) in enumerate(zip(schema_cols, df_cols)):
        if a != b:
            return False, f"mismatch at index {i}: schema='{a}' vs df='{b}'"
    return True, "ok"


def load_schema(processed_dir: Path or str = "data/processed") -> dict:
    p = Path(processed_dir) / "schema.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Run prepare_dataset first.")
    return json.loads(p.read_text())