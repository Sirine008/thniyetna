"""Experiment tracking (phase 12).

Uses MLflow when it is installed (the `ml` Compose profile, or a local ./mlruns
SQLite store ./mlruns.db when MLFLOW_TRACKING_URI is empty). Without MLflow, the same calls write a
JSON run record under reports/m2/runs/ so every experiment stays reproducible.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .config import MLFLOW_EXPERIMENT, MLFLOW_TRACKING_URI, REPORT_DIR, REPO_ROOT

try:
    import mlflow
    HAS_MLFLOW = True
except ImportError:
    HAS_MLFLOW = False


def _flat(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        elif isinstance(v, (int, float)) and v is not None:
            out[key] = float(v)
    return out


class Run:
    def __init__(self, name: str, backend: str):
        self.name, self.backend = name, backend
        self.id = uuid.uuid4().hex
        self.record: dict = {"run_name": name, "params": {}, "metrics": {}, "tags": {}, "artifacts": [],
                             "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    def log_params(self, params: dict):
        clean = {k: str(v)[:250] for k, v in params.items()}
        self.record["params"].update(clean)
        if self.backend == "mlflow":
            mlflow.log_params(clean)

    def log_metrics(self, metrics: dict, prefix: str = ""):
        flat = _flat(metrics, prefix)
        self.record["metrics"].update(flat)
        if self.backend == "mlflow":
            mlflow.log_metrics({k.replace("@", "_at_"): v for k, v in flat.items()})

    def set_tags(self, tags: dict):
        self.record["tags"].update({k: str(v) for k, v in tags.items()})
        if self.backend == "mlflow":
            mlflow.set_tags(tags)

    def log_artifact(self, path: str | Path):
        self.record["artifacts"].append(str(path))
        if self.backend == "mlflow":
            mlflow.log_artifact(str(path))


@contextmanager
def start_run(name: str, use_mlflow: bool = True):
    backend = "mlflow" if (use_mlflow and HAS_MLFLOW) else "json"
    run = Run(name, backend)
    if backend == "mlflow":
        uri = MLFLOW_TRACKING_URI or f"sqlite:///{REPO_ROOT / 'mlruns.db'}"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        with mlflow.start_run(run_name=name) as active:
            run.id = active.info.run_id
            run.record["tracking_uri"] = uri
            yield run
    else:
        yield run
    run.record["run_id"] = run.id
    run.record["backend"] = backend
    run.record["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out = REPORT_DIR / "runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{time.strftime('%Y%m%d-%H%M%S')}_{name}.json").write_text(json.dumps(run.record, indent=2, ensure_ascii=False))
