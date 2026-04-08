#!/bin/sh
set -eu

manifest_dir="${MANIFEST_DIR:-/data/manifest}"

mkdir -p "$manifest_dir"
chown -R ingestion:ingestion "$manifest_dir"

exec gosu ingestion /app/.venv/bin/python -m src.ingestion.unified.cli "$@"
