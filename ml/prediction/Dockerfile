# syntax=docker/dockerfile:1.7
# M2 scoring worker: isolated from the API like the M1 perception worker.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 PIP_ROOT_USER_ACTION=ignore \
    PYTHONPATH=/app/ml M2_MODEL_DIR=/models/m2 M2_PROCESSED_DIR=/data/m2/processed \
    M2_RAW_DIR=/data/m2/raw M2_REPORT_DIR=/data/m2/reports
COPY ml/prediction/requirements.txt /tmp/m2-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --timeout 300 --retries 12 --prefer-binary -r /tmp/m2-requirements.txt
COPY ml/prediction /app/ml/prediction
COPY data/schemas /app/data/schemas
CMD ["python", "-m", "prediction.jobs.score", "--source", "db"]
