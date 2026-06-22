# Local Development

Prerequisites: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Docker with Compose.

## Setup Ladder

```bash
# 1. Clone and configure
cp .env.example .env          # fill in API keys and passwords

# 2. Install dependencies
uv sync                       # dev dependencies

# 3. Start sidecar services
make core-min-up              # Qdrant + Redis only (fastest start)
# or
make core-up                  # full stack: Qdrant, Redis, BGE-M3, PostgreSQL
# or
make local-up                 # alias: Qdrant + Redis + BGE-M3 + PostgreSQL

# 4. Run the bot
make run-bot                  # native (reads .env)
# or
make docker-bot-up            # Compose bot stack (requires make core-up first)
```

## Compose Profiles

| Command | Services started |
|---|---|
| `make core-min-up` | Qdrant + Redis (uses `compose.core.yml`) |
| `make core-up` / `make local-up` | Qdrant + Redis + BGE-M3 + PostgreSQL |
| `make docker-bot-up` | above + bot container |
| `make docker-ingest-up` | above + Docling + ingestion |
| `make docker-full-up` | all services (profile `full`) |

Default local dev uses `COMPOSE_FILE=compose.yml:compose.dev.yml` (ports exposed on localhost).

## Required Environment Variables

Minimum to run the bot:

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `POSTGRES_PASSWORD` | Any non-empty string for local dev |
| `REDIS_PASSWORD` | Any non-empty string for local dev |
| `OPENAI_API_KEY` / `CEREBRAS_API_KEY` / `GROQ_API_KEY` | At least one LLM provider key |
| `BGE_M3_ONNX_MODEL_HOST_DIR` | Path to INT8 ONNX model dir (required for `make docker-bot-up`) |

See `.env.example` for all variables with comments.

## Validation Ladder

Run checks in this order:

```bash
make check              # Ruff lint + MyPy type check (~10s)
make test-core          # Core unit gate: src/core + src/runtime (~91 tests, ~8s)
make test               # Broader gate: core + graph paths + no-service lane
make e2e-core-live      # Golden E2E: full spine via run_assistant_request
                        # Requires: make core-up (Qdrant + BGE-M3 running)
```

### When to run which gate

| Change area | Run |
|---|---|
| `src/core/` or `src/runtime/` | `make test-core` first |
| `telegram_bot/` or services | `make test-core` + `make test` |
| Contracts | `make test-contract` |
| Pre-merge manual check | `make test-full` |
| Full pipeline proof | `make e2e-core-live` |

## Service Health Checks

```bash
make local-service-health   # check Qdrant, Redis, BGE-M3, Docling
make preflight-qdrant       # fail fast if Qdrant unreachable
make preflight-bot          # check bot runtime env (token, ports)
make test-bot-health        # Redis + Qdrant + LiteLLM preflight
```

## Ingestion

For document ingestion see [`docs/INGESTION.md`](INGESTION.md).

Quick start:
```bash
make local-up-ingest                          # start services + Docling
make ingest-unified-bootstrap                 # create Qdrant collection schema
make ingest-unified DIR=/path/to/documents    # run once
make ingest-unified-watch                     # continuous watch mode
```

## Troubleshooting

**Redis polling lock conflict** (bot fails to start with "polling lock held"):
```bash
make release-polling-lock
```

**Stale `.venv`** (type errors after branch switch):
```bash
uv sync
```

**BGE-M3 slow cold start**: the container downloads and loads the model on first run. `start_period: 420s` is set in compose. Watch logs with `docker compose logs bge-m3 -f`.

**Qdrant collection missing**: run `make ingest-unified-bootstrap` to create the schema.

**Bot container OOM**: increase `BGE_M3_MEMORY_LIMIT` in `.env` (default 4G for BGE-M3).

## CI vs Local

GitHub CI runs static checks only (Ruff, MyPy, Semgrep, lockfile check, Compose config validation). Python tests are local/manual or via `workflow_dispatch`.

```bash
make check              # mirrors CI lint/type gate
make test-core          # preferred first local gate
```
