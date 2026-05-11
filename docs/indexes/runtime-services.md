# Runtime Services Index

Quick orientation for Docker services, ingestion, the mini app, and the Telegram bot. Links to canonical docs instead of duplicating service tables or env rules.

## Docker Services

The canonical source of truth for Compose files, profiles, service names, ports, and env is [`../../DOCKER.md`](../../DOCKER.md). This section provides orientation only.

### Compose Profiles

| Profile | When You Need It |
|---|---|
| (default, no profile) | Core services: Postgres, Redis, Qdrant, BGE-M3, Docling, user-base, mini-app |
| `bot` | Telegram bot + LiteLLM proxy |
| `ingest` | Unified ingestion service |
| `ml` | Langfuse + ClickHouse + MinIO |
| `obs` | Loki + Promtail + Alertmanager |
| `voice` | LiveKit + SIP + voice agent (off by default) |

Common commands:

```bash
make docker-up          # default/unprofiled services
make docker-bot-up      # bot profile
make docker-ingest-up   # ingestion profile
make docker-ml-up       # ML/Langfuse profile
make docker-obs-up      # observability profile (Loki, Promtail, Alertmanager)
make monitoring-up      # observability alias with endpoint hints
make docker-ps          # list running containers
```

### Local Service Containers

For per-service build, healthcheck, and test details, see [`../../services/README.md`](../../services/README.md).

| Service | Local URL | Purpose |
|---|---|---|
| `bge-m3` | http://localhost:8000 | Dense + sparse + ColBERT embeddings |
| `docling` | http://localhost:5001 | PDF/DOCX → markdown parsing |
| `user-base` | http://localhost:8003 | Russian dense embeddings |

## Ingestion

The unified ingestion pipeline is the primary document ingestion path.

- **Package**: `src/ingestion/unified/`
- **CLI**: `uv run python -m src.ingestion.unified.cli`
- **Canonical docs**: [`../INGESTION.md`](../INGESTION.md), [`../GDRIVE_INGESTION.md`](../GDRIVE_INGESTION.md)

Quick commands:

```bash
make ingest-unified-preflight   # validate deps and env
make ingest-unified-bootstrap   # create/validate collection schema
make ingest-unified             # one-shot run
make ingest-unified-status      # state/DLQ status
make ingest-unified-logs        # container logs
```

Key concepts:
- Reads from `GDRIVE_SYNC_DIR`
- Uses Docling for parsing, BGE-M3 for embeddings
- Writes to Qdrant; tracks state in PostgreSQL
- Supports incremental updates and resume

See also: [`../QDRANT_STACK.md`](../QDRANT_STACK.md) for collection schema and bootstrap details.

## Mini App

Telegram Mini App backend (FastAPI) and frontend (React + Vite).

- **Backend entrypoint**: `mini_app/api.py`
- **Service name**: `mini-app-api`
- **Local port**: `8090`
- **Canonical doc**: [`../../mini_app/README.md`](../../mini_app/README.md)

Quick start:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d mini-app-api
curl -fsS http://localhost:8090/health
```

API surface:
- `GET /api/config` — UI questions + experts list
- `POST /api/start-expert` — Store deep-link payload
- `POST /api/phone` — Collect phone and create CRM lead
- `GET /health` — Service health

## Telegram Bot

Telegram transport layer and RAG orchestration.

- **Entrypoint**: `telegram_bot/main.py`
- **Bot class**: `telegram_bot/bot.py`
- **LangGraph pipeline**: `telegram_bot/graph/graph.py`
- **Canonical doc**: [`../../telegram_bot/README.md`](../../telegram_bot/README.md)

Key flows:
1. **Message/voice** → handlers (`telegram_bot/handlers/`)
2. **Query classification** → pipeline selection
3. **Cache check** → Redis semantic cache
4. **Retrieval** → hybrid search in Qdrant (dense + sparse + optional ColBERT rerank)
5. **Generation** → LiteLLM proxy
6. **Response** → Telegram message with citations

Subsystems:
- `telegram_bot/graph/` — LangGraph nodes, edges, and state
- `telegram_bot/services/` — Qdrant queries, cache, apartment search, CRM tools
- `telegram_bot/agents/` — Agent SDK RAG functions
- `telegram_bot/dialogs/` — Funnel UI and filter extraction
- `telegram_bot/middlewares/` — Throttling, i18n, error handling

Quick commands:

```bash
make run-bot           # native bot run (fast iteration)
make docker-bot-up     # bot in Docker
make test-bot-health   # local prerequisite check
python -m telegram_bot.preflight   # startup health check
```

## Voice Agent

LiveKit-powered voice path. Deferred by default.

- **Entrypoint**: `src/voice/agent.py`
- **RAG API**: `src/api/main:app`
- **Compose profile**: `voice` (intentionally off by default)

To start:

```bash
make docker-voice-up
```

See [`../../src/voice/`](../../src/voice/) for implementation details.
