#!/usr/bin/env bash
# check_services.sh — check local service health for Qdrant, Redis, BGE-M3, Docling
# Ports match compose.yml defaults; override via environment variables.
# Exits non-zero if any required service is unreachable.
set -uo pipefail

QDRANT_HOST="${QDRANT_HOST:-localhost}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
BGE_M3_HOST="${BGE_M3_HOST:-localhost}"
BGE_M3_PORT="${BGE_M3_PORT:-8000}"
DOCLING_HOST="${DOCLING_HOST:-localhost}"
DOCLING_PORT="${DOCLING_PORT:-5001}"

TIMEOUT="${HEALTH_TIMEOUT:-3}"

PASS=0
FAIL=0

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

echo "--- Local service health ---"

check_http "Qdrant"  "http://${QDRANT_HOST}:${QDRANT_PORT}/readyz"
check_tcp  "Redis"   "${REDIS_HOST}" "${REDIS_PORT}"
check_http "BGE-M3"  "http://${BGE_M3_HOST}:${BGE_M3_PORT}/health"
check_http "Docling" "http://${DOCLING_HOST}:${DOCLING_PORT}/health"

echo "---"
echo "Result: ${PASS} PASS, ${FAIL} FAIL"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
