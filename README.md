# THNIYETNA v2

THNIYETNA is a road-intelligence and maintenance platform built around five work packages:

- **M1 Perception** — road-damage detection from citizen images and inspection videos.
- **M2 Risk** — segment risk scoring and prioritization.
- **M3 Routing** — OSRM routing plus risk-aware next-best-route selection.
- **M4 Platform** — citizen, driver, Equipment and Transport workflows.
- **M5 Foundation** — PostGIS, FastAPI, Alembic, realtime events, Docker and MLOps support.

This repository is the clean implementation baseline. There is no MinIO service, no demo seed container and no PowerShell-specific project script.

## Repository layout

```text
backend/                  FastAPI API + Alembic migrations
frontend/                 React/Vite web application
ml/perception/            M1 training, inference, benchmark and worker
ml/prediction/            M2 experimental/model code
data/osm/                 Bizerte OSM/OSRM graph
models/                   validated M1 model checkpoint
infra/                    optional MLflow / monitoring support
scripts/                  operational helper scripts
docs/                     architecture and work-package documentation
tests/                    repository/contract tests
```

## Core runtime

A normal start launches:

```text
PostgreSQL/PostGIS
        ↓
FastAPI startup → Alembic upgrade head
        ↓
FastAPI API ←→ OSRM
        ↓
React/Vite web UI through Nginx
```

M1 and MLflow are optional profiles because M1 requires a validated model checkpoint and MLflow is not required to run the product.

## Clean first run

Create `.env`:

```powershell
Copy-Item .env.example .env
```

Change at least:

```text
JWT_SECRET=<long random secret>
BOOTSTRAP_PASSWORD=<password for operational staff accounts>
```

For a completely fresh database:

```powershell
docker compose down -v --remove-orphans
docker compose build
docker compose up -d
docker compose ps
```

Open:

- Web: `http://localhost:8081`
- API health: `http://localhost:8000/health`
- API readiness: `http://localhost:8000/system/ready`
- Swagger: `http://localhost:8000/docs`
- OSRM: `http://localhost:5002`

## Authentication

There is no demo seed. Authentication is part of the backend.

Citizens create their own account from the web login/register page or through:

```text
POST /auth/register
```

Alembic creates the minimum operational identities when migration `0002_bootstrap_accounts` is first applied:

| Role | Username |
|---|---|
| Driver | `driver.srtb` |
| Equipment supervisor | `equipment.supervisor` |
| Transport supervisor | `transport.supervisor` |
| Inspection vehicle | `inspection.vehicle` |

Their initial password is the value of `BOOTSTRAP_PASSWORD` in `.env` at the time the migration is applied.

Login is:

```text
POST /auth/login
```

The frontend stores the returned JWT locally and sends it as a Bearer token to protected endpoints. There is no hidden auto-login and no hard-coded `demo123` credential.

## Routing and next-best route

OSRM is a core service and starts with the normal Compose stack. M3:

1. asks OSRM for the fastest route and alternatives;
2. reads active `road_events` and unresolved road-damage complaints from PostGIS;
3. measures each route's spatial exposure to those hazards;
4. computes a composite cost from duration, distance and risk;
5. searches additional road-following corridors when the fastest route is materially risky;
6. proposes a next-best route only when risk is meaningfully reduced.

No synthetic potholes are injected by the routing endpoint.

## Creating operational transport data

A fresh database intentionally contains no fake road events, routes, buses or assignments. Log in as `transport.supervisor` and use **Lignes & flotte** to:

1. create a bus;
2. create an official route from start/end coordinates (the backend obtains the road geometry from OSRM);
3. assign the bus/route to `driver.srtb`.

The driver portal then reads that real assignment and runs the next-best-route calculation against current road hazards.

## Alembic

Schema migrations are under:

```text
backend/alembic/versions/
```

Inspect the current revision:

```powershell
docker compose exec api alembic -c alembic.ini current
```

Create a migration in a local Python environment so the generated file is written directly into `backend/alembic/versions/`:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\alembic -c alembic.ini revision -m "describe change"
cd ..
```

On the next API start, the entrypoint automatically applies the new revision. To apply it immediately to a running container:

```powershell
docker compose exec api alembic -c alembic.ini upgrade head
```

## M1 perception

The M1 runtime path is:

```text
image/video upload
  → perception_jobs
  → perception-worker
  → OpenCV sampling/decode
  → batched YOLO inference
  → GPS alignment
  → road_observations
  → spatial/temporal deduplication
  → road_events
```

The worker is deliberately not part of the default stack until a validated checkpoint exists at:

```text
models/road-damage-yolo26n.pt
```

Start it with:

```powershell
docker compose --profile m1 up -d --build perception-worker
```

M1 training and benchmarking instructions are in `ml/perception/README.md`.

## Optional MLflow

```powershell
docker compose --profile ml up -d mlflow
```

## Normal development cycle

After the first successful clean start, do not delete the database every time. Normally use:

```powershell
docker compose up -d --build
docker compose ps
```

When the database schema changes, add an Alembic migration rather than editing the running database manually.

## Tests

```bash
pytest -q
```

Frontend build:

```bash
cd frontend
npm install
npm run build
```

The central integration contract remains:

```text
M1 Perception → RoadEvent
M2 Risk       → RiskScore
M3 Routing    → RouteRecommendation
M4 Platform   → Operational action
M5 Foundation → persistence, API, migrations, realtime and deployment
```
