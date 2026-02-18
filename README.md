***REMOVED*** Contextual RAG Pipeline

Production RAG system with a LangGraph Telegram bot, hybrid retrieval in Qdrant, unified CocoIndex ingestion, optional voice agent (LiveKit), CRM integration (Kommo lead scoring, nurturing, funnel analytics), and Docker/k3s deployment paths.

***REMOVED******REMOVED*** Runtime Snapshot

- Python: `>=3.11` (recommended `3.12`)
- Package manager: `uv`
- Current project version: `2.14.0` (`pyproject.toml`)
- Primary local orchestration: `docker-compose.dev.yml` + `Makefile`

***REMOVED******REMOVED*** Quick Start

```bash
uv sync
cp .env.example .env

***REMOVED*** Core runtime: postgres, redis, qdrant, bge-m3, user-base, docling
make docker-up

***REMOVED*** Bot path (adds litellm + telegram bot)
make docker-bot-up

***REMOVED*** Optional stacks
make docker-ml-up       ***REMOVED*** langfuse + mlflow + clickhouse + minio
make monitoring-up      ***REMOVED*** loki + promtail + alertmanager
make docker-ingest-up   ***REMOVED*** unified ingestion service
make docker-voice-up    ***REMOVED*** rag-api + livekit + sip + voice-agent

***REMOVED*** Validation gate
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

***REMOVED******REMOVED*** Main Commands

- `make docker-up` / `make docker-down` / `make docker-ps`
- `make local-up` / `make local-down` (minimal subset from `docker-compose.dev.yml`)
- `make ingest-unified`, `make ingest-unified-watch`, `make ingest-unified-status`
- `make k3s-core`, `make k3s-bot`, `make k3s-ingest`, `make k3s-full`

***REMOVED******REMOVED*** Entry Points

- Telegram bot: `uv run python -m telegram_bot.main`
- RAG API: `uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8080`
- Unified ingestion CLI: `uv run python -m src.ingestion.unified.cli --help`
- Voice agent: `uv run python -m src.voice.agent`

***REMOVED******REMOVED*** Documentation

- `DOCKER.md` - Docker compose files, profiles, service map, env requirements
- `docs/PROJECT_STACK.md` - current architecture and subsystem map
- `docs/PIPELINE_OVERVIEW.md` - ingestion/query/voice runtime flows
- `docs/LOCAL-DEVELOPMENT.md` - local setup and validation flow
- `docs/QDRANT_STACK.md` - Qdrant collections, vector schema, operations
- `docs/INGESTION.md` - unified ingestion runbook and troubleshooting
- `docs/ALERTING.md` - Loki/Alertmanager setup and test flow

***REMOVED******REMOVED*** Agent Instructions

Repository-level agent workflow and validation rules live in `AGENTS.md` and scoped `AGENTS.override.md` files.
