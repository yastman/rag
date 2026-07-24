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
| PostgreSQL | Domain state (users, leads, funnel, favorites) |

An optional LangGraph supervisor + tool-routing layer exists in `telegram_bot/agents/` for CRM-style workflows (lead scoring, manager handoff, HITL confirmation). It is not required for the core Q&A path.

## Ingestion

`src/ingestion/unified/` — deterministic, idempotent, production-ready:

- SHA256-based file identity: re-ingesting the same file is a no-op.
- Idempotent upsert: changed files replace prior chunks by source path. Deleted source files are a known limitation — their chunks remain in Qdrant until manual cleanup.
- Error handling: failed documents are logged and skipped; `run_watch` retries on the next polling cycle (60 s). No DLQ or exponential backoff — orphaned chunks from deleted source files remain in Qdrant until manual cleanup (known limitation).
- Docling handles parsing in-process (native SDK, no HTTP sidecar); the unified pipeline handles chunking and embedding writes.

## Adapt to Your Domain

Replace the domain layer; keep the engine and infrastructure.

**Replaceable:** `telegram_bot/services/apartment_*` prompts and extraction logic, search schema fields, CRM/tool integrations, UI copy, i18n strings.

**Keep:** `src/core/`, `src/runtime/`, `src/ingestion/unified/`, Redis cache layer, Docker Compose profiles.

The current domain (real-estate/apartments) lives entirely in the adapter and service layers. Swapping it does not require touching the retrieval engine or pipeline.

## Quick Start

Prerequisites: Python 3.12, [`uv`](https://docs.astral.sh/uv/), Docker with Compose.

> Runtime: Docker Compose only. No k8s, no Mini App, no CRM/Kommo integration.
> Commands below are Linux/POSIX. See [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md) for
> PowerShell (Windows) equivalents.

```bash
uv sync                       # core + dev tools
uv sync --extra telegram      # bot dependencies
cp .env.example .env          # fill in credentials
make core-min-up              # start Qdrant + Redis via compose.core.yml (minimal)
# or
make core-up                  # start full sidecar stack (adds BGE-M3, PostgreSQL)
```

Run the bot natively:
```bash
make run-bot
```

Run the Compose bot stack:
```bash
make docker-bot-up
```

Notable configurable env vars (see `.env.example`): `QDRANT_QUANTIZATION_MODE`, `REDIS_MAX_CONNECTIONS`.

## Validation

> Linux/POSIX only. `make` targets require a POSIX shell.

```bash
make dev-setup       # Install dependencies, commit/push hooks, and local services
make check           # Commit-level Ruff lint + MyPy type checking
make pre-push        # Manual push gate: lint, format check, and core tests
make test-core       # Scope gate for src/core or src/runtime changes
make test            # Scope gate for adapter/service changes
make test-contract   # Scope gate for contract changes
make candidate-check # Authoritative local delivery gate
make test-full       # Major-candidate gate; manual and local only
make e2e-core-live   # Golden E2E: indexes fixture corpus, runs full spine through run_assistant_request
make qdrant-audit-indexes  # Audit Qdrant payload indexes
```

`make e2e-core-live` is the main proof of the core path. It exercises classification, retrieval, generation fallback, and runs without Telegram or voice. It requires local Qdrant and BGE-M3 running (`make core-up`).

Commit and push hooks run automatically after `make dev-setup`. GitHub runs no pytest; all pytest
suites are local. Run Linux portability and release verification through WSL or a container.

## Honest Current State

The core pipeline (`src/core/` + `src/runtime/`) is healthy and well-tested. The following surfaces are physically in-tree but are **archived/reference** — not part of the active production path, and being trimmed in open issues:

- **LangGraph dead nodes** — some graph nodes are no longer on the live execution path but remain in the file tree.

**Langfuse removed** — Langfuse SDK and tracing are fully removed (no `from langfuse` imports anywhere). The `@observe` decorators that remain are local **no-op shims** (`src.observability` / `telegram_bot.observability`) — not tracing. Observability is through structured logs.


The active production adapter is Telegram (`telegram_bot/`). Voice input is active via `telegram_bot/dialogs/` (catalog and demo dialogs).

## Project Map

| Area | Path |
|---|---|
| Core entrypoint | [`src/core/assistant.py`](src/core/assistant.py) |
| Pipeline + RAG engine | [`src/runtime/pipeline/`](src/runtime/pipeline/) |
| Telegram adapter | [`telegram_bot/`](telegram_bot/) |
| Domain tools + agents | [`telegram_bot/agents/`](telegram_bot/agents/), [`telegram_bot/services/`](telegram_bot/services/) |
| Unified ingestion | [`src/ingestion/unified/`](src/ingestion/unified/) |
| Compose runtime | [`compose.yml`](compose.yml), [`DOCKER.md`](DOCKER.md) |

## Documentation

| Document | Use it for |
|---|---|
| [`DOCKER.md`](DOCKER.md) | Compose services, profiles, ports, env, runtime contracts |

## Direction

The project is being hardened to a senior-grade codebase **without dropping any feature** — tracking epic [#2983](https://github.com/yastman/rag/issues/2983). In short: keep the full feature menu, remove migration cruft (dead LangGraph nodes, stale tests), decompose the `bot.py` god-object into per-feature handlers, document the feature map, and freeze the entry-path contracts — with **no new frameworks and no over-engineering**.

## License

This project is licensed under the [MIT License](LICENSE).
