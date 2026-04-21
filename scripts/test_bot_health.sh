#!/usr/bin/env bash
set -euo pipefail

LLM_BASE_URL=${LLM_BASE_URL:-${LITELLM_BASE_URL:-http://localhost:4000}}

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

strip_trailing_slash() {
  printf '%s' "${1%/}"
}

if ! command -v curl >/dev/null 2>&1; then
  fail "curl is required"
fi

if ! command -v uv >/dev/null 2>&1; then
  fail "uv is required"
fi

# Redis: use the same BotConfig + redis-py path as native bot startup
uv run --no-sync python - <<'PY' || fail "Redis is unreachable or auth failed for native bot startup"
from telegram_bot.config import BotConfig
import redis

config = BotConfig()
client = redis.from_url(config.redis_url, decode_responses=True)
try:
    if client.ping() is not True:
        raise RuntimeError("unexpected Redis ping response")
finally:
    client.close()
PY
echo "✓ Redis auth OK"

# Postgres: report the REAL_ESTATE_DATABASE_URL localhost:5432 contract used by
# native bot startup without turning optional DB reachability into a hard fail.
uv run --no-sync python - <<'PY'
from telegram_bot.config import BotConfig
import socket
from urllib.parse import urlparse

config = BotConfig()
parsed = urlparse(config.realestate_database_url)
host = parsed.hostname or ""
port = parsed.port or 5432

if host in {"localhost", "127.0.0.1"}:
    try:
        with socket.create_connection((host, port), timeout=1):
            print(f"✓ Postgres reachable for native bot startup: {host}:{port}")
    except OSError as exc:
        print(
            f"! Postgres unreachable at {host}:{port} "
            f"(optional for native bot runs): {exc}"
        )
else:
    print(
        f"i Postgres DSN points to {host or 'remote host'}:{port}; "
        "skipping local localhost:5432 contract check"
    )
PY

# Qdrant: use the same BotConfig + qdrant-client collection contract as native bot startup
uv run --no-sync python - <<'PY' || fail "Qdrant is unreachable or the configured collection is missing"
from telegram_bot.config import BotConfig
from qdrant_client import QdrantClient

config = BotConfig()
client = QdrantClient(
    url=config.qdrant_url,
    api_key=config.qdrant_api_key if config.qdrant_url.startswith("https://") else None,
    timeout=config.qdrant_timeout,
)
collection = config.get_collection_name()
try:
    if not client.collection_exists(collection):
        raise RuntimeError(f"Qdrant collection '{collection}' not found")
    print(f"✓ Qdrant collection exists for native bot startup: {collection}")
finally:
    client.close()
PY

# LiteLLM/LLM connectivity
normalized_llm_base_url="$(strip_trailing_slash "$LLM_BASE_URL")"
health_base_url="${normalized_llm_base_url%/v1}"
models_url="$normalized_llm_base_url/models"
health_url="$health_base_url/health/readiness"

if curl -fsS "$health_url" >/dev/null; then
  echo "✓ LiteLLM readiness OK: $health_url"
else
  # Fallback for OpenAI-compatible endpoints.
  curl -fsS "$models_url" >/dev/null || fail "LLM endpoint not responding at $LLM_BASE_URL"
  echo "✓ LLM models OK: $models_url"
fi

exit 0
