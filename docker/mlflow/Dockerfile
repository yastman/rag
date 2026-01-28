FROM ghcr.io/mlflow/mlflow:v2.22.4

# Install PostgreSQL driver for backend store
RUN pip install --no-cache-dir psycopg2-binary==2.9.11

# Default port
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
