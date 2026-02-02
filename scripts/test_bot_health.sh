#!/usr/bin/env bash
set -euo pipefail

QDRANT_URL=${QDRANT_URL:-http://localhost:6333}
QDRANT_COLLECTION=${QDRANT_COLLECTION:-contextual_bulgaria_voyage}
QDRANT_QUANTIZATION_MODE=${QDRANT_QUANTIZATION_MODE:-off}
LLM_BASE_URL=${LLM_BASE_URL:-${LITELLM_BASE_URL:-http://localhost:4000}}

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

if ! command -v curl >/dev/null 2>&1; then
  fail "curl is required"
fi

# Qdrant: target collection exists (match bot's suffix rules)
base_collection="$QDRANT_COLLECTION"
base_collection="${base_collection%_binary}"
base_collection="${base_collection%_scalar}"
collection_to_check="$base_collection"
if [ "$QDRANT_QUANTIZATION_MODE" = "scalar" ]; then
  collection_to_check="${base_collection}_scalar"
elif [ "$QDRANT_QUANTIZATION_MODE" = "binary" ]; then
  collection_to_check="${base_collection}_binary"
fi

collections=$(curl -fsS "$QDRANT_URL/collections" | tr -d '\n') || fail "Qdrant is unreachable at $QDRANT_URL"
if ! echo "$collections" | grep -q "\"name\"\s*:\s*\"$collection_to_check\""; then
  fail "Qdrant collection '$collection_to_check' not found (mode=$QDRANT_QUANTIZATION_MODE)"
fi
echo "✓ Qdrant collection exists: $collection_to_check (mode=$QDRANT_QUANTIZATION_MODE)"

# LiteLLM/LLM connectivity
if curl -fsS "$LLM_BASE_URL/health/liveliness" >/dev/null; then
  echo "✓ LLM health OK: $LLM_BASE_URL/health/liveliness"
else
  # Fallback for OpenAI-compatible endpoints
  curl -fsS "$LLM_BASE_URL/v1/models" >/dev/null || fail "LLM endpoint not responding at $LLM_BASE_URL"
  echo "✓ LLM models OK: $LLM_BASE_URL/v1/models"
fi

exit 0
