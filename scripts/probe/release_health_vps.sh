#!/usr/bin/env bash
set -euo pipefail

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-vps}"
export COMPOSE_FILE="${COMPOSE_FILE:-compose.yml:compose.vps.yml}"

log() {
  printf '[release-smoke] %s\n' "$1"
}

warn() {
  printf '[release-smoke][warn] %s\n' "$1" >&2
}

fail() {
  printf '[release-smoke][fail] %s\n' "$1" >&2
  exit 1
}

if ! command -v docker >/dev/null 2>&1; then
  fail "docker is required"
fi
if ! command -v make >/dev/null 2>&1; then
  fail "make is required"
fi

log "Docker Compose status snapshot"
docker compose ps

container_statuses="$(docker ps -a --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" --format '{{.Names}}\t{{.Status}}')"
if [ -z "$container_statuses" ]; then
  fail "no running containers found for compose project '${COMPOSE_PROJECT_NAME}'"
fi

if printf '%s\n' "$container_statuses" | grep -Eq 'Restarting|Dead'; then
  printf '%s\n' "$container_statuses"
  fail "compose project has restarting/dead containers"
fi

if printf '%s\n' "$container_statuses" | grep -Eq 'Exited \(([1-9][0-9]*)\)'; then
  printf '%s\n' "$container_statuses"
  fail "compose project has non-zero exited containers"
fi

if printf '%s\n' "$container_statuses" | grep -Eq 'Exited \(0\)'; then
  warn "compose project has exited(0) one-shot containers; continuing"
fi

if printf '%s\n' "$container_statuses" | grep -Eq '\(unhealthy\)'; then
  printf '%s\n' "$container_statuses"
  fail "compose project has unhealthy containers"
fi

# Single source of truth: scripts/lib/vps_noncore_services.sh (#1611).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=../lib/vps_noncore_services.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/../lib/vps_noncore_services.sh"

running_services="$(docker compose ps --status running --services 2>/dev/null || true)"
for removed_service in "${VPS_NONCORE_SERVICES[@]}"; do
  if printf '%s\n' "$running_services" | grep -Eq "^${removed_service}$"; then
    fail "removed service is running in minimal VPS runtime: ${removed_service}"
  fi
done

log "Bot functional smoke (Qdrant + LiteLLM)"
make test-bot-health-vps

log "Bot network reachability (qdrant, litellm, postgres, redis, bge-m3, user-base)"
docker compose exec -T bot python - <<'PY'
import socket
import sys

targets = [
    ("qdrant", 6333),
    ("litellm", 4000),
    ("postgres", 5432),
    ("redis", 6379),
    ("bge-m3", 8000),
    ("user-base", 8000),
]

failed = []
for host, port in targets:
    sock = socket.socket()
    sock.settimeout(5)
    try:
        sock.connect((host, port))
        print(f"  ok: {host}:{port}")
    except Exception as exc:
        failed.append((host, port, f"{exc.__class__.__name__}: {exc}"))
    finally:
        sock.close()

if failed:
    for host, port, reason in failed:
        print(f"  fail: {host}:{port} -> {reason}", file=sys.stderr)
    sys.exit(1)
PY

log "Mini app release smoke skipped (archived optional surface)"

handoff_runtime_env="$(
  docker compose exec -T bot python - <<'PY'
import os

print(f"HANDOFF_ENABLED={os.getenv('HANDOFF_ENABLED', 'false')}")
print(f"MANAGERS_GROUP_ID={os.getenv('MANAGERS_GROUP_ID', '')}")
PY
)"
handoff_enabled_runtime="$(printf '%s\n' "$handoff_runtime_env" | awk -F= '/^HANDOFF_ENABLED=/{print $2}')"
managers_group_id_runtime="$(printf '%s\n' "$handoff_runtime_env" | awk -F= '/^MANAGERS_GROUP_ID=/{print $2}')"

if [ "$handoff_enabled_runtime" = "true" ]; then
  log "Handoff release smoke"
  [ -n "$managers_group_id_runtime" ] || fail "MANAGERS_GROUP_ID missing in bot container"
  printf '  ok: handoff env contract present in bot container\n'
else
  warn "handoff smoke skipped (HANDOFF_ENABLED=${handoff_enabled_runtime})"
fi

log "Release smoke passed"
