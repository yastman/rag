#!/usr/bin/env bash
# check_services.sh — check local service health for Qdrant, Redis, BGE-M3, Ingestion
# Ports match compose.yml defaults; override via environment variables.
# Exits non-zero if any required service is unreachable.
set -uo pipefail

QDRANT_HOST="${QDRANT_HOST:-localhost}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
BGE_M3_HOST="${BGE_M3_HOST:-localhost}"
BGE_M3_PORT="${BGE_M3_PORT:-8000}"

TIMEOUT="${HEALTH_TIMEOUT:-3}"

PASS=0
FAIL=0
# --- CLI args ---
ENV_FILE=""
PROJECT_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --project-name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Default env-file: same .env / fixture fallback as Makefile
if [ -z "$ENV_FILE" ]; then
    if [ -f .env ]; then
        ENV_FILE=".env"
    else
        ENV_FILE="tests/fixtures/compose.ci.env"
    fi
fi

check_http() {
  local name="$1" url="$2"
  if curl -sf --max-time "$TIMEOUT" "$url" -o /dev/null 2>/dev/null; then
    echo "PASS  $name  ($url)"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $name  ($url)"
    FAIL=$((FAIL + 1))
  fi
}

check_tcp() {
  local name="$1" host="$2" port="$3"
  if nc -z -w "$TIMEOUT" "$host" "$port" 2>/dev/null; then
    echo "PASS  $name  ($host:$port)"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $name  ($host:$port)"
    FAIL=$((FAIL + 1))
  fi
}

check_ingestion() {
  local status
  if ! command -v docker >/dev/null 2>&1; then
    echo "SKIP  Ingestion  (docker not available)"
    return 0
  fi
  status=$(docker compose -f compose.yml -f compose.dev.yml --env-file "$ENV_FILE" ${PROJECT_NAME:+--project-name "$PROJECT_NAME"} --profile ingest ps ingestion --format '{{.Status}}' 2>/dev/null || true)
  if [ -z "$status" ]; then
    echo "FAIL  Ingestion  (container not found — start with make local-up-ingest)"
    FAIL=$((FAIL + 1))
  elif echo "$status" | grep -qE '^Up[[:space:]].*\(healthy\)'; then
    echo "PASS  Ingestion  (running, healthy)"
    PASS=$((PASS + 1))
  else
    echo "FAIL  Ingestion  ($status)"
    FAIL=$((FAIL + 1))
  fi
}


echo "--- Local service health ---"

check_http "Qdrant"  "http://${QDRANT_HOST}:${QDRANT_PORT}/readyz"
check_tcp  "Redis"   "${REDIS_HOST}" "${REDIS_PORT}"
check_http "BGE-M3"  "http://${BGE_M3_HOST}:${BGE_M3_PORT}/health"
check_ingestion

echo "---"
echo "Result: ${PASS} PASS, ${FAIL} FAIL"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
