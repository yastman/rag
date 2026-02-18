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

Minimum env for bot profile:
- `TELEGRAM_BOT_TOKEN`
- `LITELLM_MASTER_KEY`
- at least one provider key: `CEREBRAS_API_KEY` or `GROQ_API_KEY` or `OPENAI_API_KEY`

## 2. Start Services

```bash
# Core services (default compose set)
make docker-up

# Bot runtime
make docker-bot-up

# Optional profiles
make docker-ml-up
make docker-ingest-up
make docker-voice-up
make monitoring-up
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

## 4. Development Gates

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

Optional broader gates:

```bash
make test
make test-full
```

## 5. Running Components Without Docker Wrapper

```bash
# Telegram bot
uv run python -m telegram_bot.main

# Unified ingestion
uv run python -m src.ingestion.unified.cli run --watch

# RAG API
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8080
```

## 6. Minimal Stack (Fast Iteration)

Use the `local-*` shortcuts (they now run a minimal subset from `docker-compose.dev.yml`) when full dev stack is unnecessary:

```bash
make local-up
make local-ps
make local-down
```

## 7. Common Issues

- `docker-bot-up` fails immediately: missing required env variables in `.env`.
- Slow first startup: BGE-M3 and Docling warm up and cache models.
- Ingestion status empty: verify `GDRIVE_SYNC_DIR` and collection bootstrap.
