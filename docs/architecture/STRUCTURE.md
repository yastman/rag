# Module Ownership Map

This document is the canonical reference for active directory ownership, layer
responsibilities, and allowed import directions. It is paired with
`tests/contract/test_canonical_structure_contract.py` (ARCH-019 / #2633) and
`.importlinter`. Keep them in sync when moving code.

---

## Layers

### `src/core/`

Public boundary of the monolith. Defines Protocol-based DI contracts
(`contracts.py`) and the single public entrypoint (`assistant.py` →
`run_assistant_request`). All adapters and tests must go through this layer.
Must not import `telegram_bot` or depend on runtime implementation details.

### `src/runtime/`

Product engine: RAG pipeline, retrieval, generation, grounding, and cache
policy. Implements the contracts declared in `src/core/`. Organised into
sub-packages: `pipeline/`, `retrieval/`, `generation/`, `grounding/`, `llm/`,
`graph/`, `integrations/`, `services/`. Must not import `telegram_bot`.

### `src/adapters/`

Provider/SDK adapters — thin wrappers over LiteLLM, BGE-M3, and other
embedding providers. Must not import `src/runtime` (adapters sit below the
runtime layer). One transitional exception is documented in the contract test
and must shrink.

### `src/ingestion/unified/`

Offline document indexing pipeline. Runs outside the query path. Handles
SHA256-based idempotency, Qdrant writes, DLQ, and ColBERT backfill. Parallel
to `src/runtime` — must not import it. Entry via `cli.py` and `orchestrator.py`.

### `telegram_bot/`

Telegram adapter layer. Converts Telegram messages to/from `AssistantRequest`
/ `AssistantResult`. Contains handlers, dialogs, keyboards, domain services
(apartment search, bookings, HITL handoff), and the LangGraph CRM agent.
May import `src/core` and `src/runtime`. The reverse is forbidden.

### `services/`

Docker sidecars only — not Python packages imported by the monolith.
`bge-m3-api/` serves dense/sparse/ColBERT embeddings via HTTP.
`docling/` serves document parsing via HTTP. Each has its own `pyproject.toml`.

---

## Directory Table

| Path | Role | Owner layer | Notes |
|---|---|---|---|
| `src/core/` | Public contracts and entrypoint | core | `contracts.py` (DI Protocols), `assistant.py` (entrypoint) |
| `src/core/assistant.py` | `run_assistant_request` — single public entrypoint | core | Used by all adapters and golden E2E test |
| `src/core/contracts.py` | Protocol-based DI type definitions | core | Must remain import-independent (enforced by importlinter) |
| `src/runtime/` | RAG engine, retrieval, generation, cache | runtime | No `telegram_bot` imports |
| `src/runtime/pipeline/` | `run_assistant_pipeline`, `rag_pipeline` orchestration | runtime | `rag.py` is the main retrieval spine |
| `src/runtime/pipeline/rag.py` | Hybrid retrieval pipeline (cache → search → grade → rerank → rewrite) | runtime | High-signal; call chain starts at `run_assistant_pipeline` |
| `src/runtime/generation/` | `generate_answer`, grounded LLM response generation | runtime | `service.py` holds the LLM call |
| `src/runtime/retrieval/` | Qdrant hybrid search execution | runtime | Called by `rag.py` |
| `src/retrieval/` | `topic_classifier.py` (query-path classifier); `search_engines.py` / `search_engine_shared.py` (back-compat shims re-exporting from `src/evaluation/retrieval/`) | runtime + ingestion | Imported by `rag.py`, `assistant_pipeline.py`, `_grade_rerank.py`, `_rewrite_cache.py`, and `ingestion/unified/qdrant_writer.py` |
| `src/evaluation/retrieval/` | Real `HybridRRFSearchEngine` implementation | runtime | `search_engines.py` holds the actual hybrid-search logic; `src/retrieval/` shims re-export from here |
| `src/runtime/grounding/` | Citation and grounding policy | runtime | Applied after generation |
| `src/runtime/llm/` | LiteLLM client factory and router | runtime | Shared by generation and adapters |
| `src/runtime/graph/` | LangGraph state and node wiring for the query graph | runtime | `config.py`, `state.py`, `nodes/` |
| `src/runtime/integrations/` | Redis cache, embeddings, prompt templates, polling lock | runtime | Five cache namespaces; graceful degradation |
| `src/runtime/services/` | Qdrant service client, RAG core helpers, preprocessor, reranker | runtime | `qdrant.py` is the main Qdrant wrapper |
| `src/adapters/` | Provider adapters for LLM and embeddings | adapters | Must not import `src/runtime` (one allowlisted exception) |
| `src/adapters/llm/` | LiteLLM provider adapter | adapters | Transitional coupling to `src.runtime.llm` — must be migrated |
| `src/adapters/embeddings/` | BGE-M3 and OpenAI embedding adapters | adapters | Implement protocol from `src/core/contracts.py` |
| `src/ingestion/` | Ingestion utilities and legacy helpers | ingestion | Active sub-package is `unified/` |
| `src/ingestion/unified/` | Production ingestion pipeline | ingestion | SHA256 idempotency, Qdrant upsert, DLQ, ColBERT backfill |
| `src/services/` | Low-level shared clients and DTOs (BGE-M3 HTTP client, vectorizers) | shared | Used by runtime and ingestion |
| `src/config/` | Settings, constants, Qdrant policy | shared | `settings.py` is the single config source |
| `src/models/` | Shared data models (apartment, embedding) | shared | |
| `src/observability/` | Langfuse shim, safe payload helpers, scores | shared | `get_client()` returns `None`; `@observe` is a pass-through |
| `src/security/` | PII redaction | shared | |
| `src/utils/` | Product events, serialization helpers | shared | |
| `telegram_bot/` | Telegram adapter: handlers, dialogs, keyboards, CRM/HITL UX | adapter | May import `src/*`; the reverse is forbidden |
| `telegram_bot/bot.py` | God-object bot registration (being decomposed — epic #2983) | adapter | Voice handlers and Mini App deeplink still live here |
| `telegram_bot/handlers/` | Per-feature message/callback handlers | adapter | `command_handlers.py` includes active Mini App deeplink |
| `telegram_bot/dialogs/` | aiogram-dialogs FSM flows (catalog, funnel, handoff, demo) | adapter | |
| `telegram_bot/services/` | Domain services: apartment search, extraction, formatting, CRM | adapter | `generate_response.py` is legacy — being trimmed |
| `telegram_bot/agents/` | LangGraph supervisor + tool routing for CRM workflows | adapter | Not required for core Q&A path |
| `telegram_bot/pipelines/` | Graph-compat pipeline adapter bridging bot to core | adapter | |
| `telegram_bot/integrations/` | Conversation memory, event stream, polling lock | adapter | |
| `telegram_bot/keyboards/` | Inline keyboard builders | adapter | |
| `telegram_bot/middlewares/` | Throttling, error handling, i18n, Langfuse middleware | adapter | |
| `services/bge-m3-api/` | Self-hosted BGE-M3 embedding sidecar (FastAPI + ONNX) | sidecar | Separate Python package; not imported by monolith |
| `services/docling/` | Document parsing sidecar (PDF etc.) | sidecar | Separate Python package; called via HTTP during ingestion |
| `tests/contract/` | Architectural contract tests | tests | Pin active dirs, import boundaries, and runtime rules |
| `scripts/` | Operational and CI scripts | ops | Not part of the Python package |

---

## Import Boundaries

Allowed directions (→ means "may import"):

```
telegram_bot  →  src/core  →  src/runtime
telegram_bot  →  src/runtime          (adapter over engine — allowed)
src/adapters  →  src/core             (allowed)
src/ingestion →  src/services         (allowed)
src/ingestion →  src/core             (allowed)
src/runtime   →  src/retrieval        (topic_classifier, search engine shims)
src/ingestion →  src/retrieval        (topic_classifier via qdrant_writer.py)
```

Forbidden directions (enforced by contract tests and importlinter):

```
src/core      ✗→  telegram_bot
src/runtime   ✗→  telegram_bot
src/adapters  ✗→  src/runtime         (except documented transitional allowlist)
src/ingestion ✗→  src/runtime
src/*         ✗→  archive/
```

### Transitional exceptions

| File | Imports | Why | Action |
|---|---|---|---|
| `src/adapters/llm/litellm_provider.py` | `src.runtime.llm` | Reuses LiteLLM client factory | Move factory to `src/adapters/llm/` or a shared utility (#2633) |

---

## High-Signal Entrypoints

`src/core/assistant.py` — `run_assistant_request(request, deps)` is the **single
public entrypoint** for all adapters and the golden E2E test. Calls
`run_assistant_pipeline` in `src/runtime/pipeline/assistant_pipeline.py`.

`src/runtime/pipeline/rag.py` — `rag_pipeline()` is the retrieval spine:
semantic cache check → hybrid Qdrant search (dense + sparse + ColBERT) →
relevance grading → optional rerank → optional query-rewrite loop →
returns grounded document context.

`src/runtime/generation/service.py` — `generate_answer()` takes retrieved
context and calls the LLM to produce a cited answer.

`src/ingestion/unified/cli.py` — CLI entrypoint for the production ingestion
pipeline; delegates to `orchestrator.py` for run coordination.

---

*Refs: #2633 (ARCH-019), #3019 (ARCH-009), epic #2983. Enforced by
`tests/contract/test_canonical_structure_contract.py` and `.importlinter`.*
