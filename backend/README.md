# THNIYETNA backend

FastAPI backend and Alembic migrations.

Routers:

- `/auth` authentication and citizen registration
- `/perception` M1 ingestion/jobs/events
- `/prediction` M2 risk
- `/routing` M3 OSRM + risk-aware next-best routing
- `/platform` M4 operational workflows
- `/realtime` SSE outbox
- `/media` persistent local media
- `/system` M5 health/readiness

Database schema changes belong in `alembic/versions/`.
