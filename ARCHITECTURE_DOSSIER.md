# RAG-Fresh — Architecture Dossier (current-state, for external review)

> **Status:** dated review snapshot, not live architecture authority. Use
> [`README.md`](README.md) and [`docs/architecture/STRUCTURE.md`](docs/architecture/STRUCTURE.md)
> for current ownership, and
> [`docs/architecture/RAG_VPS_V2_PROPOSED.md`](docs/architecture/RAG_VPS_V2_PROPOSED.md) for the
> proposed reusable v2 target.
>
> **What this is:** a self-contained snapshot of the system's structure, data flow,
> dependencies, external services, and known technical debt — written to be handed to an
> external reviewer (e.g. ChatGPT Pro) with no prior context. It is **not** a PRD (no
> forward requirements); it is a *current-state architecture dossier*.
>
> **Generated:** 2026-07-06, from a code-index audit at commit `c43f690`.
> **Scale:** ~1079 files, ~174k LOC, ~10.4k symbols, Python 3.12.
> **Honesty note:** the live production path is healthy; several in-tree subsystems are
> dead/archived and actively being removed under epic **#2983**. Section 10 lists them so a
> reviewer does not mistake residue for architecture.

---

## 1. System overview

A self-hostable **Retrieval-Augmented-Generation Q&A chatbot**. A user asks a question in
natural language over Telegram; the system retrieves grounded context from a Qdrant document
store and an LLM returns a **cited** answer. The live domain is real-estate/apartments; the
domain layer (prompts, tools, catalog schema, i18n) is replaceable — the RAG engine is not.

**Key architectural decision:** it is a **Python modular monolith** — one process, in-process
function calls, *not* microservices. Heavy work (vector store, embeddings, cache, domain DB)
is delegated to four external sidecar containers via Docker Compose. There is no k8s, no web
Mini-App, no message bus.

```
                    ┌─────────────────────── one Python process ───────────────────────┐
   Telegram  ──▶    │  telegram_bot/ (adapter)  →  src/core/ (boundary)  →  src/runtime/ │
   user             │                                                        (engine)    │
                    └───────┬───────────────┬───────────────┬──────────────────┬─────────┘
                            │ HTTP           │ TCP           │ HTTP             │ TCP
                        ┌───▼───┐        ┌───▼───┐       ┌────▼────┐        ┌────▼────┐
                        │Qdrant │        │ Redis │       │ BGE-M3  │        │Postgres │
                        │vectors│        │5 caches│      │embeddings│       │domain DB│
                        └───────┘        └───────┘       └─────────┘        └─────────┘
```

---

## 2. The spine (the one flow worth memorising)

A question becomes a cited answer through a fixed call chain. This is the load-bearing path;
everything else is domain/adapter dressing.

```
Telegram message
  → run_assistant_request            src/core/assistant.py      (single public entrypoint)
    → run_assistant_pipeline         src/runtime/pipeline/assistant_pipeline.py
      → classify_query               src/runtime/routing/classify.py
      → rag_pipeline                 src/runtime/pipeline/rag.py
          1. cache check             src/runtime/integrations/cache.py (semantic answer cache)
          2. embed query             _bge_m3_query_bundle_cls → BGE-M3 /encode/hybrid
          3. hybrid Qdrant search    src/runtime/qdrant/service.py (dense + sparse + ColBERT)
          4. grade docs              src/runtime/pipeline/_grade_rerank.py
          5. optional rerank         (ColBERT MaxSim)
          6. optional query-rewrite loop (up to MAX_REWRITE_ATTEMPTS)
      → generate_answer              src/runtime/generation/service.py (LLM via LiteLLM router)
    → AssistantResult (answer + citations)
  → Telegram reply
```

`run_assistant_request` is the **only** public entrypoint used by every adapter and by the
golden E2E test. It is DI-based: dependencies are `Protocol` types defined in
`src/core/contracts.py`, so the engine can be driven with fakes.

---

## 3. Layered architecture (enforced by import-linter)

Three layers, inner cannot import outer. Contracts live in `pyproject.toml`
`[tool.importlinter]` and are checked in CI via `lint-imports`:

| Layer | Path | Role | Import rule |
|---|---|---|---|
| Adapter | `telegram_bot/` | Telegram I/O; converts messages ↔ `AssistantRequest`/`AssistantResult` | may import runtime + core |
| Public boundary | `src/core/` | `contracts.py` (Protocol DI types), `assistant.py` (entrypoint), `telemetry.py` | must NOT import `telegram_bot` |
| Engine | `src/runtime/` | pipeline, RAG, retrieval, generation, grounding, integrations | must NOT import `telegram_bot` |
| — | `archive/`, `services/` | archived/reference & standalone sidecars | `src/` must NOT import `archive` |

Enforced invariants: *Core must not import telegram_bot*, *Runtime must not import
telegram_bot*, *Core contracts layer is import-independent*, *src must not import archive*.

---

## 4. Repository map

### `src/` — the engine (framework-agnostic RAG core)

| Path | Role |
|---|---|
| `src/core/` | Public boundary: `assistant.py` (entrypoint), `contracts.py` (Protocol DI), `app.py`, `telemetry.py` |
| `src/runtime/pipeline/` | The spine: `assistant_pipeline.py`, `rag.py` (24k), `_retrieve.py`, `_cache_stage.py`, `_grade_rerank.py`, `_rewrite_cache.py` |
| `src/runtime/qdrant/service.py` | Qdrant hybrid search (dense/sparse/ColBERT, weighted RRF/DBSF) — 32k, central |
| `src/runtime/generation/` | LLM answer generation: `service.py`, `prompts.py`, `policy.py`, `streaming.py`, `messages.py` |
| `src/runtime/integrations/` | `cache.py` (30k, the 5 Redis caches + `CacheLayerManager`), `embeddings.py` (BGE-M3 shims), `prompt_manager.py` |
| `src/runtime/retrieval/` | Retrieval service facade |
| `src/runtime/grounding/` | Grounding/citation policy |
| `src/runtime/llm/router.py` | Native LiteLLM SDK boundary (provider-agnostic LLM calls) |
| `src/runtime/graph/` | Vestigial namespace: `nodes/transcribe.py` only (**dead** — no importers); classify/guard/config moved out in #3207 to `src/runtime/routing/`, `src/runtime/safety/`, `src/runtime/config.py` |
| `src/runtime/services/` | Query preprocessing, small-to-big, cache policy, coverage mode, `colbert_reranker.py` (**dead**) |
| `src/adapters/embeddings/` | `bge_m3.py` (`BgeM3EmbeddingProvider` — canonical), `openai_embeddings.py`, `local_bge_m3.py` (**dead**), `base.py` |
| `src/adapters/llm/` | `base.py` (LLM error taxonomy) |
| `src/services/` | `bge_m3_client.py` (HTTP SDK for BGE-M3), `_retry.py`, `content_loader.py`, `vectorizers.py`; `kommo_*` (**dead**, P26), `voyage.py` (**dead**) |
| `src/ingestion/` | `markdown.py` (live parse+chunk, stdlib, #3235), `chunker.py` (shared `Chunk`); `unified/` (the live pipeline) |
| `src/ingestion/unified/` | `flow.py` (stateless scan→parse→embed→upsert), `qdrant_writer.py` (27k), `config.py`, `manifest.py`, `commands.py`, `colbert_backfill.py` |
| `src/models/apartment.py` | Domain model (HardFilters etc.); `embedding_model.py` (**dead** in-process singletons) |
| `src/security/pii_redaction.py` | `PIIRedactor` — query PII redaction (on the hot path) |
| `src/config/` | `settings.py`, `constants.py`, `services.yaml` |
| `src/observability/` | **no-op** `@observe` shims (Langfuse removed, #2844) + structured-log helpers |
| `src/contextualization/` | anthropic/groq/openai contextualizers — **dead** (providers extra emptied #2893) |

### `telegram_bot/` — the adapter + domain layer

| Path | Role |
|---|---|
| `main.py` → `lifecycle/` | Process bootstrap: `lifecycle.py` (22k), `services.py` (DI wiring → `build_services`), `postgres_bootstrap.py` |
| `bot.py` | **34k god-object** dispatcher — being decomposed into per-feature handlers (#2983) |
| `pipeline/supervisor.py` | **43k** query supervisor orchestrating the RAG call |
| `handlers/` | Feature handlers: catalog, favorites, phone_collector, feedback, demo, handoff, commands |
| `dialogs/` | aiogram-dialog FSMs: `catalog/`, `filter/`, `funnel/`, `demo`, `viewing`, `settings`, voice |
| `services/rag/` | Bot-side RAG helpers — **legacy mirror** of `src/runtime/*` (dedup/removal candidate) |
| `services/apartment/` | Domain: filter extraction, catalog rendering, apartments service |
| `services/crm/` | Kommo CRM — **dead**, P26 |
| `services/generation/` | Response formatting, streaming, session summary |
| `services/observability/` | Redis monitor, funnel analytics; `nurturing_scheduler.py` (**dead**, apscheduler) |
| `agents/` | **Entire dir dead** — LangGraph supervisor + CRM/manager/apartment tools (P26 removal) |
| `pipelines/` | Client-direct pipeline entrypoints (`client.py`) + pre-agent state contract |
| `middlewares/` | i18n (fluentogram), throttling (cachetools TTLCache), error handler, fsm_cancel |
| `preflight/` | Startup checks + remediation (Qdrant/Redis/BGE-M3 URL validation) |
| `locales/{ru,en,uk}/` | fluent `.ftl` translations |

### `services/` — standalone sidecar source

| Path | Role |
|---|---|
| `services/bge-m3-api/` | Self-hosted **ONNX** BGE-M3 embedding service (FastAPI): `app.py` (22k), `config.py`, `Dockerfile`. Endpoints `/health` `/encode/{dense,sparse,hybrid,colbert}` `/rerank` `/metrics` |

---

## 5. External services (Docker Compose)

All four are load-bearing; none can be removed without dropping a feature.

| Service | Image | Purpose | Notes |
|---|---|---|---|
| **qdrant** | `qdrant/qdrant:v1.18.3` | Vector store (dense + sparse + ColBERT); also the ingestion idempotency store | storage config (`on_disk_payload`, `indexing_threshold_kb`) mounted to cap growth |
| **redis** | `redis:8.6.3` | Five independent caches: semantic-answer, embedding, search, rerank, extraction | version-prefixed keys; graceful degradation on miss |
| **bge-m3** | built ONNX service | Self-hosted embeddings + optional ColBERT rerank | cold-start model load up to ~7 min |
| **postgres** | `postgres:17` | Bot real-estate **domain DB** only (users/leads/funnel/favorites) | Plain PostgreSQL 17 (pgvector removed — not required by runtime) |
| bot | built | The Telegram adapter process | depends on all four healthy |
| ingestion | built (profile `ingest`/`full`) | Document scan→parse→embed→upsert loop | stateless; no PostgreSQL dependency (idempotency via Qdrant payloads) |

Ingestion is stateless: idempotency is SHA-256 content identity written into Qdrant payloads;
there is no external state DB (the former Postgres orchestrator was removed).

---

## 6. Dependencies (`pyproject.toml`)

**Core (lean base, every package has a live import):** `openai`, `qdrant-client`, `redis`,
`redisvl`, `pydantic`(+settings), `httpx`, `tenacity`, `pyyaml`, `litellm`, `python-dotenv`,
`typing-extensions`, `numpy`, `aiohttp`, `requests` (last two are transitive safety-pins),
`phonenumbers`.

**Extras:**
- `telegram` — aiogram, aiogram-dialog, fluentogram, cachetools, asyncpg, uvloop **+ langgraph, langchain-core (dead, being removed P26)**.
- `bge-extras` — fastapi test dependencies for the BGE-M3 service (`docling-native` removed by #3235).
- `ml-local` — FlagEmbedding, torch, torchvision, sentence-transformers, scipy **(entirely dead — no live import; removable, saves multi-GB torch)**.
- `eval` — ragas **(dead, CVE-isolated, being removed)**.
- `bge-extras` — fastapi, httpx (service tests only).
- `providers` — empty (anthropic/groq removed #2893).

**Dev tooling:** ruff, mypy, pylint, bandit, vulture, pytest(+asyncio/xdist/cov/timeout),
deptry, pip-audit, import-linter, radon, interrogate.

**Known dependency gaps (from audit):** `fluent_compiler` is *live* (i18n) but *undeclared*
(only transitively present); `voyageai`/`apscheduler` are *imported by dead code only*.

---

## 7. Ingestion pipeline (`src/ingestion/unified/`)

Deterministic, idempotent, in-process:

- **Markdown-only stdlib parser** (`markdown.py`, #3235) parses documents in-process —
  no converter SDK, no HTTP sidecar (`docling-serve` and the Docling SDK removed by #3235).
- SHA-256 file identity: re-ingesting an unchanged file is a no-op; a changed file's chunks
  are atomically replaced by source path.
- Chunks are embedded via the BGE-M3 HTTP service (`/encode/hybrid`, one forward pass →
  dense+sparse+ColBERT) and upserted into Qdrant by `QdrantHybridWriter.upsert_chunks_sync`.
- `run_watch` polls the sync dir every 60 s. Failed docs are logged & skipped (no DLQ;
  orphaned chunks from deleted source files remain until manual cleanup — known limitation).

---

## 8. Caching (Redis, `src/runtime/integrations/cache.py`)

`CacheLayerManager` owns five independent caches, all version-prefixed with graceful
degradation on miss: **semantic answer** (RedisVL `SemanticCache` + `BgeM3CacheVectorizer`,
1024-dim), **embedding**, **search**, **rerank**, **extraction**. Cache invalidates on
version bump.

---

## 9. Test topology

~230 test files across a 12-tier pyramid. CI runs **static/lint guardrails only** (Ruff,
MyPy, Semgrep, lockfile, compose-config); pytest suites are local/manual.

| Tier | Dir | Gate command | Runs |
|---|---|---|---|
| Unit | `tests/unit/` (~150) | `make test-core` (91 tests ~8s), `make test` | fast, mocked |
| Contract | `tests/contract/` (~110) | `make test-contract` | static-analysis invariants (layering, dead-code-removed, dependency hygiene, migration locks) |
| Integration | `tests/integration/` | `make test-integration[-full]` | real Qdrant/Redis/APIs |
| Smoke | `tests/smoke/` | `make test-smoke` | live-service health |
| E2E | `tests/e2e/` + `tests/e2e_core/` (harness) | `make e2e-core-live` | full spine through `run_assistant_request` |
| Chaos / Load / Regression / Characterization | resp. dirs | selective | resilience, throughput, golden snapshots |
| Baseline | `tests/baseline/` | — | **empty** (Langfuse metrics removed) — removable |

Test-hygiene is itself guarded by contract tests (`test_no_new_duplicate_test_names`,
`test_no_cross_lane_markers_under_unit`, `test_no_misleading_test_prefix_contract`,
`test_dedupe_test_files_1996_contract`).

**Audit-flagged test debt (in-flight):** ~40 orphan unit tests exercising already-dead code;
live-spine tests trapped in the dead `agents/` dir (`agents/test_rag_pipeline.py` 85k must be
rescued *before* the dir is swept); monster files (`test_bot_handlers.py` 251k) to split with
the `bot.py` decomposition; ~12 swarm/Kiro contract tests that test *agent tooling* not the
product; landed migration-lock contracts to retire.

---

## 10. Known technical debt & in-flight cleanup (epic #2983)

The project is being hardened to senior-grade **without dropping any feature**. Active
roadmap phases and their intent (a reviewer should read residue below as *scheduled for
removal*, not as architecture):

| Phase | Scope |
|---|---|
| P23 | Docling post-migration stabilization; remove dead `document_parser.py`/`indexer.py`/`hybrid_chunker.py`/`contextual_*`; fix `.pptx` format-set bug |
| P24 | BGE-M3 service test coverage; delete dead in-process FlagEmbedding cluster; remove `ml-local` (torch) extra |
| P25 | Remove Langfuse residue (SDK gone; `@observe` are no-op shims) |
| P26 | Remove unused agent/CRM/dead-graph layer + `langgraph`/`langchain`/`ragas` deps (owner-confirmed unused) |
| P28 | Lean-monolith gaps: delete `voyageai`/`apscheduler` dead clusters + dead `src/api`+`src/contextualization`; declare `fluent_compiler` |

**Dead subsystems physically in-tree (being removed):** `telegram_bot/agents/`, LangGraph
builder, Kommo CRM, `src/contextualization/`, in-process FlagEmbedding
(`local_bge_m3.py`, `embedding_model.py`), `document_parser.py`, `indexer.py`,
`hybrid_chunker.py`, `contextual_loader/schema.py`, `voyage.py`, `reranker.py`,
`colbert_reranker.py`, `services/user-base` (archived). (`src/api/` removed, #3212.)

**Hotspots (churn × complexity):** `src/runtime/pipeline/rag.py`, `telegram_bot/agents/rag_tool.py`
(dead), `telegram_bot/bot.py` (god-object), `telegram_bot/pipeline/supervisor.py`.

---

## 11. Questions a reviewer might evaluate

1. Is the 3-layer split (adapter → core boundary → runtime engine) clean enough, or is the
   `telegram_bot/services/rag/*` legacy mirror of `src/runtime/*` a smell worth collapsing?
2. Is the `bot.py` (34k) + `supervisor.py` (43k) concentration the main structural risk?
3. Is 4 external services the right minimum for a self-hostable RAG bot, or can the domain
   Postgres be folded away without losing the apartment features?
4. Is the embedding client stack (HTTP SDK → provider adapter → legacy shims) over-layered?
5. Is the contract-test tier (~110 static guards) proportionate, or ossified around past
   migrations?

---

*End of dossier. Paths are given as inline code (not links) so this file is portable and
self-contained. Line/size figures are as of commit `c43f690`, 2026-07-06.*
