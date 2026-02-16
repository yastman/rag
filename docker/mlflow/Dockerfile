# syntax=docker/dockerfile:1@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6
FROM ghcr.io/mlflow/mlflow:v3.9.0@sha256:ac0532a98f874c5624b1e56c85af4ef6ffe488fa04a3b2fd0fd44e5bd13552a9

# Install PostgreSQL driver for backend store
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install psycopg2-binary==2.9.11

# Default port
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
