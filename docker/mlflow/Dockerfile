# syntax=docker/dockerfile:1@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6
FROM ghcr.io/mlflow/mlflow:v3.10.1@sha256:bb350de1ae29025e3f78d70a3443047ca863429cc577a28e050c7156ed8d388d

# Install PostgreSQL driver for backend store
RUN --mount=type=cache,target=/tmp/pip-cache \
    PIP_CACHE_DIR=/tmp/pip-cache pip install psycopg2-binary==2.9.11

# Non-root user
RUN useradd -r -m -s /bin/false mlflow && \
    mkdir -p /mlflow/artifacts && \
    chown -R mlflow:mlflow /mlflow
USER mlflow

# Default port
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
