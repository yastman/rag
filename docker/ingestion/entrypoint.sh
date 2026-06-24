#!/bin/sh
set -eu

manifest_dir="${MANIFEST_DIR:-/data/manifest}"

mkdir -p "$manifest_dir"
# Best-effort: under the hardened compose profile (cap_drop: ALL,
# no-new-privileges, non-root user) chown is not permitted and not needed —
# the volume is already owned correctly. Do not let EPERM crash-loop the
# container. (#3105 follow-up)
chown -R ingestion:ingestion "$manifest_dir" 2>/dev/null || true

exec gosu ingestion /app/.venv/bin/python -m src.ingestion.unified.cli "$@"
