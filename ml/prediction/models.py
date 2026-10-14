"""Model factory for M2 (phases 7-9): baseline -> Random Forest -> XGBoost.

LSTM/GRU are out of scope by design. Every estimator is a scikit-learn
compatible object so evaluation, calibration and explanation are shared.
"""
from __future__ import annotations

from itertools import product

import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import RANDOM_STATE

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:  # pragma: no cover - xgboost is in requirements.txt
    HAS_XGB = False


# ---------------------------------------------------------------- classifiers
def logreg(C: float = 0.5) -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(C=C, max_iter=5000)),
    ])


def random_forest(n_estimators=400, min_samples_leaf=20, max_features="sqrt", max_depth=None) -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", RandomForestClassifier(
            n_estimators=n_estimators, min_samples_leaf=min_samples_leaf, max_features=max_features,
            max_depth=max_depth, n_jobs=-1, random_state=RANDOM_STATE)),
    ])


def xgboost_clf(**params):
    if not HAS_XGB:
        raise ImportError("xgboost is not installed")
    base = dict(
        n_estimators=2000, learning_rate=0.02, max_depth=4, min_child_weight=10,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0, objective="binary:logistic",
        eval_metric="aucpr", early_stopping_rounds=100, tree_method="hist",
        random_state=RANDOM_STATE, n_jobs=-1,
    )
    base.update(params)
    return xgb.XGBClassifier(**base)


CLASSIFIER_GRIDS = {
    "logreg": [{"C": c} for c in (0.05, 0.5, 5.0)],
    "random_forest": [
        {"min_samples_leaf": leaf, "max_features": mf}
        for leaf, mf in product((10, 40), ("sqrt", 0.5))
    ],
    "xgboost": [
        {"max_depth": d, "min_child_weight": mcw}
        for d, mcw in product((3, 5), (5, 20))
    ],
}
CLASSIFIER_FACTORY = {"logreg": logreg, "random_forest": random_forest, "xgboost": xgboost_clf}


def fit_classifier(name: str, params: dict, X_tr, y_tr, X_va=None, y_va=None):
    model = CLASSIFIER_FACTORY[name](**params)
    if name == "xgboost":
        model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
    else:
        model.fit(X_tr, y_tr)
    return model


# ---------------------------------------------------------------- regressors
class RollingMeanBaseline:
    """Naive count forecast: last-30-day daily mean of the same governorate."""

    def __init__(self, column: str = "hist_acc_sum_30", window: int = 30):
        self.column, self.window = column, window

    def fit(self, X, y):  # noqa: D401 - sklearn API
        self.fallback_ = float(np.mean(y))
        return self

    def predict(self, X):
        v = np.asarray(X[self.column], dtype=float) / self.window
        return np.where(np.isnan(v), self.fallback_, v)


def poisson_glm(alpha: float = 1e-3) -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", PoissonRegressor(alpha=alpha, max_iter=3000)),
    ])


def rf_regressor() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", RandomForestRegressor(n_estimators=400, min_samples_leaf=20, max_features=0.5,
                                        n_jobs=-1, random_state=RANDOM_STATE)),
    ])


def xgb_poisson():
    if not HAS_XGB:
        raise ImportError("xgboost is not installed")
    return xgb.XGBRegressor(
        n_estimators=2000, learning_rate=0.02, max_depth=4, min_child_weight=10, subsample=0.8,
        colsample_bytree=0.8, objective="count:poisson", eval_metric="poisson-nloglik",
        early_stopping_rounds=100, tree_method="hist", random_state=RANDOM_STATE, n_jobs=-1,
    )


REGRESSOR_FACTORY = {
    "naive_rolling_mean": RollingMeanBaseline,
    "poisson_glm": poisson_glm,
    "random_forest_reg": rf_regressor,
    "xgboost_poisson": xgb_poisson,
}


def fit_regressor(name: str, X_tr, y_tr, X_va=None, y_va=None):
    model = REGRESSOR_FACTORY[name]()
    if name == "xgboost_poisson":
        model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
    else:
        model.fit(X_tr, y_tr)
    return model
