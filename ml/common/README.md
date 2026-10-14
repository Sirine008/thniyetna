# Shared ML conventions

ML experiments should record parameters, metrics, dataset/version metadata and
checkpoint paths. MLflow is optional and runs under the `ml` Compose profile.
Its artifacts are persisted in the `mlflow_artifacts` Docker volume.
