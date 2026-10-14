"""Explainability (phase 10): per-prediction and global feature contributions.

Contributions are returned in log-odds units of the *base* (uncalibrated) model,
which is what the RiskScore contract's `top_factors[].contribution` expects:
  * XGBoost  -> exact TreeSHAP via the booster (`pred_contribs=True`)
  * logistic -> exact linear SHAP: coef * (standardised x - training mean (=0))
  * random forest -> shap.TreeExplainer if the `shap` package is installed
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _kind(model) -> str:
    name = type(model).__name__
    if name == "XGBClassifier":
        return "xgboost"
    if hasattr(model, "named_steps"):
        last = model.named_steps["model"]
        return {"LogisticRegression": "logreg", "RandomForestClassifier": "random_forest"}.get(type(last).__name__, "other")
    return "other"


def contributions(model, X: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, str]:
    """Return (contributions DataFrame, base value per row, unit)."""
    kind = _kind(model)
    cols = list(X.columns)
    if kind == "xgboost":
        import xgboost as xgb
        dm = xgb.DMatrix(X, feature_names=cols)
        raw = model.get_booster().predict(dm, pred_contribs=True)
        return pd.DataFrame(raw[:, :-1], columns=cols, index=X.index), raw[:, -1], "log_odds"
    if kind == "logreg":
        imp, sc, lr = model.named_steps["impute"], model.named_steps["scale"], model.named_steps["model"]
        xs = sc.transform(imp.transform(X))
        contrib = xs * lr.coef_[0]
        return pd.DataFrame(contrib, columns=cols, index=X.index), np.full(len(X), lr.intercept_[0]), "log_odds"
    if kind == "random_forest":
        import shap  # optional
        imp, rf = model.named_steps["impute"], model.named_steps["model"]
        Xi = pd.DataFrame(imp.transform(X), columns=cols, index=X.index)
        ex = shap.TreeExplainer(rf)
        sv = ex.shap_values(Xi, check_additivity=False)
        sv = sv[1] if isinstance(sv, list) else (sv[..., 1] if sv.ndim == 3 else sv)
        base = ex.expected_value[1] if np.ndim(ex.expected_value) else ex.expected_value
        return pd.DataFrame(sv, columns=cols, index=X.index), np.full(len(X), base), "probability"
    raise ValueError(f"No explainer for model type {type(model).__name__}")


def top_factors(contrib_row: pd.Series, values_row: pd.Series, k: int = 5) -> list[dict]:
    order = contrib_row.abs().sort_values(ascending=False).index[:k]
    out = []
    for f in order:
        v = values_row.get(f)
        if isinstance(v, (np.floating, np.integer)):
            v = v.item()
        if isinstance(v, float) and np.isnan(v):
            v = None
        out.append({"feature": f, "contribution": round(float(contrib_row[f]), 4), "value": v})
    return out


def global_importance(model, X: pd.DataFrame) -> pd.DataFrame:
    c, _, unit = contributions(model, X)
    imp = c.abs().mean().sort_values(ascending=False)
    signed = c.mean()
    return pd.DataFrame({"feature": imp.index, "mean_abs_contribution": imp.values,
                         "mean_signed_contribution": signed[imp.index].values, "unit": unit})


def save_importance_plot(imp: pd.DataFrame, path: str | Path, title: str, top: int = 20) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = imp.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.35 * len(d) + 1.2))
    colors = ["#c0392b" if s > 0 else "#2471a3" for s in d["mean_signed_contribution"]]
    ax.barh(d["feature"], d["mean_abs_contribution"], color=colors)
    ax.set_xlabel(f"mean |contribution| ({d['unit'].iloc[0]})")
    ax.set_title(title)
    fig.tight_layout()
    path = Path(path)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def save_beeswarm(model, X: pd.DataFrame, path: str | Path, max_rows: int = 3000) -> Path | None:
    """SHAP beeswarm summary (requires the optional `shap` package)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import shap
    except ImportError:
        return None
    Xs = X.sample(min(max_rows, len(X)), random_state=0)
    c, base, _ = contributions(model, Xs)
    exp = shap.Explanation(values=c.to_numpy(), base_values=base, data=Xs.to_numpy(), feature_names=list(Xs.columns))
    shap.plots.beeswarm(exp, max_display=20, show=False)
    plt.tight_layout()
    plt.savefig(path, dpi=130)
    plt.close("all")
    return Path(path)
