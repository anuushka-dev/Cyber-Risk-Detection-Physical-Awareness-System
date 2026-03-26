# train/train_model.py
import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)

from pathlib import Path
import argparse
import json
import logging
import os
import time
import threading
from pprint import pformat

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
import plotly.graph_objects as go

from sklearn.pipeline import Pipeline as SkPipeline
from sklearn.model_selection import StratifiedKFold, RandomizedSearchCV, GridSearchCV
from sklearn.metrics import f1_score, classification_report, confusion_matrix, make_scorer
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight

# local utils
from utils.feature_utils import select_numeric_categorical
from utils.data_utils import load_schema

LOG_FMT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
SEED = 42

# -------------------------
# Small threaded flow-cleaner (optional demo utility)
# -------------------------
class ThreadedFlowCleaner:
    """
    Lightweight thread that periodically prunes an external flows dict by 'last_seen' timestamp.
    This is a demonstration helper ONLY. It does not participate in training data -- it's safe to enable
    with --enable_flow_cleaner to exercise your flow assembler integration or local demos.
    """
    def __init__(self, flows: dict, idle_seconds: int = 5, interval: float = 1.0):
        self.flows = flows
        self.idle_seconds = idle_seconds
        self.interval = interval
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="flow_cleaner")

    def start(self):
        logging.info("Starting ThreadedFlowCleaner (idle=%ds)", self.idle_seconds)
        self.thread.start()

    def stop(self):
        logging.info("Stopping ThreadedFlowCleaner")
        self._stop.set()
        self.thread.join(timeout=2.0)

    def _run(self):
        while not self._stop.is_set():
            now = time.time()
            remove = []
            for fid, meta in list(self.flows.items()):
                last = meta.get("last_seen", 0)
                if now - last > self.idle_seconds:
                    remove.append(fid)
            for fid in remove:
                # defensive remove
                try:
                    del self.flows[fid]
                except KeyError:
                    pass
            time.sleep(self.interval)

# -------------------------
# Wrapper to save fitted preprocessor + booster + helper methods
# -------------------------
class XGBoostPipelineWrapper:
    """
    Small wrapper object to save:
      - fitted preprocessor (sklearn transformer)
      - xgboost Booster (trained via xgb.train)
      - label encoder
    Provides predict/predict_proba that accept pandas DataFrame.
    """
    def __init__(self, preprocessor, booster: xgb.Booster, label_encoder: LabelEncoder, feature_list):
        self.preprocessor = preprocessor
        self.booster = booster
        self.le = label_encoder
        self.feature_list = list(feature_list)

    def predict_proba(self, X: pd.DataFrame):
        X2 = X[self.feature_list].copy()
        X2.columns = X2.columns.str.strip()
        Xt = self.preprocessor.transform(X2)
        # ensure float32
        if Xt.dtype != np.float32:
            try:
                Xt = Xt.astype(np.float32)
            except Exception:
                Xt = np.array(Xt, dtype=np.float32)
        dmat = xgb.DMatrix(Xt)
        probs = self.booster.predict(dmat)
        return probs

    def predict(self, X: pd.DataFrame):
        probs = self.predict_proba(X)
        idx = np.argmax(probs, axis=1)
        return self.le.inverse_transform(idx)

# -------------------------
# Helpers
# -------------------------
def load_pipeline_skeleton(path: Path):
    p = path / "pipeline_skeleton.joblib"
    if not p.exists():
        raise FileNotFoundError(f"Pipeline skeleton not found at {p}. Run model/architecture.py first.")
    pipeline = joblib.load(p)
    if not isinstance(pipeline, SkPipeline):
        raise ValueError("Unexpected pipeline skeleton type. Expect sklearn.pipeline.Pipeline.")
    if "preprocessor" not in pipeline.named_steps or "estimator" not in pipeline.named_steps:
        raise ValueError("Pipeline skeleton must contain 'preprocessor' and 'estimator' steps.")
    return pipeline

def load_feature_list(path: Path, processed_dir: Path):
    p = path / "feature_list.json"
    if p.exists():
        return json.loads(p.read_text())
    # fallback: try schema.json
    schema_p = Path(processed_dir) / "schema.json"
    if schema_p.exists():
        schema = json.loads(schema_p.read_text())
        if "feature_columns" in schema:
            logging.warning("feature_list.json missing; falling back to schema.feature_columns")
            return [c.strip() for c in schema["feature_columns"]]
    raise FileNotFoundError("feature_list.json not found and no schema.feature_columns fallback available.")

def prepare_Xy_from_df(df: pd.DataFrame, feature_list):
    df = df.copy()
    df.columns = df.columns.str.strip()
    missing = [c for c in feature_list if c not in df.columns]
    if missing:
        raise ValueError(f"Missing features in dataframe (first 20 shown): {missing[:20]}")
    X = df[feature_list].copy()
    if "Label" not in df.columns:
        raise ValueError("Label column missing from dataframe.")
    y = df["Label"].astype(str).copy()
    return X, y

def build_param_grid():
    param_grid = {
        "estimator__max_depth": [4, 6, 8],
        "estimator__learning_rate": [0.05, 0.1],
        "estimator__n_estimators": [100, 300],
        "estimator__subsample": [0.8, 1.0],
        "estimator__colsample_bytree": [0.8, 1.0],
    }
    return param_grid

def compute_per_class_thresholds(booster, X_val_trans, y_val_enc, le, feature_list, preprocessor):
    """
    Equivalent threshold search but for booster + preprocessor.
    """
    try:
        dval = xgb.DMatrix(X_val_trans)
        probs = booster.predict(dval)
    except Exception:
        return {c: 0.5 for c in le.classes_}
    thresholds = {}
    for i, cls in enumerate(le.classes_):
        y_true = (y_val_enc == i).astype(int)
        best_t = 0.5
        best_f1 = -1.0
        for t in np.linspace(0.1, 0.9, 17):
            y_pred = (probs[:, i] >= t).astype(int)
            f1 = f1_score(y_true, y_pred)
            if f1 > best_f1:
                best_f1 = f1
                best_t = float(t)
        thresholds[cls] = best_t
    return thresholds

def safe_try_import_smote():
    try:
        from imblearn.over_sampling import SMOTE
        return SMOTE
    except Exception:
        return None

# -------------------------
# Main
# -------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", default="data/processed")
    parser.add_argument("--dataset_dir", default="dataset")
    parser.add_argument("--model_dir", default="model")
    parser.add_argument("--out_dir", default="models")
    parser.add_argument("--cv", type=int, default=3, help="number of CV folds (k). Default 3 for speed/safety.")
    parser.add_argument("--search", choices=["randomized", "grid", "none"], default="randomized")
    parser.add_argument("--n_iter", type=int, default=15, help="n_iter for RandomizedSearchCV")
    parser.add_argument("--n_jobs", type=int, default=2, help="parallel jobs (default 2, safe for limited RAM)")
    parser.add_argument("--early_stopping_rounds", type=int, default=50)
    parser.add_argument("--resample", choices=["none", "class_weight", "smote", "random"], default="class_weight")
    parser.add_argument("--random_state", type=int, default=SEED)
    parser.add_argument("--tune_subset", type=int, default=400000, help="rows to use for hyperparameter tuning subset")
    parser.add_argument("--enable_flow_cleaner", action="store_true", help="start demo threaded flow cleaner while training (optional)")
    args = parser.parse_args()

    np.random.seed(args.random_state)
    processed = Path(args.processed)
    dataset_dir = Path(args.dataset_dir)
    model_dir = Path(args.model_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Loading pipeline skeleton and feature list...")
    pipeline_skel = load_pipeline_skeleton(model_dir)
    feature_list = load_feature_list(model_dir, processed)

    preprocessor = pipeline_skel.named_steps["preprocessor"]
    # estimator from skeleton is only used for param defaults; we'll use xgb.train for final fitting
    base_estimator = pipeline_skel.named_steps["estimator"]
    base_params = base_estimator.get_params()

    logging.info("Loading datasets (parquet)...")
    train_df = pd.read_parquet(dataset_dir / "train.parquet")
    val_df = pd.read_parquet(dataset_dir / "val.parquet")
    test_df = pd.read_parquet(dataset_dir / "test.parquet")
    logging.info("Loaded shapes: train=%s val=%s test=%s", train_df.shape, val_df.shape, test_df.shape)

    # Optional demo flow cleaner (does not alter data used by training)
    demo_flows = {}
    cleaner = None
    if args.enable_flow_cleaner:
        cleaner = ThreadedFlowCleaner(demo_flows, idle_seconds=5)
        cleaner.start()

    # Prepare X,y
    X_train, y_train = prepare_Xy_from_df(train_df, feature_list)
    X_val, y_val = prepare_Xy_from_df(val_df, feature_list)
    X_test, y_test = prepare_Xy_from_df(test_df, feature_list)
    logging.info("Prepared X/y from data (features=%d)", len(feature_list))

    # detect numeric/categorical
    numeric_cols, categorical_cols = select_numeric_categorical(X_train)
    logging.info("Detected numeric=%d, categorical=%d features", len(numeric_cols), len(categorical_cols))

    if args.resample == "smote" and len(categorical_cols) > 0:
        raise RuntimeError("SMOTE requested but categorical columns are present. Use --resample random/class_weight or encode categoricals and use SMOTENC.")

    # label encoder (train only)
    le = LabelEncoder()
    le.fit(y_train)
    joblib.dump(le, out_dir / "label_encoder.joblib")
    logging.info("Saved label encoder (classes=%d) to %s", len(le.classes_), str(out_dir / "label_encoder.joblib"))

    y_train_enc = le.transform(y_train)
    y_val_enc = le.transform(y_val)
    y_test_enc = le.transform(y_test)

    # check unseen labels
    unseen_in_val = set(y_val.unique()) - set(y_train.unique())
    unseen_in_test = set(y_test.unique()) - set(y_train.unique())
    if unseen_in_val or unseen_in_test:
        logging.error("Found labels in val/test not present in train. Val unseen: %s Test unseen: %s", unseen_in_val, unseen_in_test)
        raise ValueError("Validation/test contains labels not seen in training. Inspect dataset splits.")
# sample weight for CV (will be subset later)
    sample_weight_for_cv = None
    if args.resample == "class_weight":
    # Compute full weights, then subset with the same indices used for tuning
        sample_weight_full = compute_sample_weight(class_weight="balanced", y=y_train_enc)
        logging.info("Computed sample_weight for CV (class_weight) – will subset after creating tuning set.")

    # -----------------------------
    # Subset-based CV tuning (fast)
    # -----------------------------
    logging.info("Preparing subset for hyperparameter tuning (rows=%d)", args.tune_subset)
    if len(X_train) > args.tune_subset:
        idx = np.random.choice(len(X_train), args.tune_subset, replace=False)
        X_tune = X_train.iloc[idx].reset_index(drop=True)
        y_tune = y_train_enc[idx]
    else:
        X_tune = X_train
        y_tune = y_train_enc

    # Subset sample weights if using class_weight
    if args.resample == "class_weight" and sample_weight_full is not None:
    # Ensure idx is defined (for the else case we need to create it)
        if 'idx' not in locals():
            idx = np.arange(len(X_train))
        sample_weight_for_cv = sample_weight_full[idx]
        logging.info("Subset sample_weight to tuning set (size %d).", len(sample_weight_for_cv))
    else:
        sample_weight_for_cv = None

    # cast to float32 early for memory savings (preprocessor will handle transforms)
    # note: we keep original X_train dtype for final preprocessing transform
    # CV will operate on DataFrame and pipeline (sklearn handles dtype); still convert columns to float32 where numeric
    for c in numeric_cols:
        if c in X_tune.columns and X_tune[c].dtype != np.float32:
            try:
                X_tune[c] = X_tune[c].astype(np.float32)
            except Exception:
                pass

    logging.info("Starting CV search (method=%s, cv=%d, n_iter=%d, n_jobs=%d)...", args.search, args.cv, args.n_iter, args.n_jobs)
    cv = StratifiedKFold(n_splits=args.cv, shuffle=True, random_state=args.random_state)

    # Build estimator for CV (sklearn wrapper) - use preprocessor from skeleton and a fresh XGBClassifier
    estimator_for_cv = xgb.XGBClassifier(**{k: v for k, v in base_params.items() if not k.startswith("_")})
    cv_pipeline = SkPipeline(steps=[("preprocessor", preprocessor), ("estimator", estimator_for_cv)])
    param_grid = build_param_grid()

    search_result = None
    best_params = {}

    if args.search == "none":
        logging.info("Skipping hyperparameter search (--search none). Using skeleton params.")
    elif args.search == "grid":
        gs = GridSearchCV(estimator=cv_pipeline, param_grid=param_grid, cv=cv,
                          scoring=make_scorer(f1_score, average="macro"),
                          n_jobs=args.n_jobs, verbose=2, refit=False)
        fit_kwargs = {}
        if sample_weight_for_cv is not None:
            fit_kwargs = {"estimator__sample_weight": sample_weight_for_cv}
        gs.fit(X_tune, y_tune, **fit_kwargs)
        search_result = gs
        best_params = gs.best_params_
    else:
        rs = RandomizedSearchCV(estimator=cv_pipeline,
                                param_distributions=param_grid,
                                n_iter=args.n_iter,
                                cv=cv,
                                scoring=make_scorer(f1_score, average="macro"),
                                n_jobs=args.n_jobs,
                                random_state=args.random_state,
                                verbose=2,
                                refit=False)
        fit_kwargs = {}
        if sample_weight_for_cv is not None:
            fit_kwargs = {"estimator__sample_weight": sample_weight_for_cv}
        rs.fit(X_tune, y_tune, **fit_kwargs)
        search_result = rs
        best_params = rs.best_params_

    logging.info("CV search done. best_params (raw)=%s", str(best_params))

    # Save CV summary
    if search_result is not None:
        out_cv = out_dir / "cv_results.json"
        try:
            summary = {"best_params": search_result.best_params_, "best_score": float(search_result.best_score_)}
            if hasattr(search_result, "cv_results_"):
                cr = search_result.cv_results_
                entries = []
                for i in range(min(5, len(cr["params"]))):
                    entries.append({"params": cr["params"][i], "mean_test_score": float(cr["mean_test_score"][i]), "std_test_score": float(cr["std_test_score"][i])})
                summary["example_entries"] = entries
            out_cv.write_text(json.dumps(summary, indent=2))
            logging.info("Wrote CV summary to %s", out_cv)
        except Exception as e:
            logging.warning("Failed to save CV summary: %s", e)

    # Merge best params into final params
    final_params = base_params.copy()
    if best_params:
        for k, v in best_params.items():
            if k.startswith("estimator__"):
                final_params[k.replace("estimator__", "")] = v
            else:
                final_params[k] = v

    logging.info("Final XGB params (preview): %s", {k: final_params[k] for k in ["max_depth", "learning_rate", "n_estimators", "subsample", "colsample_bytree"] if k in final_params})

    # -----------------------------
    # Final training using DMatrix (native xgboost.train)
    # -----------------------------
    logging.info("Fitting preprocessor on full training data...")
    preprocessor_fitted = preprocessor.fit(X_train)
    X_train_trans = preprocessor_fitted.transform(X_train)
    X_val_trans = preprocessor_fitted.transform(X_val)
    X_test_trans = preprocessor_fitted.transform(X_test)

    # ensure float32 for DMatrix
    try:
        if X_train_trans.dtype != np.float32:
            X_train_trans = X_train_trans.astype(np.float32)
        if X_val_trans.dtype != np.float32:
            X_val_trans = X_val_trans.astype(np.float32)
    except Exception:
        # if sparse matrix etc. convert via numpy
        X_train_trans = np.asarray(X_train_trans).astype(np.float32)
        X_val_trans = np.asarray(X_val_trans).astype(np.float32)

    # handle resampling for final training
    X_final = X_train_trans
    y_final = np.array(y_train_enc)
    sample_weight_final = None

    if args.resample == "class_weight":
        sample_weight_final = compute_sample_weight(class_weight="balanced", y=y_train_enc)
        logging.info("Using class_weight sample weights for final training.")
    elif args.resample == "random":
        # random oversample (on transformed arrays)
        unique, counts = np.unique(y_train_enc, return_counts=True)
        target = int(np.max(counts))
        Xs, ys = [], []
        for cls in unique:
            mask = (y_train_enc == cls)
            Xc = X_train_trans[mask]
            yc = y_train_enc[mask]
            if len(Xc) == 0:
                continue
            if len(Xc) < target:
                idxs = np.random.choice(len(Xc), size=(target - len(Xc)), replace=True)
                Xc_up = np.concatenate([Xc, Xc[idxs]], axis=0)
                yc_up = np.concatenate([yc, yc[idxs]], axis=0)
            else:
                Xc_up = Xc
                yc_up = yc
            Xs.append(Xc_up)
            ys.append(yc_up)
        X_final = np.concatenate(Xs, axis=0)
        y_final = np.concatenate(ys, axis=0)
        perm = np.random.permutation(len(y_final))
        X_final = X_final[perm]; y_final = y_final[perm]
        logging.info("Random oversampling produced final training shape=%s", X_final.shape)
    elif args.resample == "smote":
        SMOTE = safe_try_import_smote()
        if SMOTE is None:
            raise RuntimeError("SMOTE requested but imbalanced-learn not installed.")
        sm = SMOTE(random_state=args.random_state)
        X_final, y_final = sm.fit_resample(X_train_trans, y_train_enc)
        logging.info("SMOTE produced final training shape=%s", X_final.shape)
    else:
        logging.info("No resampling for final training.")

    # build DMatrix
    dtrain = xgb.DMatrix(X_final, label=y_final)
    dval = xgb.DMatrix(X_val_trans, label=y_val_enc)

    # xgb params mapping
    xgb_params = {
        "objective": "multi:softprob",
        "num_class": len(le.classes_),
        "max_depth": int(final_params.get("max_depth", 6)),
        "eta": float(final_params.get("learning_rate", 0.1)),
        "subsample": float(final_params.get("subsample", 0.8)),
        "colsample_bytree": float(final_params.get("colsample_bytree", 0.8)),
        "tree_method": "hist",
        "verbosity": 0,
        "seed": args.random_state,
    }
    num_boost_round = int(final_params.get("n_estimators", 200))

    evals_result = {}
    logging.info("Starting native XGBoost training (num_boost_round=%d)", num_boost_round)
    booster = xgb.train(
        xgb_params,
        dtrain,
        num_boost_round=num_boost_round,
        evals=[(dval, "validation")],
        early_stopping_rounds=args.early_stopping_rounds,
        evals_result=evals_result,
        verbose_eval=True
    )

    # wrap and save final pipeline wrapper
    wrapper = XGBoostPipelineWrapper(preprocessor_fitted, booster, le, feature_list)
    model_path = out_dir / "intrusion_model.joblib"
    joblib.dump(wrapper, model_path)
    logging.info("Saved fitted pipeline wrapper to %s", model_path)

    # Evaluate on test using wrapper
    y_pred = wrapper.predict(X_test)
    try:
        y_pred_proba = wrapper.predict_proba(X_test)
    except Exception:
        y_pred_proba = None

    macro_f1 = f1_score(y_test, y_pred, average="macro")
    class_report = classification_report(y_test, y_pred, digits=4)
    cm = confusion_matrix(y_test, y_pred, labels=le.classes_)

    logging.info("Final test macro-F1 = %.4f", macro_f1)
    (out_dir / "classification_report.txt").write_text(class_report, encoding='utf-8')
    joblib.dump(cm, out_dir / "confusion_matrix.joblib")
    (out_dir / "model_metadata.json").write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "train_shape": X_train.shape,
        "val_shape": X_val.shape,
        "test_shape": X_test.shape,
        "cv_folds": args.cv,
        "search_method": args.search,
        "n_iter": args.n_iter,
        "final_xgb_params": {k: xgb_params[k] for k in ["max_depth", "eta", "num_class", "subsample", "colsample_bytree"] if k in xgb_params},
        "test_macro_f1": float(macro_f1),
        "label_classes": le.classes_.tolist()
    }, indent=2))
    logging.info("Saved reports and metadata to %s", out_dir)

    # thresholds
    thresholds = compute_per_class_thresholds(booster, X_val_trans, y_val_enc, le, feature_list, preprocessor_fitted)
    (out_dir / "model_thresholds.json").write_text(json.dumps(thresholds, indent=2))
    logging.info("Saved model_thresholds.json")

    # Save evals_result as plotly interactive plot
    try:
        if "validation" in evals_result and "mlogloss" in evals_result["validation"]:
            # Plot eval metric curves (if available)
            # evals_result structure: {'validation': {'mlogloss': [...], 'merror': [...]}}
            fig = go.Figure()
            for metric, vals in evals_result["validation"].items():
                fig.add_trace(go.Scatter(y=vals, name=f"validation-{metric}"))
            fig.update_layout(title="XGBoost evals (validation)", xaxis_title="Boosting round", yaxis_title="metric")
            html_path = out_dir / "training_plot.html"
            fig.write_html(str(html_path))
            logging.info("Saved training plot to %s", html_path)
        else:
            # fallback: save simple placeholder
            (out_dir / "training_plot.html").write_text("<html><body><p>No evals_result mlogloss found.</p></body></html>")
    except Exception as e:
        logging.warning("Failed to write training plot: %s", e)

    # Stop demo cleaner if running
    if cleaner:
        cleaner.stop()

    logging.info("Training pipeline complete. Macro-F1: %.4f", macro_f1)

if __name__ == "__main__":
    main()

