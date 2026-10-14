# M1 — Perception code

- `prepare_rdd2022.py` — Pascal-VOC → YOLO conversion with deterministic splits.
- `train_detector.py` — compare YOLO26n, YOLO26s and YOLO11n.
- `benchmark.py` — test-set accuracy and runtime measurements.
- `export_model.py` — ONNX/OpenVINO/TensorRT export.
- `detector.py` — shared batched image inference wrapper.
- `video.py` — time-based video sampling.
- `gps.py` — timestamp/GPS interpolation.
- `severity.py` — bounded visual severity proxy.
- `worker.py` — durable image/video job consumer, observation persistence and event deduplication.
- `citizen_vlm.py` — citizen-image adapter using the validated detector; text remains metadata until a VLM is separately validated.

The runtime checkpoint is mounted from `models/`. Do not claim model quality
until the repository's benchmark has been run on RDD2022 plus a separate local
Tunisia pilot set.
