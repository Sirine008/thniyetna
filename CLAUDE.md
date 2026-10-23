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
- Tests: `ml\.venv\Scripts\python.exe -m pytest -q` (repo root) after any code change; all tests must pass. Test dependencies (fastapi,
  python-jose... = the API's) come from `requirements-dev.txt`, installed once in the M2 venv:
  `ml\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`. Expected: 0 skips except M1's `cv2` test
  (OpenCV only exists in the perception worker image). Do not use a bare `pytest` from PATH (another Python without
  the API packages). Frontend: `npm test` in `frontend/` (node --test, `src/lib/routeState.js`) and `npm run build`.
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

## M1 perception (pretrained, since 2026-10-23)
- Model: public `dronefreak/rdd2022-yolo26s` (AGPL-3.0) → `models/road-damage-yolo26s.pt` via
  `python scripts/download_m1_model.py`; check with `scripts/check_m1_model.py` in the worker image. CPU only
  (the Dockerfile installs CPU torch first). Card: `docs/M1_MODEL_CARD.md` (published metrics are the author's, not ours).
- Start: `docker compose ... --profile m2 --profile m1 up -d --build perception-worker`. Pilot/benchmark run in the
  worker image (`perception.pilot`, `perception.benchmark --source`), not in `ml/.venv` (no torch there).
- Pilot photos `data/m1/pilot/` and outputs `data/m1/pilot_out/` are gitignored; never commit them.
- Known: potholes in close-up citizen photos are missed (0/7 on the pilot). Do not claim local accuracy.

## Demo data (scripts/seed_demo.py)
- Needs the stack with `--profile m2 --profile m1` (perception-worker) and photos in `data/m1/pilot/`. Run from the repo
  root with the M2 venv (it calls `prediction.jobs.score`):
  - seed (idempotent): `ml\.venv\Scripts\python.exe -X utf8 scripts/seed_demo.py`
  - reset (lists demo rows, asks `yes`, deletes only them + their media, then one normal M2 pass):
    `ml\.venv\Scripts\python.exe -X utf8 scripts/seed_demo.py --reset`
  - `--summary` prints the DB summary; `--rescore` forces the M2 pass. Route checks always run (the API keeps one
    active alert per driver and line, so re-running does not duplicate alerts).
  - Layout (23/10): L1 -> reroute (2 hazards on OSM-125567491, which has a road around it), L2 -> warning (own hazard on
    OSM-116022841, no road around; L2 also passes L1's stretch), L3/L4 -> no hazard; reports >= 2 km from every line.
- Everything goes through the API (OSRM lines, M1 worker, validation, `/routing/driver/next-best`) and the normal
  M2 job; the script only adds the demo tag and, on reset, deletes demo rows. Never insert scores/routes/alerts by hand.
- Demo rows: usernames `demo.*`; `metadata.demo` / `payload.demo` / `options.demo` = true elsewhere. The API exposes
  `demo` and the UI shows "DÉMO — données fictives". M2 training excludes them (`condition_model.TRAINING_EVENTS_SQL`,
  `drop_demo`, test `test_demo_events_are_excluded_from_condition_training`).
- Passwords: `data/demo/demo_accounts.json` (gitignored); never print or commit them.

## M3 destination search (place index, since 2026-10-23)
- Citizen page « Carte des incidents · Bizerte » (`frontend/src/pages/Citizen.jsx`, `components/PlaceSearch.jsx`):
  free destination = autocomplete search, a map click (nearest place name shown) or the 3 shortcut buttons; start =
  « Ma position » (browser geolocation), « Carte » (next map click) or the Bizerte centre by default. M3 logic unchanged.
- Table `places` (Alembic `0007_places_index`, extension `pg_trgm`): name (name:fr preferred), name_ar, name_norm
  (normalised search key of every name variant), category, rank, locality (nearest town / village), point geom.
  Normalisation (`backend/routing/places_index.py`, shared by the API and the script): case, accents, punctuation,
  ligatures, Arabic diacritics and letter variants (أ/ا, ة/ه, ى/ي), so « menzel bourguiba » = « Ménzel-Bourguiba » = « منزل بورقيبة ».
- Build / rebuild (after `scripts/osm-clip-bizerte.sh` or a fresh DB; idempotent, replaces the table), from the repo
  root with the M2 venv (pyosmium) and the host DB:
  `$env:DATABASE_URL = "<DB from the host>"; ml\.venv\Scripts\python.exe -X utf8 scripts/build_places_index.py`
  (`--dry-run` = counts only). Keeps points inside TN-23 (`admin_areas`, 300 m tolerance): 711 rows on 2026-10-23
  (441 streets, 64 schools, 46 villages, 6 towns/city, 5 hospitals, 5 ports...); OSM coverage of streets is sparse.
- API: `GET /routing/places?q=...&limit=8` (name, category in French, category_key, lat, lon, name_ar?, locality?;
  503 if the table is missing) and `GET /routing/places/nearest?lat=&lon=` (place within 3 km, `covered`).
- Coverage: `POST /routing/route` answers 422 « Destination hors de la zone couverte (gouvernorat de Bizerte) »
  (or « Point de départ hors… ») when a point is outside TN-23 + 2 km (the OSRM extract), when OSRM returns
  NoSegment / NoRoute, or when OSRM snaps a point more than 1.5 km away (e.g. Lake Ichkeul, the sea).
- Result card (`frontend/src/lib/routeState.js`, wording of the driver alerts): safe « Trajet vérifié · aucun danger
  significatif » (green) / reroute « Alternative plus sûre recommandée », risque A % → B % + dangers évités / warning
  « Danger sur l’itinéraire — aucune alternative sûre » (red) with each hazard (type in French, distance from the start
  = `hazards[].distance_from_start_m`, risk). Never « vérifié » when `fastest_risk` >= 0.42.
- Tests: `tests/test_routing_places.py`, `tests/test_routing_event_reroute.py` (warning card data), `npm test`.

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
- Tests: `tests/test_rag_core.py` runs anywhere; `tests/test_rag_api.py` needs fastapi (installed in `ml/.venv`
  from `requirements-dev.txt`).
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
