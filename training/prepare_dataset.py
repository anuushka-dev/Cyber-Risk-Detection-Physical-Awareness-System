# training/prepare_dataset.py

from pathlib import Path
import argparse, json, logging, sys, time, hashlib
import numpy as np
import pandas as pd

# Config: tune these if necessary
SEED = 42
SAMPLE_LIMIT = 200_000
DEFAULT_CHUNKSIZE = 200_000
CLIP_BOUNDS = (-1e9, 1e9)  # safe clipping to avoid huge outliers
MIN_ROWS_FOR_SAMPLE = 1000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def choose_chunksize():
    # adaptive: read available RAM if psutil available
    try:
        import psutil
        ram_gb = psutil.virtual_memory().available // (1024**3)
    except Exception:
        ram_gb = 4
    if ram_gb >= 16:
        return DEFAULT_CHUNKSIZE
    elif ram_gb >= 8:
        return 100_000
    elif ram_gb >= 4:
        return 50_000
    else:
        return 25_000

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def get_csv_files(raw_dir: Path):
    if not raw_dir.exists():
        raise FileNotFoundError(f"{raw_dir} not found")
    files = sorted([p for p in raw_dir.iterdir() if p.suffix.lower() == ".csv"])
    if not files:
        raise FileNotFoundError(f"No CSVs in {raw_dir}")
    return files

def deterministic_sample(files, limit, chunksize, seed):
    rng = np.random.RandomState(seed)
    collected = []
    count = 0
    for f in files:
        for chunk in pd.read_csv(f, chunksize=chunksize, low_memory=False):
            chunk.replace([np.inf, -np.inf], np.nan, inplace=True)
            remaining = limit - count
            if remaining <= 0:
                break
            if len(chunk) <= remaining:
                collected.append(chunk)
                count += len(chunk)
            else:
                collected.append(chunk.sample(n=remaining, random_state=seed))
                count += remaining
        if count >= limit:
            break
    if not collected:
        return pd.DataFrame()
    return pd.concat(collected, ignore_index=True)

def infer_schema(sample_df: pd.DataFrame):
    col_types = {}
    numeric_cols = []
    for c in sample_df.columns:
        if pd.api.types.is_numeric_dtype(sample_df[c]):
            col_types[c] = "numeric"
            numeric_cols.append(c)
        else:
            col_types[c] = "categorical"
    medians = {}
    for c in numeric_cols:
        med = sample_df[c].median(skipna=True)
        medians[c] = float(med) if not pd.isna(med) else 0.0
    return {"col_types": col_types, "numeric_cols": numeric_cols, "medians": medians}

def downcast_df(df: pd.DataFrame):
    # downcast ints and floats to reduce memory
    for col in df.select_dtypes(include=["int64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="integer")
    for col in df.select_dtypes(include=["float64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="float")
    return df

def process_and_write_parts(files, out_dir: Path, schema: dict, chunksize: int):
    parts = []
    stats = {"rows_read": 0, "rows_written": 0, "rows_dropped": 0, "clipped_counts": {}}
    part_idx = 0
    for f in files:
        logging.info(f"Processing file {f.name}")
        for chunk in pd.read_csv(f, chunksize=chunksize, low_memory=False):
            stats["rows_read"] += len(chunk)
            # Normalize column names for this chunk (strip leading/trailing spaces)
            chunk.columns = chunk.columns.str.strip()
            # replace infinities
            chunk.replace([np.inf, -np.inf], np.nan, inplace=True)
            # drop rows that are entirely NaN
            chunk.dropna(axis=0, how="all", inplace=True)
            # negative flow duration if present
            if "Flow Duration" in chunk.columns:
                mask_invalid = chunk["Flow Duration"].apply(lambda x: pd.isna(x) or (isinstance(x, (int,float)) and x < 0))
                if mask_invalid.any():
                    stats["rows_dropped"] += int(mask_invalid.sum())
                    chunk = chunk[~mask_invalid]
            # fill numeric medians
            for c in schema["numeric_cols"]:
                if c in chunk.columns:
                    if chunk[c].isna().any():
                        chunk[c].fillna(schema["medians"].get(c, 0.0), inplace=True)
                    lo, hi = CLIP_BOUNDS
                    clipped = ((chunk[c] < lo) | (chunk[c] > hi)).sum()
                    if clipped:
                        stats["clipped_counts"][c] = stats["clipped_counts"].get(c, 0) + int(clipped)
                        chunk[c] = chunk[c].clip(lo, hi)
            # fill categorical
            for c,t in schema["col_types"].items():
                if t == "categorical" and c in chunk.columns:
                    if chunk[c].isna().any():
                        chunk[c].fillna("UNKNOWN", inplace=True)
            # drop duplicates
            before = len(chunk)
            chunk.drop_duplicates(inplace=True)
            stats["rows_dropped"] += before - len(chunk)
            # downcast
            chunk = downcast_df(chunk)
            part_file = out_dir / f"part_{part_idx}.parquet"
            chunk.to_parquet(part_file, index=False)
            parts.append(str(part_file))
            stats["rows_written"] += len(chunk)
            logging.info(f"Wrote part {part_file} rows={len(chunk)}")
            part_idx += 1
    return parts, stats
def merge_parts(parts, out_path: Path):
    # merge in a memory-friendly way
    df_iter = (pd.read_parquet(p) for p in parts)
    combined = pd.concat(df_iter, ignore_index=True)
    # Normalize column names (remove CICIDS leading/trailing spaces)
    combined.columns = combined.columns.str.strip()
    # final write
    combined.to_parquet(out_path, index=False)
    return combined

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw_dir", default="Raw_Dataset", help="raw csv folder (default: Raw_Dataset)")
    parser.add_argument("--out_dir", default="data/processed", help="output folder (default data/processed)")
    parser.add_argument("--sample_limit", type=int, default=SAMPLE_LIMIT)
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    files = get_csv_files_from = None
    try:
        files = get_csv_files(raw_dir)
    except Exception as e:
        logging.error(str(e))
        sys.exit(2)

    chunksize = choose_chunksize()
    logging.info(f"Chunksize chosen: {chunksize}")

    logging.info("Sampling deterministic rows to infer schema and medians...")
    sample_df = deterministic_sample(files, args.sample_limit, chunksize, SEED)
    if sample_df.empty or len(sample_df) < MIN_ROWS_FOR_SAMPLE:
        logging.error("Sample too small or empty; aborting.")
        sys.exit(3)

    # Normalize sample column names (remove leading/trailing spaces from headers)
    sample_df.columns = sample_df.columns.str.strip()

    schema = infer_schema(sample_df)
    (out_dir / "schema_prelim.json").write_text(json.dumps(schema, indent=2))
    logging.info("Saved provisional schema")

    parts, stats = process_and_write_parts(files, out_dir, schema, chunksize)
    logging.info(f"Wrote {len(parts)} part files")

    final_path = out_dir / "combined_cleaned.parquet"
    logging.info("Merging parts...")
    combined = merge_parts(parts, final_path)
    logging.info(f"Final merged saved to {final_path} shape={combined.shape}")

    # post-run meta
    meta = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parts": parts,
        "stats": stats,
        "sha256": sha256_file(final_path),
        "rows": int(combined.shape[0]),
        "cols": int(combined.shape[1])
    }
    (out_dir / "schema.json").write_text(json.dumps({
        **schema,
        "feature_columns": list(combined.columns),
        "meta": meta
    }, indent=2))
    (out_dir / "dataset_stats.json").write_text(json.dumps(meta, indent=2))

    # quick validation: ensure no infs in numeric columns
    numeric = combined.select_dtypes(include=["number"])
    if not np.isfinite(numeric.values).all():
        logging.error("Non-finite values present in numeric columns after cleaning")
        sys.exit(4)

    # sample CSV for quick tests
    sample_csv = out_dir / "sample_cleaned.csv.gz"
    combined.sample(n=min(2000, len(combined)), random_state=SEED).to_csv(sample_csv, index=False, compression="gzip")
    logging.info("Prepared sample CSV and metadata. DONE.")

if __name__ == "__main__":
    main()