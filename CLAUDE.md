# THNIYETNA v2 — notes for Claude Code

Road-intelligence platform for Bizerte (Faculté des Sciences de Bizerte, Team 5B).
Five work packages: M1 perception, **M2 risk prediction (Sirine Tiouajni, lead; Ahmed Ghroubi, co-lead)**,
M3 routing, M4 platform, M5 foundation. Contract chain:
`M1 RoadEvent → M2 RiskScore (data/schemas/risk_score.schema.json, v1.1.0) → M3 route → M4 action`.

## Environment
- Windows + PowerShell. Use PowerShell syntax (`$env:VAR = "..."`, `.\.venv\Scripts\Activate.ps1`).
- M2 Python env: `ml/.venv` (Python 3.12), packages from `ml/prediction/requirements.txt` (pinned — the
  shipped model bundle is a pickle, do not upgrade scikit-learn / xgboost / numpy).
- M2 commands run from `ml/` as modules: `python -m prediction.<module>`.
- Stack: `docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 up -d --build`
- DB from the host: `postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5432/thniyetna`
- `.env` at the repo root is already configured (JWT_SECRET, BOOTSTRAP_PASSWORD, DB settings).
  Do not modify it, recreate it from `.env.example`, or print its secret values.
- Raw M2 data lives in `data/external/m2/` (not versioned): `accidents_tn.json`, `weather_reference.xlsx`,
  `tunisia-latest.osm.pbf`. Never commit these files.

## Rules
- Run `pytest -q` (repo root) after any code change; all tests must pass.
- Never invent metrics or results. Report numbers only from files the pipeline wrote
  (`reports/m2/training_report.json`, `reports/m2/ablation.csv`, `docs/M2_MODEL_CARD.md`).
- Before retraining, back up `models/m2/`, `reports/m2/` and `docs/M2_MODEL_CARD.md`
  (copy to `backup/m2-<date>/`), so the previous model can be restored.
- Schema changes go through a new Alembic revision in `backend/alembic/versions/`, never by hand.
- Ask before deleting files or running `docker compose down -v` (it erases the database).
- Keep `risk_scores.risk_score` meaning (0..1) and the RiskScore 1.1.0 contract unchanged.

## M2 open items — runbook

### 1. Weather per governorate experiment
1. `python -m prediction.fetch_weather --start 2022-04-01 --end <today> --out ../data/external/m2/weather_governorates.csv`
   Check: 24 `gov_code`, ~1,650 days each, no empty column.
2. Back up (see Rules), then:
   `$env:M2_WEATHER_FILE = "weather_governorates.csv"; python -m prediction.train train; python -m prediction.train ablation`
3. Compare with the baseline model `2026.10.11-2054`:
   test PR-AUC 0.6111 · ablation `without_weather` Δ +0.0011 · within-governorate median ROC-AUC 0.524.
4. Keep the new model only if test PR-AUC improves and weather now helps in the ablation;
   otherwise restore the backup and record it as a negative result. Write a short comparison table
   in `docs/M2_WEATHER_EXPERIMENT.md`.

### 2. End-to-end run of the M2 worker (never verified)
1. Start the stack (command above); `docker compose ps` must show db, osrm, api, web, m2-worker healthy.
   If the m2-worker build fails, check the `mlflow-skinny==2.16.2` pin first.
2. `$env:DATABASE_URL = "<DB from the host>"; python -m prediction.jobs.ingest all --gov Bizerte --classes motorway,national,regional`
   (+ `python -m prediction.jobs.ingest weather` if per-governorate weather was kept)
3. `python -m prediction.jobs.score --source db --once`
4. Verify: `GET http://localhost:8000/prediction/model` (status ok), `/prediction/governorates` (24 rows with names),
   `/prediction/segments?min_level=high`; web UI `http://localhost:8081` → transport.supervisor "Réseau à risque",
   equipment.supervisor "Priorités d'entretien".

### 3. Mode B condition model (after M1 produces events)
`python -m prediction.condition_model train --source db` — quality gate: ≥ 50 positives and
≥ +0.02 PR-AUC over the rule-based prior, otherwise the prior stays (expected and fine).

### 4. Limits to state in the report (from docs/M2_MODEL_CARD.md)
No accident GPS (segment risk is an exposure allocation) · within-governorate day timing ≈ chance (AUC 0.52) ·
history carries the signal · trees do not beat logistic regression · accident export lags the scoring date.
