#!/usr/bin/env bash
set -euo pipefail

REQUIRE_MINI_APP_ENDPOINT="${REQUIRE_MINI_APP_ENDPOINT:-auto}" # auto|true|false
MINI_APP_FRONTEND_URL="${MINI_APP_FRONTEND_URL:-http://127.0.0.1:8091/health}"
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

case "$REQUIRE_MINI_APP_ENDPOINT" in
  auto|true|false) ;;
  *)
    fail "REQUIRE_MINI_APP_ENDPOINT must be one of: auto,true,false"
    ;;
esac

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

log "Bot functional smoke (Qdrant + LiteLLM)"
make test-bot-health-vps

log "Bot network reachability (qdrant, litellm, postgres, redis)"
docker compose exec -T bot python - <<'PY'
import socket
import sys

targets = [
    ("qdrant", 6333),
    ("litellm", 4000),
    ("postgres", 5432),
    ("redis", 6379),
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

mini_running="$(docker compose ps mini-app-api mini-app-frontend --status running --services 2>/dev/null || true)"
mini_expected=false
if [ "$REQUIRE_MINI_APP_ENDPOINT" = "true" ]; then
  mini_expected=true
elif [ "$REQUIRE_MINI_APP_ENDPOINT" = "auto" ] && [ -n "$mini_running" ]; then
  mini_expected=true
fi

if [ "$mini_expected" = "true" ]; then
  log "Mini app release smoke"
  if ! printf '%s\n' "$mini_running" | grep -Eq '^mini-app-frontend$'; then
    fail "mini-app-frontend is not running"
  fi

  if ! printf '%s\n' "$mini_running" | grep -Eq '^mini-app-api$'; then
    fail "mini-app-api is not running"
  fi

  docker compose exec -T mini-app-frontend wget -qO- http://127.0.0.1/health >/dev/null \
    || fail "mini-app-frontend internal /health failed"
  docker compose exec -T mini-app-api python - <<'PY'
import urllib.request
urllib.request.urlopen("http://localhost:8090/health", timeout=10)
print("  ok: mini-app-api internal /health")
PY

  curl -fsS "$MINI_APP_FRONTEND_URL" >/dev/null \
    || fail "mini-app frontend host endpoint failed: $MINI_APP_FRONTEND_URL"
  log "Mini app endpoint OK: $MINI_APP_FRONTEND_URL"
else
  warn "mini app endpoint check skipped (REQUIRE_MINI_APP_ENDPOINT=${REQUIRE_MINI_APP_ENDPOINT})"
fi

HANDOFF_ENABLED="${HANDOFF_ENABLED:-false}"

if [ "$HANDOFF_ENABLED" = "true" ]; then
  log "Handoff release smoke"
  docker compose exec -T bot python - <<'PY'
import os

handoff_enabled = os.getenv("HANDOFF_ENABLED", "false")
managers_group_id = os.getenv("MANAGERS_GROUP_ID", "")

assert handoff_enabled == "true", "HANDOFF_ENABLED is not true in bot container"
assert managers_group_id, "MANAGERS_GROUP_ID missing in bot container"
print("  ok: handoff env contract present in bot container")
PY
else
  warn "handoff smoke skipped (HANDOFF_ENABLED=${HANDOFF_ENABLED})"
fi

log "Release smoke passed"
