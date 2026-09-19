#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/../.."
# shellcheck source=../lib/release_compose.sh
. "${SCRIPT_DIR}/../lib/release_compose.sh"
release_compose_init

log() { printf '[release-smoke] %s\n' "$1"; }
fail() { printf '[release-smoke][fail] %s\n' "$1" >&2; exit 1; }

for service in "${release_services[@]}"; do
  ids="$("${release_compose[@]}" ps -q "$service" 2>/dev/null)" || fail "Cannot inspect required service: $service"
  [ -n "$ids" ] || fail "Required service missing: $service"
  while IFS= read -r id; do
    state="$(docker inspect --format '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$id" 2>/dev/null)" || fail "Cannot inspect required service: $service"
    [ "$state" = running:healthy ] || fail "Required service is not running and healthy: $service"
  done <<< "$ids"
  log "Healthy: $service"
done

handoff_runtime_env="$(
  "${release_compose[@]}" exec -T bot python - 2>/dev/null <<'PY'
import os

print(f"HANDOFF_ENABLED={os.getenv('HANDOFF_ENABLED', 'false')}")
print(f"MANAGERS_GROUP_ID={os.getenv('MANAGERS_GROUP_ID', '')}")
PY
)" || fail "Cannot read bot handoff configuration"
handoff_enabled_runtime="$(printf '%s\n' "$handoff_runtime_env" | awk -F= '/^HANDOFF_ENABLED=/{print $2}')"
managers_group_id_runtime="$(printf '%s\n' "$handoff_runtime_env" | awk -F= '/^MANAGERS_GROUP_ID=/{print $2}')"

if [ "$handoff_enabled_runtime" = "true" ]; then
  log "Handoff release smoke"
  [ -n "$managers_group_id_runtime" ] || fail "MANAGERS_GROUP_ID missing in bot container"
  printf '  ok: handoff env contract present in bot container\n'
else
  log "handoff smoke skipped"
fi

log "Release smoke passed"
