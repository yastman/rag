<div align="center">

# RAG Q&A Chatbot

**Ask questions in natural language. Get answers grounded in your private documents.**

[![CI](https://github.com/yastman/rag/actions/workflows/ci.yml/badge.svg)](https://github.com/yastman/rag/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Docker Compose](https://img.shields.io/badge/runtime-Docker%20Compose-2496ED.svg)](DOCKER.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

</div>

---

A self-hostable RAG question-answer bot. Users ask in natural language via Telegram; the system retrieves grounded context from a Qdrant document store and generates a cited answer via an LLM. It is a Python modular monolith — one process, in-process function calls, with external sidecar services managed by Docker Compose.

The current live domain is real-estate/apartments. The domain layer is replaceable.

## Features

The live Telegram bot is a real-estate assistant: a RAG Q&A core plus a service menu. All actions are kept; only the question path is the pure RAG core, the rest is the (replaceable) domain layer.

| Menu action | What it does | Layer |
|---|---|---|
| 💬 Ask a question | RAG Q&A over the document store | **core** |
| 🏠 Find an apartment | Filtered catalog search | domain |
| 🔑 Services | Service info | domain |
| 📅 Book a viewing | Schedule a viewing | domain |
| 👤 Contact a manager | Human handoff (HITL) | domain/agent |
| 📌 My bookmarks | Saved listings | domain |
| 🎯 Demo | Guided demo flow | domain |

## How It Works

```
User message (Telegram)
        │
        ▼
run_assistant_request()          src/core/assistant.py
        │
        ▼
run_assistant_pipeline()         src/runtime/pipeline/assistant_pipeline.py
        │
        ├─ classify_query()      src/runtime/graph/nodes/classify.py
        │
        ▼
rag_pipeline()                   src/runtime/pipeline/rag.py
        │  cache check → hybrid Qdrant search (dense+sparse+ColBERT)
        │  → grade docs → optional rerank → optional query-rewrite loop
        │  returns: grounded document context
        │
        ▼
generate_answer()                src/runtime/generation/service.py
        │  LLM call with retrieved context
        │
        ▼
AssistantResult (answer + citations)
        │
        ▼
Telegram reply
```

`run_assistant_request` (`src/core/assistant.py`) is the single public entrypoint used by all adapters and the golden E2E test.

## Architecture

One Python process. Three layers:

| Layer | Path | Role |
|---|---|---|
| Adapter | `telegram_bot/` | Telegram interface — converts messages to/from `AssistantRequest` / `AssistantResult` |
| Public boundary | `src/core/` | `contracts.py` defines Protocol-based DI types; `assistant.py` is the entrypoint |
| Engine | `src/runtime/` | Pipeline, RAG, retrieval, generation, grounding |

External sidecar services (Docker Compose — **not** part of the Python binary):

| Service | Purpose |
|---|---|
| Qdrant | Vector store — dense, sparse, and ColBERT-style retrieval |
| BGE-M3 (ONNX) | Self-hosted embeddings served via a local API |
| Redis | Five independent caches: semantic answer, embedding, search, rerank, extraction. Version-prefixed keys; graceful degradation on miss |
| PostgreSQL | Persistent state (conversation, ingestion tracking) |
| Docling | Document parsing for ingestion (PDF, etc.) |

The current retrieval profile is `RETRIEVAL_PROFILE=bge_m3_full`: dense + sparse + ColBERT from local BGE-M3. This is a naming anchor documented in `.env.example`; runtime profile switching is a follow-up item.

An optional LangGraph supervisor + tool-routing layer exists in `telegram_bot/agents/` for CRM-style workflows (lead scoring, manager handoff, HITL confirmation). It is not required for the core Q&A path.

## Ingestion

`src/ingestion/unified/` — deterministic, idempotent, production-ready:

- SHA256-based file identity: re-ingesting the same file is a no-op.
- Idempotent upsert with orphan cleanup (deleted source files are removed from Qdrant).
- Dead-letter queue (DLQ) for failed documents, with retry and backoff.
- Docling handles parsing; CocoIndex handles chunking and embedding writes.

See [`docs/INGESTION.md`](docs/INGESTION.md) for operations and schema details.

## Adapt to Your Domain

Replace the domain layer; keep the engine and infrastructure.

**Replaceable:** `telegram_bot/services/apartment_*` prompts and extraction logic, search schema fields, CRM/tool integrations, UI copy, i18n strings.

**Keep:** `src/core/`, `src/runtime/`, `src/ingestion/unified/`, Redis cache layer, Docker Compose profiles.

The current domain (real-estate/apartments) lives entirely in the adapter and service layers. Swapping it does not require touching the retrieval engine or pipeline.

## Quick Start

Prerequisites: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Docker with Compose.

> Runtime: Docker Compose only. No k8s, no Mini App, no CRM/Kommo integration.

```bash
cp .env.example .env          # fill in credentials
make core-min-up              # start Qdrant + Redis (minimal)
# or
make core-up                  # start full sidecar stack (adds BGE-M3, Docling, PostgreSQL)
```

Run the bot natively:
```bash
make run-bot
```

Run the Compose bot stack:
```bash
make docker-bot-up
```

For the full setup ladder, environment variables, and troubleshooting, see [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md).

Notable configurable env vars (see `.env.example`): `QDRANT_QUANTIZATION_MODE`, `REDIS_MAX_CONNECTIONS`.

## Validation

```bash
make check          # Ruff lint + MyPy strict type checking
make test-core      # Fast core gate (~91 tests, ~8s) — run first for any src/core or src/runtime change
make test           # Broader fast gate (unit + graph paths) — run for adapter/service changes
make e2e-core-live  # Golden E2E: indexes fixture corpus, runs full spine through run_assistant_request
make qdrant-audit-indexes  # Audit Qdrant payload indexes
```

`make e2e-core-live` is the main proof of the core path. It exercises classification, retrieval, generation fallback, and runs without Telegram or voice. It requires local Qdrant and BGE-M3 running (`make core-up`).

CI runs static/lint guardrails only (Ruff, MyPy, Semgrep, lockfile check). Pytest suites are local/manual.

## Honest Current State

The core pipeline (`src/core/` + `src/runtime/`) is healthy and well-tested. The following surfaces are physically in-tree but are **archived/reference** — not part of the active production path, and being trimmed in open issues:

- **LangGraph dead nodes** — some graph nodes are no longer on the live execution path but remain in the file tree.
- **Langfuse removed** — Langfuse integration was removed; observability is through structured logs and the Loki/Promtail stack.

The active production adapter is Telegram (`telegram_bot/`). Voice input is active via `telegram_bot/dialogs/` (catalog and demo dialogs).

Other honest limits:

- Monitoring (Loki/Promtail/Alertmanager) is local/dev only.

## Project Map

| Area | Path |
|---|---|
| Core entrypoint | [`src/core/assistant.py`](src/core/assistant.py) |
| Pipeline + RAG engine | [`src/runtime/pipeline/`](src/runtime/pipeline/) |
| Telegram adapter | [`telegram_bot/`](telegram_bot/) |
| Domain tools + agents | [`telegram_bot/agents/`](telegram_bot/agents/), [`telegram_bot/services/`](telegram_bot/services/) |
| Unified ingestion | [`src/ingestion/unified/`](src/ingestion/unified/) |
| Compose runtime | [`compose.yml`](compose.yml), [`DOCKER.md`](DOCKER.md) |
| Full docs index | [`docs/README.md`](docs/README.md) |

## Documentation

| Document | Use it for |
|---|---|
| [`DOCKER.md`](DOCKER.md) | Compose services, profiles, ports, env, runtime contracts |
| [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md) | Local setup and validation ladder |
| [`docs/INGESTION.md`](docs/INGESTION.md) | Ingestion operations |
| [`docs/QDRANT_STACK.md`](docs/QDRANT_STACK.md) | Vector schema and Qdrant operations |
| [`docs/PIPELINE_OVERVIEW.md`](docs/PIPELINE_OVERVIEW.md) | Query, retrieval, and generation flows |
| [`docs/review/PROJECT_GUIDE.md`](docs/review/PROJECT_GUIDE.md) | Folder map and high-signal files |
| [`docs/review/ACCESS_FOR_REVIEWERS.md`](docs/review/ACCESS_FOR_REVIEWERS.md) | Safe review path before running commands |
| [`docs/architecture/STRUCTURE.md`](docs/architecture/STRUCTURE.md) | Module ownership map |

## Direction

The project is being hardened to a senior-grade codebase **without dropping any feature** — tracking epic [#2983](https://github.com/yastman/rag/issues/2983). In short: keep the full feature menu, remove migration cruft (dead LangGraph nodes, stale tests), decompose the `bot.py` god-object into per-feature handlers, document the feature map, and freeze the entry-path contracts — with **no new frameworks and no over-engineering**.

## License

This project is licensed under the [MIT License](LICENSE).
