# syntax=docker/dockerfile:1@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6
FROM ghcr.io/mlflow/mlflow:v3.10.0@sha256:f1e711271dd0c1efec7e896cb50d098acd4ba53781a5ab2a3a95167738a01e14

# Install PostgreSQL driver for backend store
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install psycopg2-binary==2.9.11

# Default port
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
