#!/bin/sh
set -eu

# hf_offline: enforce HuggingFace offline mode only when the baked model cache
# is present and non-empty. If the build-time pre-warm silently failed (best-effort
# step), the cache directory will be empty/missing — in that case allow runtime
# download rather than crashing with no models and no network access.
# ponytail: simple directory-size check; upgrade path is a proper manifest file.
hf_cache_dir="${HF_HUB_CACHE:-/opt/huggingface/hub}"
if [ -d "$hf_cache_dir" ] && [ -n "$(ls -A "$hf_cache_dir" 2>/dev/null)" ]; then
    export HF_HUB_OFFLINE=1
    export TRANSFORMERS_OFFLINE=1
else
    # Cache missing or empty — allow runtime download
    unset HF_HUB_OFFLINE 2>/dev/null || true
    unset TRANSFORMERS_OFFLINE 2>/dev/null || true
fi

manifest_dir="${MANIFEST_DIR:-/data/manifest}"

mkdir -p "$manifest_dir"
# Best-effort: under the hardened compose profile (cap_drop: ALL,
# no-new-privileges, non-root user) chown is not permitted and not needed —
# the volume is already owned correctly. Do not let EPERM crash-loop the
# container. (#3105 follow-up)
chown -R ingestion:ingestion "$manifest_dir" 2>/dev/null || true

exec gosu ingestion /app/.venv/bin/python -m src.ingestion.unified.cli "$@"
