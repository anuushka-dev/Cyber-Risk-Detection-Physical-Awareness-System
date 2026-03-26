from pathlib import Path
import argparse, json, logging, sys, time
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import joblib

SEED = 42
MIN_CLASS_COUNT = 30   # classes with fewer samples will be grouped into OTHER_ATTACK

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def load_combined(processed_dir: Path):
    p = processed_dir / "combined_cleaned.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Run prepare_dataset first.")
    return pd.read_parquet(p)

def group_small_classes(df, min_count=MIN_CLASS_COUNT):
    if "Label" not in df.columns:
        raise KeyError("Label column missing")
    counts = df["Label"].value_counts()
    small = counts[counts < min_count].index.tolist()
    if small:
        logging.info(f"Grouping small classes (<{min_count}) into OTHER_ATTACK: {small}")
        df["Label"] = df["Label"].apply(lambda x: "OTHER_ATTACK" if x in small else x)
    return df

def safe_stratified_split(X, y, train_size, val_size, test_size, random_state=SEED):
    # First split train vs temp
    try:
        X_train, X_temp, y_train, y_temp = train_test_split(
            X, y, train_size=train_size, stratify=y, random_state=random_state
        )
        # compute proportion of val within temp
        temp_total = val_size + test_size
        val_rel = val_size / temp_total
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, test_size=(test_size/temp_total), stratify=y_temp, random_state=random_state
        )
        return X_train, X_val, X_test, y_train, y_val, y_test, True
    except ValueError as e:
        logging.warning("Stratified split failed (too few samples per class). Falling back to non-stratified split. Error: %s", e)
        # fallback random split without stratify
        N = len(y)
        idx = np.arange(N)
        rng = np.random.RandomState(random_state)
        rng.shuffle(idx)
        n_train = int(train_size * N)
        n_val = int(val_size * N)
        train_idx = idx[:n_train]
        val_idx = idx[n_train:n_train+n_val]
        test_idx = idx[n_train+n_val:]
        X_np = X.reset_index(drop=True)
        y_np = pd.Series(y).reset_index(drop=True)
        return (X_np.iloc[train_idx], X_np.iloc[val_idx], X_np.iloc[test_idx],
                y_np.iloc[train_idx], y_np.iloc[val_idx], y_np.iloc[test_idx], False)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", default="data/processed")
    parser.add_argument("--train_frac", type=float, default=0.7)
    parser.add_argument("--val_frac", type=float, default=0.2)
    parser.add_argument("--test_frac", type=float, default=0.1)
    args = parser.parse_args()

    processed = Path(args.processed).resolve()
    if abs(args.train_frac + args.val_frac + args.test_frac - 1.0) > 1e-6:
        logging.error("train_frac + val_frac + test_frac must sum to 1.0")
        sys.exit(2)

    # Load and normalize columns
    df = load_combined(processed)
    df.columns = df.columns.str.strip()
    logging.info(f"Loaded combined dataset shape={df.shape}")

    if "Label" not in df.columns:
        logging.error("Label column not found. Aborting.")
        sys.exit(3)

    df = df.dropna(subset=["Label"])
    df = group_small_classes(df, MIN_CLASS_COUNT)
    label_counts = df["Label"].value_counts().to_dict()
    logging.info(f"Label counts after grouping: {label_counts}")

    le = LabelEncoder()
    y = le.fit_transform(df["Label"])
    classes = list(le.classes_)
    logging.info(f"Label classes: {classes}")

    X = df.drop(columns=["Label"]).reset_index(drop=True)

    X_train, X_val, X_test, y_train, y_val, y_test, stratified = safe_stratified_split(
        X, y, train_size=args.train_frac, val_size=args.val_frac, test_size=args.test_frac, random_state=SEED
    )
    logging.info(f"Split done. stratified={stratified}. Shapes: train={X_train.shape}, val={X_val.shape}, test={X_test.shape}")

    train_df = X_train.copy()
    train_df["Label"] = le.inverse_transform(y_train)
    val_df = X_val.copy()
    val_df["Label"] = le.inverse_transform(y_val)
    test_df = X_test.copy()
    test_df["Label"] = le.inverse_transform(y_test)

    train_path = processed / "train.parquet"
    val_path = processed / "val.parquet"
    test_path = processed / "test.parquet"
    train_df.to_parquet(train_path, index=False)
    val_df.to_parquet(val_path, index=False)
    test_df.to_parquet(test_path, index=False)
    logging.info(f"Wrote train {train_df.shape} -> {train_path}")
    logging.info(f"Wrote val {val_df.shape} -> {val_path}")
    logging.info(f"Wrote test {test_df.shape} -> {test_path}")

    meta = {
        "seed": SEED,
        "label_classes": classes,
        "feature_columns": list(X.columns),
        "train_shape": train_df.shape,
        "val_shape": val_df.shape,
        "test_shape": test_df.shape,
        "stratified_split": bool(stratified),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    (processed / "train_test_meta.json").write_text(json.dumps(meta, indent=2))
    joblib.dump(le, processed / "label_encoder.joblib")
    logging.info("Saved train_test_meta.json and label_encoder.joblib")

    sample_npz = processed / "train_sample.npz"
    sample_small = train_df.sample(n=min(200, len(train_df)), random_state=SEED)
    np.savez_compressed(sample_npz, X=sample_small.drop(columns=["Label"]).to_numpy(), y=sample_small["Label"].to_numpy())
    logging.info("Saved small sample npz for quick tests. DONE.")

if __name__ == "__main__":
    main()