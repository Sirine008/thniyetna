"""Versioned model bundle: everything inference needs, in one joblib file.

models/m2/
  m2-risk-<version>.joblib    the bundle
  current.json                pointer {"version": ..., "file": ...} read by the worker/API
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .config import MODEL_DIR, MODEL_NAME


class PlattCalibrator:
    """Monotone sigmoid recalibration on the logit of the base probability.

    Unlike isotonic regression it creates no ties, so ranking metrics
    (ROC-AUC / PR-AUC) are preserved exactly while probabilities are corrected.
    """

    def fit(self, proba, y):
        from sklearn.linear_model import LogisticRegression
        z = _logit(proba).reshape(-1, 1)
        self.lr_ = LogisticRegression(C=1e6, max_iter=1000).fit(z, np.asarray(y))
        return self

    def predict(self, proba):
        return self.lr_.predict_proba(_logit(proba).reshape(-1, 1))[:, 1]


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


_XGB_KEY = "__xgboost_ubj__"


def _pack_xgb(model):
    """XGBoost estimators are stored as params + native UBJSON model.

    A pickled Booster embeds a platform-specific RNG state, so a bundle trained
    on Linux fails to load on Windows (and vice versa) with "input stream corrupted".
    """
    if type(model).__module__.split(".")[0] != "xgboost":
        return model
    return {_XGB_KEY: type(model).__name__, "params": model.get_params(),
            "raw": bytes(model.get_booster().save_raw("ubj"))}


def _unpack_xgb(obj):
    if not (isinstance(obj, dict) and _XGB_KEY in obj):
        return obj
    import xgboost as xgb
    model = getattr(xgb, obj[_XGB_KEY])(**obj["params"])
    model.load_model(bytearray(obj["raw"]))
    return model


@dataclass
class ModelBundle:
    version: str
    features: list[str]
    feature_groups: dict[str, list[str]]
    classifier: object                  # P(>=1 accident in governorate on day t)
    classifier_name: str
    calibrator: object | None           # PlattCalibrator: base proba -> calibrated proba
    threshold: float                    # alert threshold on calibrated proba (max-F1 on validation)
    count_model: object                 # E[#accidents in governorate on day t]
    count_model_name: str
    fatal_classifier: object | None = None  # P(>=1 fatal accident)
    fatal_calibrator: object | None = None
    road_class_weights: dict[str, float] = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    mlflow_run_id: str | None = None

    # ----------------------------------------------------------- persistence
    def __getstate__(self):
        return {k: _pack_xgb(v) for k, v in self.__dict__.items()}

    def __setstate__(self, state):
        self.__dict__.update({k: _unpack_xgb(v) for k, v in state.items()})

    # ------------------------------------------------------------- inference
    def _X(self, df: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in self.features if c not in df.columns]
        if missing:
            raise KeyError(f"Missing features for inference: {missing[:5]}...")
        return df[self.features].astype(float)

    def base_proba(self, df: pd.DataFrame) -> np.ndarray:
        return self.classifier.predict_proba(self._X(df))[:, 1]

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        p = self.base_proba(df)
        if self.calibrator is not None:
            p = self.calibrator.predict(p)
        return np.clip(p, 1e-4, 1 - 1e-4)

    def predict_count(self, df: pd.DataFrame) -> np.ndarray:
        return np.clip(self.count_model.predict(self._X(df)), 0, None)

    def predict_fatal_proba(self, df: pd.DataFrame) -> np.ndarray | None:
        if self.fatal_classifier is None:
            return None
        p = self.fatal_classifier.predict_proba(self._X(df))[:, 1]
        if self.fatal_calibrator is not None:
            p = self.fatal_calibrator.predict(p)
        return np.clip(p, 1e-4, 1 - 1e-4)

    @property
    def model_id(self) -> str:
        return f"{MODEL_NAME}:{self.version}"


def save_bundle(bundle: ModelBundle, model_dir: Path | None = None, make_current: bool = True) -> Path:
    model_dir = Path(model_dir or MODEL_DIR)
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"{MODEL_NAME}-{bundle.version}.joblib"
    joblib.dump(bundle, path, compress=3)
    if make_current:
        (model_dir / "current.json").write_text(json.dumps({
            "name": MODEL_NAME, "version": bundle.version, "file": path.name,
            "classifier": bundle.classifier_name, "count_model": bundle.count_model_name,
            "mlflow_run_id": bundle.mlflow_run_id, "threshold": bundle.threshold,
        }, indent=2))
    return path


def load_bundle(model_dir: Path | None = None, version: str | None = None) -> ModelBundle:
    model_dir = Path(model_dir or MODEL_DIR)
    if version is None:
        pointer = model_dir / "current.json"
        if not pointer.exists():
            raise FileNotFoundError(f"No trained M2 model in {model_dir} (run `python -m prediction.train all`)")
        file = json.loads(pointer.read_text())["file"]
    else:
        file = f"{MODEL_NAME}-{version}.joblib"
    return joblib.load(model_dir / file)
