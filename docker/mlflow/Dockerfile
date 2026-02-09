# syntax=docker/dockerfile:1
FROM ghcr.io/mlflow/mlflow:v3.9.0

# Install PostgreSQL driver for backend store
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install psycopg2-binary==2.9.11

# Default port
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
