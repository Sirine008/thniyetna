# M2 — Road Condition & Risk Prediction

Owner: Sirine Tiouajni (Technical Lead), Ahmed Ghroubi (Technical Co-Lead).

M2 turns accident history, weather, the OSM road network and M1 road events into
a **RiskScore per road segment** (contract: `data/schemas/risk_score.schema.json`,
v1.1.0) consumed by M3 (routing cost) and M4 (map, dashboards, maintenance).

```
accidents (2015→) ─┐
weather (daily) ───┼─► governorate × day panel ─► LR / RF / XGBoost ─► P(accident), E[#accidents], P(fatal)
OSM road stats ────┘        (features at t-1)        (MLflow, SHAP)            │
                                                                                ▼
OSM / road_segments ──► exposure thinning (length × learned class weight) ─► P_accident(segment)
M1 RoadEvents + complaints ──► condition prior  (or learned condition_model) ─► P_condition(segment)
                                                                                ▼
                         risk_score = 1 − (1 − P_accident)(1 − P_condition)  → risk_level, factors,
                         predicted_condition, maintenance_priority  → risk_scores (PostGIS) → API
```

Mode A (now): public Tunisian data only, no M1. Mode B (later): M1 events and
validation statuses feed the condition component; `condition_model.py` learns
from their history. **Same code path, same contract** — only the inputs change.

## Layout

| File | Role |
|---|---|
| `config.py` | paths, governorate reference (ISO 3166-2:TN), splits, risk levels |
| `io_accidents.py` / `io_weather.py` / `io_osm.py` | loaders (Arabic export, Meteostat/Open-Meteo, Geofabrik PBF) |
| `calendar_tn.py` | Tunisian holidays, Ramadan, Eid |
| `features.py` | leakage-safe panel (`build_training_panel`, `build_inference_frame`) |
| `models.py` | logistic baseline, Random Forest, XGBoost, count models |
| `train.py` | phases 5–12: panel → models → calibration → SHAP → MLflow → bundle; ablation |
| `explain.py` | log-odds contributions (exact TreeSHAP / linear SHAP), plots |
| `registry.py` | versioned model bundle + `current.json` pointer |
| `segment_risk.py` | segment RiskScore (accident + condition components) |
| `condition_model.py` | Mode B learned condition model with a quality gate |
| `contract.py` | JSON-schema validation of every RiskScore |
| `predict.py` | file-based CLI (governorate forecast, segment scoring, GeoJSON) |
| `jobs/ingest.py` | load accidents, weather, governorates, OSM segments into PostGIS |
| `jobs/score.py` | scoring worker (DB or files) → `risk_scores`, `governorate_risk_forecasts`, outbox |
| `fetch_weather.py` | per-governorate weather from Open-Meteo (next experiment) |
| `report.py` | model card (`docs/M2_MODEL_CARD.md`, `models/m2/model_card.json`) |

## Run it

```bash
cd ml
pip install -r prediction/requirements.txt
# raw files in data/external/m2/ (see its README)

python -m prediction.train all            # OSM extract (~1.5 min) + train (~2.5 min) + ablation + model card
python -m prediction.predict governorate --gov Bizerte,Tunis --date 2026-09-28 --days 3
python -m prediction.predict segments --gov Bizerte --classes motorway,national,regional \
       --events ../reports/m2/samples/m1_events_sample.json --out bizerte.geojson
pytest -q prediction/tests                # 43 tests incl. the leakage test
```

With the stack (PostGIS + API running, migration `0003_m2_risk_model` applied by the API entrypoint):

```bash
export DATABASE_URL=postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5432/thniyetna
python -m prediction.jobs.ingest all --gov Bizerte --classes motorway,national,regional
python -m prediction.jobs.score --source db --once
# or as a service:
docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 up -d --build
```

API (`/prediction`, served from the batch, contextual-v1 kept as fallback):
`POST /risk`, `GET /risk/{segment}`, `GET /risk/{segment}/contract`,
`GET /segments?min_level=high`, `GET /governorates?day=…`, `GET /model`.

## Compatibility notes for M3 / M4

- `risk_scores.risk_score` keeps its meaning (0..1). M3 now reads it for every segment a candidate
  route follows (model score preferred over a contextual-v1 row, expired scores ignored).
- `risk_scores.risk_category` keeps the legacy 3 values (critical is stored as `high`)
  so `Ministry.jsx` and the platform stats keep working; the 4-level contract value is in
  the new `risk_level` column. M4 reads `risk_level` (falls back to `risk_category` for contextual rows).
- Contract 1.1.0 changes `segment_id` to a string because `road_segments.id` is a UUID
  (1.0.0 said integer) — to be confirmed with M3/M4.

Results and limits: see `docs/M2_MODEL_CARD.md`.
