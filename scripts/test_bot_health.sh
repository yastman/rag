#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

resolve_qdrant_collection() {
  local dotenv_value compose_default

  if [ -n "${QDRANT_COLLECTION:-}" ]; then
    printf '%s\n' "$QDRANT_COLLECTION"
    return 0
  fi

  if [ -f "$PROJECT_ROOT/.env" ]; then
    dotenv_value=$(
      sed -nE "s/^[[:space:]]*(export[[:space:]]+)?QDRANT_COLLECTION[[:space:]]*=[[:space:]]*['\"]?([^'\"#[:space:]]+)['\"]?.*$/\\2/p" "$PROJECT_ROOT/.env" \
        | tail -n1
    )
    if [ -n "$dotenv_value" ]; then
      printf '%s\n' "$dotenv_value"
      return 0
    fi
  fi

  compose_default=$(
    sed -nE "s/^[[:space:]]*QDRANT_COLLECTION:[[:space:]]*\\$\\{QDRANT_COLLECTION:-([^}]+)\\}[[:space:]]*$/\\1/p" "$PROJECT_ROOT/compose.yml" \
      | head -n1
  )
  if [ -n "$compose_default" ]; then
    printf '%s\n' "$compose_default"
    return 0
  fi

  printf '%s\n' "gdrive_documents_bge"
}

QDRANT_URL=${QDRANT_URL:-http://localhost:6333}
QDRANT_COLLECTION=$(resolve_qdrant_collection)
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
