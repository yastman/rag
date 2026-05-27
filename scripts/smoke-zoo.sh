#!/usr/bin/env bash
# scripts/smoke-zoo.sh - Quick smoke test for all zoo services
# Usage: ./scripts/smoke-zoo.sh [--quiet]
# Exit: 0 if all pass, 1 if any fail
#
# Issue #2196: redis-cli is invoked via the host CLI when present, otherwise
# via `docker exec dev-redis-1 redis-cli ...`. When neither path is available
# the Redis check is reported as a dependency failure (not a Redis outage)
# and the script continues with the remaining independent service checks.

set -euo pipefail

QUIET="${1:-}"
FAILED=0
PASSED=0

# Colors (disabled in quiet mode)
if [[ "$QUIET" != "--quiet" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' NC=''
fi

REDIS_CONTAINER="${SMOKE_REDIS_CONTAINER:-dev-redis-1}"

# Resolve a redis-cli invocation prefix:
#   - host redis-cli when available
#   - `docker exec $REDIS_CONTAINER redis-cli` when only Docker is available
#   - empty when neither is available (caller must classify as dependency error)
resolve_redis_cli() {
    if command -v redis-cli > /dev/null 2>&1; then
        echo "redis-cli"
        return 0
    fi
    if command -v docker > /dev/null 2>&1; then
        # Use the canonical local-dev container name. Operators can override
        # via SMOKE_REDIS_CONTAINER for non-default project names.
        echo "docker exec -i ${REDIS_CONTAINER} redis-cli"
        return 0
    fi
    return 1
}

check() {
    local name="$1"
    local cmd="$2"

    if eval "$cmd" > /dev/null 2>&1; then
        [[ "$QUIET" != "--quiet" ]] && echo -e "${GREEN}[OK]${NC} $name"
        PASSED=$((PASSED + 1))
        return 0
    else
        [[ "$QUIET" != "--quiet" ]] && echo -e "${RED}[FAIL]${NC} $name"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

dependency_fail() {
    local name="$1"
    local detail="$2"
    [[ "$QUIET" != "--quiet" ]] && \
        echo -e "${YELLOW}[DEP]${NC} $name (dependency missing: $detail)"
    FAILED=$((FAILED + 1))
}

[[ "$QUIET" != "--quiet" ]] && echo -e "${YELLOW}Zoo Smoke Tests${NC}"
[[ "$QUIET" != "--quiet" ]] && echo "=================="

# 1+2. Redis: resolve invocation, otherwise classify as dependency failure.
REDIS_CLI="$(resolve_redis_cli)" || REDIS_CLI=""
if [[ -n "$REDIS_CLI" ]]; then
    check "Redis PING" "$REDIS_CLI -h localhost -p 6379 PING | grep -q PONG"
    check "Redis FT._LIST" "$REDIS_CLI -h localhost -p 6379 FT._LIST"
else
    dependency_fail "Redis PING" "host redis-cli not installed and docker not available"
    dependency_fail "Redis FT._LIST" "host redis-cli not installed and docker not available"
fi

# 3. Qdrant
check "Qdrant readyz" "curl -sf http://localhost:6333/readyz"

# 4. bge-m3
check "bge-m3 health" "curl -sf http://localhost:8000/health | grep -q ok"

# 5. bm42
check "bm42 health" "curl -sf http://localhost:8002/health | grep -q ok"

# 6. user-base
check "user-base health" "curl -sf http://localhost:8003/health | grep -q ok"

# 7. litellm
check "litellm health" "curl -sf http://localhost:4000/health/liveliness"

# Summary
[[ "$QUIET" != "--quiet" ]] && echo "=================="
[[ "$QUIET" != "--quiet" ]] && echo -e "Passed: ${GREEN}$PASSED${NC}, Failed: ${RED}$FAILED${NC}"

if [[ $FAILED -gt 0 ]]; then
    exit 1
fi
exit 0
