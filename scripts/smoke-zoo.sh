#!/usr/bin/env bash
# scripts/smoke-zoo.sh - Quick smoke test for all zoo services
# Usage: ./scripts/smoke-zoo.sh [--quiet]
# Exit: 0 if all pass, 1 if any fail

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

check() {
    local name="$1"
    local cmd="$2"

    if eval "$cmd" > /dev/null 2>&1; then
        [[ "$QUIET" != "--quiet" ]] && echo -e "${GREEN}[OK]${NC} $name"
        ((PASSED++))
        return 0
    else
        [[ "$QUIET" != "--quiet" ]] && echo -e "${RED}[FAIL]${NC} $name"
        ((FAILED++))
        return 1
    fi
}

[[ "$QUIET" != "--quiet" ]] && echo -e "${YELLOW}Zoo Smoke Tests${NC}"
[[ "$QUIET" != "--quiet" ]] && echo "=================="

# 1. Redis
check "Redis PING" "redis-cli -h localhost -p 6379 PING | grep -q PONG"

# 2. Redis Query Engine (FT.*)
check "Redis FT._LIST" "redis-cli -h localhost -p 6379 FT._LIST"

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
