# M2 experiment — weather per governorate (negative result)

Date: 2026-10-14 · Baseline: `m2-risk:2026.10.11-2054` · Experiment: `m2-risk:2026.10.14-1857`
· **Decision: baseline kept, experiment model not deployed.**

## Question
The baseline uses one Meteostat reference station for all 24 governorates, and its ablation shows
weather does not help (`without_weather` Δ PR-AUC +0.0011). Does a separate weather series for each
governorate (Open-Meteo ERA5 archive, one representative point per OSM governorate polygon) change that?

## Data
| | Baseline | Experiment |
|---|---|---|
| Weather file | `weather_reference.xlsx` (1 station) | `weather_governorates.csv` (24 gov. × 1,658 days, no missing values) |
| Weather window | 2022-04-01 → 2026-10-08 | 2022-04-01 → 2026-10-14 |
| Weather SHA-256 prefix | `053bb61284593aad` | `bace8f9590299a80` |
| Accidents | 69,394 records, 2015-01-01 → 2026-09-27 (`dd778fbccfb4b02f`) | same |
| Panel | 39,360 governorate-days, 2022-04-02 → 2026-09-27 | same |
| Split | train ≤ 2023-12-31 · val ≤ 2024-12-31 · test → 2026-09-27 | same |

Only the weather input changed. Feature set (50 features), split and model grids are identical.

## Results (test period)
Source: `reports/m2/training_report.json`, `ablation.csv`, `test_metrics_per_governorate.csv` of each run.

| Metric | Baseline `2026.10.11-2054` | Experiment `2026.10.14-1857` | Δ |
|---|---|---|---|
| Chosen classifier | logreg | logreg | — |
| **Test PR-AUC** (calibrated) | 0.6111 | 0.6100 | −0.0011 |
| **Test F1** (calibrated, threshold) | 0.6119 @ 0.31 | 0.6121 @ 0.29 | +0.0002 |
| Test ROC-AUC | 0.6829 | 0.6824 | −0.0005 |
| Validation PR-AUC | 0.6567 | 0.6561 | −0.0006 |
| **Ablation `without_weather` Δ PR-AUC** | +0.0011 | +0.0022 | — |
| Ablation `only_weather` PR-AUC | 0.4043 | 0.4429 | +0.0386 |
| **Within-governorate median ROC-AUC** (24 gov.) | 0.5241 | 0.5187 | −0.0054 |
| Fatal-accident PR-AUC | 0.1961 | 0.1953 | −0.0008 |
| Count model (xgboost_poisson) test Poisson deviance | 0.9959 | 0.9950 | −0.0009 |

## Decision
Keep criteria (CLAUDE.md runbook): test PR-AUC improves **and** weather helps in the ablation.
Both fail:
- **Test PR-AUC:** it dropped slightly (0.6111 → 0.6100).
- **Weather in the ablation:** removing weather still *raises* PR-AUC, now by +0.0022.

Per-governorate weather does carry more signal on its own (`only_weather` 0.40 → 0.44). But none of it
adds to the accident history, which remains the dominant feature group (`without_history` Δ ≈ −0.03 in
both runs). Within-governorate day timing stays at chance level.
The baseline model was restored.

## Commands
PowerShell, run from `ml/` with `ml\.venv` (Python 3.12.10, pinned `requirements.txt`):

```powershell
.\.venv\Scripts\python.exe -m prediction.fetch_weather --start 2022-04-01 --end 2026-10-14 --out ..\data\external\m2\weather_governorates.csv
# backup of models/m2, reports/m2, docs/M2_MODEL_CARD.md -> backup/m2-2026-10-14/
$env:M2_WEATHER_FILE = "weather_governorates.csv"
.\.venv\Scripts\python.exe -m prediction.train train --no-mlflow
.\.venv\Scripts\python.exe -m prediction.train ablation --no-mlflow
```

**`--no-mlflow` note:** the first `train` attempt failed before writing any output, with
`ModuleNotFoundError: No module named 'alembic'`. `mlflow-skinny` does not install alembic, but the
local SQLite tracking store (`sqlite:///mlruns.db`, used when `MLFLOW_TRACKING_URI` is empty) needs it.
Both runs were therefore logged as JSON run records instead of MLflow, and the experiment has no
MLflow run ID. `alembic==1.14.0` has since been added to `ml/prediction/requirements.txt`, and the SQLite
store was checked to work with it.

## Artifacts
- Experiment weather input, kept for a re-run: `data/external/m2/weather_governorates.csv` (not versioned).
- Experiment outputs: `backup/m2-2026-10-14-weather-experiment/` (not versioned):
  - `models/m2/` — the `2026.10.14-1857` bundle, its `current.json` and `model_card.json`
  - `reports/m2/` — `training_report.json`, `ablation.csv`, `test_metrics_per_governorate.csv`,
    `MODEL_CARD.md`, and the 2 JSON run records
- Pre-experiment backup (identical to the restored state): `backup/m2-2026-10-14/`.
- `data/processed/m2/panel_governorate_day.parquet` (gitignored) was last written by the experiment run.
  Nothing reads it, and `train` / `ablation` rebuild it.
