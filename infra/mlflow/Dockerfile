# syntax=docker/dockerfile:1.7
FROM ghcr.io/mlflow/mlflow:v2.16.2
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefer-binary psycopg2-binary
