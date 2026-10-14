# Monitoring (M5)

Operational AI needs monitoring beyond offline accuracy: request latency,
error rates, data-quality checks on incoming events, and model-drift signals
for M2's predictions.

Starting point:
- `logging_config.py` — structured logging shared by all API routers
- Add Prometheus/Grafana or a hosted equivalent once there's a deployed
  environment worth monitoring; not needed for local dev.
