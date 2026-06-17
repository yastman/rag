# Runtime Services Index

Quick orientation for Docker services, ingestion, archived Mini App notes, and the Telegram bot. Links to canonical docs instead of duplicating service tables or env rules.

## Docker Services

The canonical source of truth for Compose files, profiles, service names, ports, and env is [`../../DOCKER.md`](../../DOCKER.md). This section provides orientation only.

### Compose Profiles

| Profile | When You Need It |
|---|---|
| (default, no profile) | **Dev**: Postgres, Redis, Qdrant, BGE-M3, Docling. **VPS**: Postgres, Redis, Qdrant, BGE-M3, bot — the minimal RAG chatbot core. |
| `bot` | Telegram bot runtime using the in-process LiteLLM SDK router |
| `ingest` | Unified ingestion service |
| `ml` | Langfuse + ClickHouse + MinIO |
| `obs` | archived — see `archive/obs/` |
| `voice` | LiveKit + SIP + voice agent (off by default) |

> On VPS (`compose.yml:compose.vps.yml`), Docling, ingestion, and the
> ML platform (Langfuse/ClickHouse/MinIO) are gated behind the `vps-noncore`
> profile. See [DOCKER.md](../../DOCKER.md) for the full VPS runtime contract.

Common commands:

```bash
make docker-up          # default/unprofiled services
make docker-bot-up      # bot profile
make docker-ingest-up   # ingestion profile
make docker-core-up       # ML/Langfuse profile
# docker-obs-up / monitoring-up archived — see archive/obs/
make docker-ps          # list running containers
```

### Local Service Containers

For per-service build, healthcheck, and test details, see [`../../services/README.md`](../../services/README.md).

| Service | Local URL | Purpose |
|---|---|---|
| `bge-m3` | http://localhost:8000 | Dense + sparse + ColBERT embeddings |
| `docling` | http://localhost:5001 | PDF/DOCX → markdown parsing |

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

## Archived Mini App

The Telegram Mini App backend/frontend has been archived under
[`../../archive/mini_app/`](../../archive/mini_app/) and is no longer a Docker
service or required validation surface. Do not add `mini-app-api` or
`mini-app-frontend` back to default Compose, CI lint paths, or required tests
without a new product decision.

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
5. **Generation** → in-process LiteLLM SDK router
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

The voice path (LiveKit + SIP + voice agent) is an optional surface. It is not part of the core product path and is off by default.

- **Compose profile**: `voice` (intentionally off by default)
- **Implementation**: `src/voice/agent.py`, `src/api/main:app`
- **Archived docs**: [`../archive/observability/VOICE_TRACING_BASELINE.md`](../archive/observability/VOICE_TRACING_BASELINE.md)
