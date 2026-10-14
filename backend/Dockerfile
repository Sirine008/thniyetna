# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_ROOT_USER_ACTION=ignore

# Dependency layer changes only when requirements.txt changes.
COPY requirements.txt .
# BuildKit cache means a failed/retried build does not have to download every
# Python wheel again. We intentionally do NOT use --no-cache-dir here.
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --timeout 300 --retries 12 --prefer-binary -r requirements.txt

COPY . .
EXPOSE 8000
RUN chmod +x /app/entrypoint.sh
CMD ["/app/entrypoint.sh"]
