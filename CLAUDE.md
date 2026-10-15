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
- DB from the host: `postgresql+psycopg://thniyetna:thniyetna_dev@localhost:5433/thniyetna`
- `.env` at the repo root is already configured (JWT_SECRET, BOOTSTRAP_PASSWORD, DB settings).
  Do not modify it, recreate it from `.env.example`, or print its secret values.
- Raw M2 data lives in `data/external/m2/` (not versioned): `accidents_tn.json`, `weather_reference.xlsx`,
  `tunisia-latest.osm.pbf`. Never commit these files.

## Rules
- Run `pytest -q` (repo root) after any code change; all tests must pass.
- Never invent metrics or results. Report numbers only from files the pipeline wrote
  (`reports/m2/training_report.json`, `reports/m2/ablation.csv`, the model card).
- Model card: `train` / `ablation` regenerate it at `reports/m2/MODEL_CARD.md` (+ `models/m2/model_card.json`).
  They do **not** touch `docs/M2_MODEL_CARD.md`; that copy is only refreshed by
  `python -m prediction.report --md ../docs/M2_MODEL_CARD.md` (run it after a model is kept).
- Before retraining, back up `models/m2/`, `reports/m2/` and `docs/M2_MODEL_CARD.md`
  (copy to `backup/m2-<date>/`), so the previous model can be restored.
- Schema changes go through a new Alembic revision in `backend/alembic/versions/`, never by hand.
- Ask before deleting files or running `docker compose down -v` (it erases the database).
- Keep `risk_scores.risk_score` meaning (0..1) and the RiskScore 1.1.0 contract unchanged.

## M2 open items — runbook

### 1. Weather per governorate experiment
**Done 2026-10-14 — negative result, baseline kept** (see `docs/M2_WEATHER_EXPERIMENT.md`).
1. `python -m prediction.fetch_weather --start 2022-04-01 --end <today> --out ../data/external/m2/weather_governorates.csv`
   Check: 24 `gov_code`, ~1,650 days each, no empty column.
2. Back up (see Rules), then:
   `$env:M2_WEATHER_FILE = "weather_governorates.csv"; python -m prediction.train train; python -m prediction.train ablation`
3. Compare with the baseline model `2026.10.11-2054`:
   test PR-AUC 0.6111 · ablation `without_weather` Δ +0.0011 · within-governorate median ROC-AUC 0.524.
4. Keep the new model only if test PR-AUC improves and weather now helps in the ablation;
   otherwise restore the backup and record it as a negative result. Write a short comparison table
   in `docs/M2_WEATHER_EXPERIMENT.md`.

### 2. End-to-end run of the M2 worker
**Done 2026-10-15.** Stack up (db/api healthy; osrm, web, m2-worker have no healthcheck), 69,394 accidents + reference
weather ingested, one scoring pass writes 675 Bizerte segments + 24 governorate forecasts/day; `/prediction/model` ok,
`/prediction/governorates` 24 named rows, `/prediction/segments` + `/platform/map` serve all 675 segments. All segments
score `low` (max 0.18), so `?min_level=high` is empty; the UI then shows the top 5 % by `exposure_percentile`
(`?top=0.05`, display-only ranking). The worker log's `history_staleness_days` is taken on the last day of the 30-day
segment horizon, while `governorate_risk_forecasts` stores only the first 7 days (17–24 on 2026-10-15) — not a bug. UI screens checked via the built bundle only, not with a logged-in session.
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

### 4. Limits to state in the report (from docs/M2_MODEL_CARD.md, the card of the shipped `2026.10.11-2054`)
No accident GPS (segment risk is an exposure allocation) · within-governorate day timing ≈ chance (AUC 0.52) ·
history carries the signal · trees do not beat logistic regression · accident export lags the scoring date.

## RAG assistant (part A)
- **Audience = field users** (equipment / transport supervisors); developer docs are not indexed. `rag.ingest`
  reads only `data/rag/corpus/**` (field guides; a future user guide also goes there). The `docs/**/*.md` rows
  were deleted on 2026-10-15 (4 guides / 582 chunks remain).
- Ollama on the **Windows host**: LLM `llama3.2:3b`, embeddings `nomic-embed-text` (768 dims). The api reads
  `OLLAMA_URL` / `RAG_LLM_MODEL` / `RAG_EMBED_MODEL` (defaults in `backend/rag/config.py`, documented in `.env.example`).
  If the api cannot reach Ollama, the user sets `OLLAMA_HOST=0.0.0.0` on Windows; do not work around it.
- No torch / sentence-transformers / large downloads (mobile data, CPU only). The only RAG dependency is `pypdf`.
- DB image = `infra/db/Dockerfile` (postgis 16-3.4 + pgvector 0.8.6 from the frozen PGDG **archive**, because
  bullseye-pgdg was removed from apt.postgresql.org). Tables: Alembic `0004_rag` (`rag_documents`, `rag_chunks`
  with HNSW + GIN, `rag_queries` = evaluation log).
- Add documents to `data/rag/corpus/` (never commit them; only its README is versioned), then index (skips unchanged files):
  `docker compose -f docker-compose.yml -f ml/prediction/docker-compose.m2.yml --profile m2 exec api python -m rag.ingest`
- Endpoints (both supervisor roles): `POST /assistant/ask`, `GET /assistant/status`.
- Tests: `tests/test_rag_core.py` runs anywhere; `tests/test_rag_api.py` needs fastapi (skipped in `ml/.venv`,
  run it in the api image).
- First check (2026-10-15, 14 docs / 625 chunks): plumbing works, but both test questions were refused.
  "Limites du modèle M2 ?" → retrieval miss (French question vs English model card; the limits chunk is not in
  the top 4). "Nid-de-poule par temps froid ?" → the cold-mix pages are retrieved, but llama3.2:3b still answers
  the refusal sentence. (Superseded by the A.5/A.6 evaluation below; developer docs are no longer indexed.)
- Evaluation (A.5): `data/rag/eval/questions.jsonl` (16 answerable field questions + 4 unanswerable; DRAFT, to be
  validated by Sirine) and `python -m rag.evaluate --variant <name>` (backend/rag/evaluate.py), run on the host from
  `backend/` with `DATABASE_URL` (host DB) and `OLLAMA_URL=http://localhost:11434`; ~10–15 min per variant, run
  variants one after another. Results: `data/rag/eval/results_<variant>.json`; table rebuilt in
  `docs/RAG_EVALUATION.md` (`--report-only` after editing labels). Answer correctness = manual `label`
  (correct / partial / wrong) on each non-refused answer — never invent labels; read the answer against the source.
- Run so far (2026-10-15): baseline, bilingual, prompt_v2, combined (all labelled). Users ask in French only, so
  bilingual retrieval is dropped (`RAG_BILINGUAL=false`; the llama3.2:3b translations were poor).
  **Pending re-run:** combined_gemma4 (5 questions, only if RAM allows), fts_french, chunk_context,
  confidence_gate, numbers_rule.
- A.6 flags (`backend/rag/config.py`, `.env.example`, passed by docker-compose): defaults
  `RAG_PROMPT_VERSION=v2`, `RAG_NUMBERS_RULE=true`, `RAG_BILINGUAL=false`, `RAG_MIN_SIMILARITY=0` (gate off),
  `RAG_FTS_CONFIG=simple`, `RAG_CHUNK_CONTEXT=false`. Alembic 0005 adds `tsv_fr` ('french' stemming),
  0006 adds `context`, `embedding_ctx`, `tsv_fr_ctx`; after a fresh DB or new documents run
  `docker compose ... exec api python -m rag.ingest --contexts` once (ingest also backfills missing contexts).
- Known issue before re-running chunk_context: the heading heuristic (`rag/context.py`) drops numbered fiche
  section titles (e.g. "4. ÉQUIPEMENTS" repeats on every CERIU fiche, so it is treated as a footer) and takes
  uppercase sign texts ("ROUTE BARREE") as headings; the page header (hot vs warm mix fiche) is correct.
- Gate threshold (confidence_gate): `python -m rag.evaluate --gate-from chunk_context` applies a fixed rule
  (midpoint between the lowest best-similarity of a retrieved answerable question and the highest of an
  unanswerable one) and reports leave-one-out next to the in-sample result. It is tuned on the evaluation set;
  say so, and set the value in `VARIANTS` for confidence_gate / numbers_rule before running them.
- `/assistant` responses declare `application/json; charset=utf-8` (PowerShell 5.1 mojibake fixed).
- Part B (UI for field users, French only): tab "Assistant" in both ministries (`frontend/src/components/Assistant.jsx`,
  last 5 Q&A kept in sessionStorage) and "Fiche d'intervention" on the rows of "Priorités d'entretien"
  (`InterventionSheet.jsx`, printable). `POST /assistant/intervention/{segment_code}` (equipment_supervisor,
  `backend/rag/intervention.py`): Constat / Priorité / Données manquantes come from the DB by template (numbers as
  stored, never by the LLM); advice sections come from 6 retrieved chunks with [n]; a section without citation is
  flagged `uncited` and shown with a warning. No defect on the segment → only "Conseils d'inspection". Ollama down →
  the DB sections are still returned (`assistant_available: false`). Sources carry a 400-char `excerpt`
  (`/ask` too). nginx `/api/assistant/` has `proxy_read_timeout 300s` (a sheet took 58 s on a cold model).
- Live check 2026-10-15 (equipment.supervisor, OSM-100663969, P3, no defect): the sheet is correct, but its advice
  had no [n] (now flagged). `/ask` "température minimale enrobé chaud" answered "0 °C" (wrong, same failure as eval
  q12; the guides say > 10 °C) — the excerpts and the notice are there so users can catch it.
