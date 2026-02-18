# Project Stack

Current stack snapshot for this repository as of 2026-02-18.

## Runtime And Tooling

| Area | Stack |
| --- | --- |
| Language | Python `>=3.11` (recommended `3.12`) |
| Package/deps | `uv`, `pyproject.toml`, `uv.lock` |
| Lint/type/tests | Ruff, MyPy, pytest + xdist |
| Local orchestration | Docker Compose v2 (`docker-compose.dev.yml`, `docker-compose.local.yml`) |
| Server orchestration | k3s + Kustomize (`k8s/overlays/*`) |

## Core Application Components

| Component | Path | Role |
| --- | --- | --- |
| Telegram bot | `telegram_bot/` | Main user-facing interface, LangGraph orchestration |
| Graph pipeline | `telegram_bot/graph/` | Classification, guard, cache, retrieval, rerank, generation |
| Bot services | `telegram_bot/services/` | Qdrant, LLM, BGE-M3 clients, reranker, routing |
| RAG API | `src/api/` | FastAPI wrapper around the same graph runtime |
| Voice agent | `src/voice/` | LiveKit agent that calls `src/api` |
| Unified ingestion | `src/ingestion/unified/` | CocoIndex flow + Docling + Qdrant writer + state manager |
| Retrieval/evaluation | `src/retrieval/`, `src/evaluation/` | Search variants, metrics, offline eval |

## Data And Infra Services

| Service | Purpose |
| --- | --- |
| Qdrant | Hybrid dense+sparse retrieval storage |
| Redis | Cache and runtime state (`REDIS_PASSWORD` is required in compose/k8s deployments) |
| PostgreSQL (pgvector image) | App/ingestion/observability state |
| BGE-M3 API | Local dense/sparse embeddings and rerank endpoint |
| Docling | Document parsing/chunk extraction |
| LiteLLM | LLM gateway with fallback chain |
| Langfuse + ClickHouse + MinIO + redis-langfuse | Tracing/analytics |
| Loki + Promtail + Alertmanager | Log-based monitoring and alerting |

## Deployment Surfaces

- Local dev: `docker-compose.dev.yml` via `make docker-up` / `make docker-bot-up` / `make docker-full-up`
- Minimal local: `docker-compose.local.yml` via `make local-up` / `make local-down`
- VPS compose: `docker-compose.vps.yml`
- k3s overlays: `k8s/overlays/core`, `k8s/overlays/bot`, `k8s/overlays/ingest`, `k8s/overlays/full`

## Canonical Operations Docs

- `docs/PIPELINE_OVERVIEW.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/QDRANT_STACK.md`
- `docs/INGESTION.md`
- `docs/ALERTING.md`
- `DOCKER.md`
