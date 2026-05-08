# Local Development

Canonical local setup and verification flow.

## Prerequisites

- Python `3.12` recommended (`>=3.11` supported)
- `uv`
- Docker + Docker Compose v2

## 1. Bootstrap Workspace

```bash
uv sync
cp .env.example .env
```

For local development, the canonical environment file is `.env` in the repo root. `.env.local` is legacy/manual-only and is not auto-loaded by local commands.

Minimum env for bot profile:
- `TELEGRAM_BOT_TOKEN`
- `LITELLM_MASTER_KEY`
- at least one provider key: `CEREBRAS_API_KEY` or `GROQ_API_KEY` or `OPENAI_API_KEY`
- optional `QDRANT_COLLECTION` (defaults to `gdrive_documents_bge` from `compose.yml` if unset)

Minimum env for Telegram E2E (Telethon userbot):
- `TELEGRAM_API_ID` (from [my.telegram.org](https://my.telegram.org))
- `TELEGRAM_API_HASH` (from [my.telegram.org](https://my.telegram.org))
- `E2E_BOT_USERNAME` (defaults to `@test_nika_homes_bot`)
- an authorized Telethon session file (e.g., `e2e_tester.session`)
- if the session is present but unauthorized, refresh it with `uv run python scripts/e2e/auth.py --phone <PHONE>`

The canonical local Compose project name is `dev`. `COMPOSE_PROJECT_NAME=dev` is set in `tests/fixtures/compose.ci.env`, which `make` targets use as a fallback when `.env` is absent. Do not create worktree-named Docker projects.

Secret model by compose file:
- `compose.yml` is the secure baseline: no predictable built-in secret defaults.
- `compose.dev.yml` may provide local-only defaults for development convenience (`pk-lf-dev`, `sk-lf-dev`, `clickhouse`, `miniosecret`, `langfuseredis`, `devkey`).
- Production/VPS stacks must set real secret values via environment management or file-backed secret patterns (`*_FILE` / `secrets:`) when available.

## 2. Start Services

```bash
# Core services (default compose set)
make docker-up

# Bot runtime
make docker-bot-up

# Optional profiles
make docker-ml-up
make docker-ingest-up
make monitoring-up

# Voice is intentionally off by default; start separately when needed:
# make docker-voice-up
```

## 3. Validate Runtime

```bash
make docker-ps
curl -fsS http://localhost:6333/readyz
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:5001/health
```

Bot preflight:

```bash
make test-bot-health
```

If `make test-bot-health` reports Redis auth failure after editing `.env`:

```bash
make local-redis-recreate
make test-bot-health
```

`make test-bot-health` is a local helper for the published native bot prerequisites:
- Redis via the same `BotConfig` + `redis.from_url(...)` path used by native startup
- Qdrant via `BotConfig.get_collection_name()` + `qdrant-client`
- LiteLLM via proxy readiness (`/health/readiness`)
- optional localhost Postgres note without turning DB reachability into a hard failure

The authoritative startup preflight still lives in [`telegram_bot/preflight.py`](../telegram_bot/preflight.py) and runs when you start the bot. That runtime preflight also keeps the repo-local BGE-M3 health and warmup contract, because BGE-M3 is not a generic upstream SDK probe in this repo.

## 4. Development Gates

Local release gate:

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
make test-bot-health
```

Optional broader gates:

```bash
make test
make test-full
```

Trace coverage gate:

```bash
make validate-traces-fast
```

This target runs natively on the host and automatically points to local Docker service endpoints (`localhost:6333`, `localhost:8000`, `localhost:4000`, etc.). You can override individual endpoints if needed: `make validate-traces-fast QDRANT_URL=http://custom:6333`.

When `.env` is absent, `validate-traces-fast` runs a preflight guard before `docker compose up`. If fallback uses `tests/fixtures/compose.ci.env` with the local default `POSTGRES_PASSWORD=postgres`, reusing `dev_postgres_data` is allowed. The guard fails fast only when fallback password and existing volume credentials can mismatch, preventing an unhealthy Langfuse/Postgres auth loop.

If Langfuse CLI returns `401` or points to wrong host, run with explicit host:

```bash
lf --host "$LANGFUSE_HOST" traces list --name rag-api-query --limit 1
```

## 5. Python Runtime Note

Docker images that import `telegram_bot.observability` (and therefore `langfuse`) run on Python 3.13. Local native development via `uv` may use a different Python version (3.11+ supported, 3.12 recommended).

## 6. Running Components Without Docker Wrapper

```bash
# Telegram bot
uv run python -m telegram_bot.main

# Unified ingestion
uv run python -m src.ingestion.unified.cli run --watch

# RAG API
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8080
```

## 7. Minimal Stack (Fast Iteration)

Use the `local-*` shortcuts (they now run a minimal subset from `compose.yml:compose.dev.yml`) when full dev stack is unnecessary:

```bash
make local-up
make test-bot-health
make bot
make local-ps
make local-down
```

If you changed `.env` `REDIS_PASSWORD`, recreate local Redis before retrying bot health:

```bash
make local-redis-recreate
make test-bot-health
```

`make bot` is the operator-facing command for this local loop; `make run-bot` remains the lower-level/native target.

For ingestion workflows that require docling:

```bash
make local-up-ingest
make local-ps
make local-down
```

## 8. Common Issues

- `docker-bot-up` fails immediately: missing required env variables in `.env`.
- Slow first startup: BGE-M3 and Docling warm up and cache models.
- Ingestion status empty: verify `GDRIVE_SYNC_DIR` and collection bootstrap.
- Redis auth error (`WRONGPASS` / `NOAUTH`) after changing `.env` `REDIS_PASSWORD`: run `make local-redis-recreate`, then `make test-bot-health`.
