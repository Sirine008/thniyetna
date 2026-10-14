# THNIYETNA — M2 Risk Prediction package (2026-10-11)

Unzip at the root of `thnyetna-v2-main/`: every file lands at its repository path.

## Files that REPLACE existing ones
- `ml/prediction/README.md`, `baseline.py`, `explain.py`, `xgboost_model.py`, `requirements.txt`
- `backend/prediction/router.py`, `backend/prediction/schemas.py` (all previous endpoints kept)
- `data/schemas/risk_score.schema.json` (now RiskScore 1.1.0)
- `docs/work-packages/M2.md`
- `.github/workflows/ci.yml` (installs the M2 requirements before `pytest`)
- `.gitignore` (original content + M2 section)

## New files
- `ml/prediction/**` (pipeline, jobs, tests, Dockerfile, `docker-compose.m2.yml`)
- `backend/alembic/versions/0003_m2_risk_model.py` (additive migration, applied automatically on API start)
- `models/m2/` (trained bundle, `current.json`, `model_card.json`)
- `reports/m2/` (metrics, ablation, SHAP plots, MLflow store `mlruns.db`, samples)
- `data/processed/m2/` (governorate road statistics + polygons from OSM)
- `data/external/m2/README.md` (where to put the raw files — not shipped)
- `docs/M2_MODEL_CARD.md`

`docker-compose.yml` is NOT modified: M2 is added with
`docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 up -d --build`.

## Verified before packaging
- `pytest -q` on the merged repository: 43 passed.
- Alembic `upgrade head` 0001 → 0002 → 0003 on PostgreSQL 16 + PostGIS 3.4.
- `jobs.ingest all` + `jobs.score --source db` on Bizerte (675 segments, 2 M1 events, 1 complaint).
- API via TestClient: `/prediction/model`, `/governorates`, `/segments`, `POST /risk`,
  `/risk/{id}/contract` (validated against the schema), and `/platform/map` (M4) still reads the scores.

Not verified here: the Docker build of the m2-worker, the Open-Meteo fetcher (no internet in the
build environment) and the `mlflow-skinny==2.16.2` client pin (runs were logged with MLflow 3.17
against a local SQLite store).
