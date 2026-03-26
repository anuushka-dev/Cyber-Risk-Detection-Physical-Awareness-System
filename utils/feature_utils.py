# utils/feature_utils.py
"""
Feature selection helpers:
 - remove_constant_features
 - remove_highly_correlated
 - safe_strip_columns
 - select_numeric_categorical
All functions are pure and documented.
"""

from typing import List, Tuple, Dict
import re
import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif

ID_LIKE_RE = re.compile(r"(id$|^id|flow|time|timestamp|src|dst|ip|addr|address)", re.I)

def safe_strip_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns.astype(str)]
    return df

def select_numeric_categorical(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    df = safe_strip_columns(df)
    numeric = df.select_dtypes(include=["number"]).columns.tolist()
    categorical = [c for c in df.columns if c not in numeric and c != "Label"]
    return numeric, categorical

def detect_id_like_columns(df: pd.DataFrame) -> List[str]:
    # flag columns whose name or very-low-variance suggests identifier/timestamp
    cols = []
    for c in df.columns:
        if ID_LIKE_RE.search(c):
            cols.append(c)
        else:
            # also flag near-unique columns (cardinality >> 80% of rows)
            try:
                nunique = df[c].nunique(dropna=True)
                if len(df) > 0 and nunique / max(1, len(df)) > 0.8:
                    cols.append(c)
            except Exception:
                pass
    return list(dict.fromkeys(cols))

def compute_mutual_info(df: pd.DataFrame, label_col: str="Label", numeric_only: bool=True, sample: int=100000, seed: int=0) -> Dict[str,float]:
    # returns mutual information per numeric feature; sample for speed
    df = safe_strip_columns(df)
    if label_col not in df.columns:
        raise KeyError("Label not found")
    n = min(sample, len(df))
    sample_df = df.sample(n=n, random_state=seed) if n < len(df) else df
    y = sample_df[label_col].astype(str).values
    if numeric_only:
        X = sample_df.select_dtypes(include=["number"]).fillna(0.0)
        if X.shape[1] == 0:
            return {}
        mi = mutual_info_classif(X.values, y, discrete_features=False, random_state=seed)
        return dict(zip(X.columns.tolist(), mi.tolist()))
    else:
        # compute for all by converting categoricals to ordinal (cheap)
        X = sample_df.drop(columns=[label_col]).copy()
        for c in X.columns:
            if X[c].dtype == "object":
                X[c] = X[c].astype("category").cat.codes
        X = X.fillna(0.0).select_dtypes(include=["number"])
        if X.shape[1] == 0:
            return {}
        mi = mutual_info_classif(X.values, y, discrete_features=False, random_state=seed)
        return dict(zip(X.columns.tolist(), mi.tolist()))

def remove_constant_features(df: pd.DataFrame, tol: float=0.0) -> List[str]:
    df = safe_strip_columns(df)
    drops = []
    for c in df.columns:
        try:
            if df[c].dropna().shape[0] == 0:
                drops.append(c)
                continue
            std = float(pd.to_numeric(df[c], errors="coerce").std(skipna=True)) if df[c].dtype.kind in "fi" else 0.0
            if std <= tol:
                drops.append(c)
        except Exception:
            continue
    return drops

def remove_highly_correlated(df: pd.DataFrame, numeric_cols: List[str], corr_threshold: float=0.98) -> List[str]:
    if not numeric_cols:
        return []
    numeric_df = df[numeric_cols].select_dtypes(include=["number"]).fillna(0.0)
    corr = numeric_df.corr().abs()
    # upper triangle
    to_drop = set()
    cols = corr.columns
    for i in range(len(cols)):
        for j in range(i+1, len(cols)):
            if corr.iloc[i,j] >= corr_threshold:
                # drop the column with higher mean absolute correlation
                mean_i = corr.iloc[i].mean()
                mean_j = corr.iloc[j].mean()
                drop = cols[i] if mean_i > mean_j else cols[j]
                to_drop.add(drop)
    return list(to_drop)

def safe_feature_selection(df: pd.DataFrame, label_col: str="Label", corr_threshold: float=0.98, const_tol: float=0.0, mi_threshold: float=0.6) -> Dict:

    df = safe_strip_columns(df)
    numeric, categorical = select_numeric_categorical(df)
    dropped = {'id_like': [], 'constant': [], 'correlated': [], 'high_mi_id_like': []}

    # 1) id-like
    dropped['id_like'] = detect_id_like_columns(df)

    # 2) constant
    dropped['constant'] = remove_constant_features(df, tol=const_tol)

    # 3) correlated
    dropped['correlated'] = remove_highly_correlated(df, numeric_cols=numeric, corr_threshold=corr_threshold)

    # 4) mutual information: find numeric features with very high MI and check name
    mi = compute_mutual_info(df, label_col=label_col, numeric_only=True)
    high_mi = [k for k,v in mi.items() if v >= mi_threshold]
    # if any high_mi are id-like or have suspicious names, mark as leakage
    high_mi_id_like = [c for c in high_mi if ID_LIKE_RE.search(c)]
    dropped['high_mi_id_like'] = high_mi_id_like

    # final features: drop union
    to_drop = set(dropped['id_like'] + dropped['constant'] + dropped['correlated'] + dropped['high_mi_id_like'])
    final_features = [c for c in df.columns.tolist() if c not in to_drop and c != label_col]

    return {'final_features': final_features, 'dropped': dropped, 'mi': mi}
