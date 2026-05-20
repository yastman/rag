#!/usr/bin/env bash
set -euo pipefail

APPLY=false
if [ "${1:-}" = "--apply" ]; then
  APPLY=true
elif [ "${1:-}" != "" ]; then
  echo "Usage: $0 [--apply]" >&2
  exit 2
fi

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-vps}"
export COMPOSE_PROJECT_NAME
if [ "$COMPOSE_PROJECT_NAME" != "vps" ]; then
  echo "Refusing cleanup: COMPOSE_PROJECT_NAME must be vps for vps_* volume allowlist" >&2
  exit 1
fi

# Service and volume allowlists

removed_services=(
  mini-app-api
  mini-app-frontend
  docling
  ingestion
  langfuse
  langfuse-worker
  clickhouse
  minio
  redis-langfuse
)

removable_volumes=(
  vps_clickhouse_data
  vps_clickhouse_logs
  vps_minio_data
  vps_langfuse_redis_data
  vps_ingestion-manifest
)

protected_volumes=(
  vps_qdrant_data
  vps_postgres_data
  vps_redis_data
  vps_hf_cache
)

# Cross-check: no protected volume appears in removable list

for protected in "${protected_volumes[@]}"; do
  for candidate in "${removable_volumes[@]}"; do
    if [ "$candidate" = "$protected" ]; then
      echo "Refusing unsafe cleanup: protected volume listed as removable: $candidate" >&2
      exit 1
    fi
  done
done

# Preflight: verify removed services are vps-noncore gated

preflight_noncore_profiles() {
  local config_json
  config_json="$(mktemp)"
  trap 'rm -f "$config_json"' RETURN
  docker compose config --format json > "$config_json"
  python3 - "$config_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
removed = {
    "mini-app-api",
    "mini-app-frontend",
    "docling",
    "ingestion",
    "langfuse",
    "langfuse-worker",
    "clickhouse",
    "minio",
    "redis-langfuse",
}
bad = []
for name in sorted(removed):
    service = data.get("services", {}).get(name, {})
    profiles = set(service.get("profiles") or [])
    if "vps-noncore" not in profiles:
        bad.append(f"{name}: profiles={sorted(profiles)}")
if bad:
    print("Refusing cleanup because removed services are still default-enabled:", file=sys.stderr)
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
PY
}

echo "Removed services:"
printf '  %s\n' "${removed_services[@]}"
echo "Removable volumes:"
printf '  %s\n' "${removable_volumes[@]}"
echo "Protected volumes:"
printf '  %s\n' "${protected_volumes[@]}"

export COMPOSE_FILE="${COMPOSE_FILE:-compose.yml:compose.vps.yml}"
preflight_noncore_profiles

if [ "$APPLY" != "true" ]; then
  echo "Dry run only. Re-run with --apply to stop services and remove allowlisted volumes."
  exit 0
fi

# Apply: stop, remove containers, then remove allowlisted volumes

docker compose stop "${removed_services[@]}" || true
docker compose rm -f "${removed_services[@]}" || true

for volume in "${removable_volumes[@]}"; do
  if docker volume inspect "$volume" >/dev/null 2>&1; then
    docker volume rm "$volume"
  else
    echo "Volume not present, skipping: $volume"
  fi
done

docker system df
df -h /
