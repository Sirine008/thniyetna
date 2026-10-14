"""
Small MLflow helper so every training script logs runs the same way.
"""
import mlflow

from apps.api.shared.config import MLFLOW_TRACKING_URI  # adjust import path per your setup


def start_run(experiment_name: str, run_name: str | None = None):
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experiment_name)
    return mlflow.start_run(run_name=run_name)
