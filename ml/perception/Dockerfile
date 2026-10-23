# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    M1_DEVICE=cpu
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
# CPU-only torch first, so ultralytics does not pull the CUDA wheels (M1 runs on CPU).
RUN --mount=type=cache,target=/root/.cache/pip pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
COPY ml/perception/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --prefer-binary -r /app/requirements.txt
COPY ml/perception /app/perception
ENV PYTHONPATH=/app
CMD ["python", "-m", "perception.worker"]
