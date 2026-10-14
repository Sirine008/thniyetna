"""Metrics shared by every M2 experiment."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, brier_score_loss, f1_score, log_loss, mean_absolute_error,
    mean_poisson_deviance, mean_squared_error, precision_score, r2_score, recall_score,
    roc_auc_score,
)


def best_f1_threshold(y_true, proba) -> float:
    grid = np.round(np.arange(0.05, 0.951, 0.01), 2)
    scores = [f1_score(y_true, proba >= t, zero_division=0) for t in grid]
    return float(grid[int(np.argmax(scores))])


def classification_metrics(y_true, proba, threshold: float) -> dict:
    y_true = np.asarray(y_true)
    proba = np.clip(np.asarray(proba, dtype=float), 1e-6, 1 - 1e-6)
    pred = proba >= threshold
    return {
        "n": int(len(y_true)),
        "base_rate": float(y_true.mean()),
        "threshold": float(threshold),
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "brier": float(brier_score_loss(y_true, proba)),
        "log_loss": float(log_loss(y_true, proba)),
    }


def regression_metrics(y_true, pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    pred = np.clip(np.asarray(pred, dtype=float), 1e-6, None)
    return {
        "n": int(len(y_true)),
        "mae": float(mean_absolute_error(y_true, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, pred))),
        "r2": float(r2_score(y_true, pred)),
        "poisson_deviance": float(mean_poisson_deviance(y_true, pred)),
    }


def calibration_table(y_true, proba, bins: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"y": np.asarray(y_true), "p": np.asarray(proba)})
    df["bin"] = pd.qcut(df["p"], q=bins, duplicates="drop")
    t = df.groupby("bin", observed=True).agg(mean_pred=("p", "mean"), observed=("y", "mean"), n=("y", "size"))
    return t.reset_index(drop=True)


def per_group_metrics(df: pd.DataFrame, y_col: str, p_col: str, group: str = "gov_code") -> pd.DataFrame:
    rows = []
    for g, d in df.groupby(group):
        if d[y_col].nunique() < 2:
            continue
        rows.append({group: g, "n": len(d), "base_rate": d[y_col].mean(),
                     "roc_auc": roc_auc_score(d[y_col], d[p_col]),
                     "pr_auc": average_precision_score(d[y_col], d[p_col])})
    return pd.DataFrame(rows)
