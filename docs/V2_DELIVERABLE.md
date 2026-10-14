# v2 deliverable — architecture + M1

## Architecture decisions

- Keep the five actors and five work packages.
- Use M5 as a shared foundation, not as another business workflow.
- Keep FastAPI, React/Vite/Leaflet, PostgreSQL/PostGIS, OSRM, SSE, Docker Compose and optional MLflow.
- Use Alembic as the only schema migration system.
- Store media on a persistent local Docker volume and keep only references in PostgreSQL.
- Isolate the heavy M1 runtime in a dedicated worker.
- Use PostgreSQL `perception_jobs` as a durable lightweight work queue.

## M1 delivered

- image inference path;
- video inference path;
- time-based frame sampling;
- batch inference;
- RDD2022 conversion from Pascal VOC to YOLO;
- YOLO26n / YOLO26s / YOLO11n comparison training;
- validation metrics and runtime benchmark script;
- ONNX/OpenVINO/TensorRT export entry point;
- timestamped GPS storage and interpolation;
- `RoadObservation` persistence;
- spatial-temporal event deduplication;
- automatic M1 queueing from citizen road-damage photos;
- durable worker jobs with restart-safe claiming;
- local persistent media storage;
- M1 unit tests.

## Important validation boundary

The repository contains the training/inference system but does not invent a
trained road-damage checkpoint or benchmark. M1 becomes empirically validated
only after RDD2022 training plus a separate Tunisia pilot evaluation.
