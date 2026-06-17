# Canonical Project Structure and Layering Map

**Issue:** #2633 (ARCH-19)
**Status:** Authoritative after archival PRs for voice, API, k8s, and Voyage landed.
**Enforced by:** `tests/contract/test_canonical_structure_contract.py`

---

## Active Directory Layout

```
rag-fresh/
├── src/                        # Reusable assistant core + infrastructure
│   ├── core/                   # PUBLIC assistant entrypoint & product contract
│   ├── runtime/                # RAG pipeline, retrieval, generation, orchestration
│   │   ├── pipeline/           # Imperative assistant pipeline
│   │   ├── graph/              # LangGraph compat facade (builder + nodes)
│   │   ├── generation/         # LLM generation service & policy
│   │   ├── retrieval/          # Retrieval service
│   │   ├── grounding/          # Grounding / answer-policy
│   │   ├── llm/                # LLM router
│   │   ├── services/           # Low-level RAG helpers (cache, reranker, qdrant…)
│   │   └── integrations/       # Cache, embeddings, prompt manager
│   ├── adapters/               # Provider / SDK adapters (embeddings, LLM)
│   │   ├── embeddings/         # BGE-M3, OpenAI, local adapters
│   │   └── llm/                # LiteLLM adapter
│   ├── ingestion/              # Ingestion infrastructure
│   │   └── unified/            # CANONICAL ingestion pipeline (CocoIndex + Docling)
│   ├── retrieval/              # Search engines, reranker, topic classifier
│   ├── contextualization/      # Contextual embedding providers
│   ├── models/                 # Shared data models (apartment, embedding model)
│   ├── services/               # Shared service clients (BGE-M3, Kommo, vectorizers…)
│   ├── config/                 # Settings, constants, Qdrant policy
│   ├── security/               # PII redaction
│   └── utils/                  # Product events, serialization, structure parser
│
├── telegram_bot/               # Telegram adapter (the ONLY production channel)
│   ├── agents/                 # CRM + domain tools, HITL, agent factory
│   ├── services/               # Bot-layer business logic (catalog, scoring, handoff…)
│   ├── dialogs/                # aiogram-dialogs flows (catalog, CRM, funnel…)
│   ├── handlers/               # aiogram message/command handlers
│   ├── graph/                  # Compat facades over src/runtime/graph
│   ├── middlewares/            # Bot middlewares (i18n, throttling, error handler)
│   ├── integrations/           # Bot-specific integrations (cache, memory, prompts)
│   ├── pipelines/              # Bot-side pipeline client
│   ├── keyboards/              # Inline keyboard builders
│   ├── dialogs/                # (see above)
│   ├── models/                 # Bot-specific models
│   ├── constants/              # Bot constants
│   ├── locales/                # Fluent i18n bundles (en, ru, uk)
│   ├── config/                 # Bot YAML configs
│   └── bot.py / main.py        # Bot entry points
│
├── services/                   # External sidecar services (Docker images only)
│   ├── bge-m3-api/             # BGE-M3 embedding + rerank sidecar
│   ├── docling/                # Document parsing / chunking sidecar
│   └── user-base/              # Telegram user-base service
│
├── archive/                    # ARCHIVED surfaces — never imported by live code
│   ├── api/                    # FastAPI RAG API (archived)
│   ├── voice/                  # LiveKit voice agent (archived)
│   ├── mini_app/               # Telegram Mini App (archived)
│   └── k8s/                    # k3s manifests (archived)
│
├── tests/                      # Test tiers
│   ├── unit/                   # Fast unit tests
│   ├── contract/               # Static/structural contract tests
│   ├── integration/            # Service-integration tests
│   ├── e2e_core/               # Core E2E (Qdrant + BGE-M3, no Telegram)
│   ├── smoke/                  # Runtime smoke tests
│   └── …                       # eval, load, benchmark, chaos, regression
│
├── scripts/                    # Operational scripts (ingestion, eval, probes)
├── docker/                     # Compose helper configs (Qdrant, Postgres, monitoring)
├── docs/                       # All project documentation
│   └── architecture/           # THIS document and architecture artifacts
│
├── compose.yml                 # Primary Docker Compose runtime
├── compose.core.yml            # Minimal core stack (Qdrant + Redis only)
├── compose.dev.yml             # Dev overrides
├── Makefile                    # All local commands
└── pyproject.toml              # Python project, deps, tools
```

---

## Layer Definitions

### `src/core` — Public Assistant Entrypoint

The single canonical entry point for the assistant. Any adapter (Telegram, API,
tests) should call `run_assistant_request()` from `src/core/assistant.py` and
receive an `AssistantResult`. The product contract is `src/core/contracts.py`.

**Canonical files:**
- `src/core/assistant.py` — `run_assistant_request()` / `AssistantResult`
- `src/core/contracts.py` — typed state contracts
- `src/core/pipeline.py` — orchestration entry (delegates to `src/runtime`)

**Rule:** `src/core` imports `src/runtime` but never `telegram_bot`.

---

### `src/runtime` — RAG Pipeline and Orchestration

All retrieval, generation, grounding, LLM routing, caching, and pipeline logic.
Contains the imperative assistant pipeline and the LangGraph compatibility facade.

**Sub-packages:**
| Package | Purpose |
|---|---|
| `pipeline/` | Imperative `AssistantPipeline` — main runtime loop |
| `graph/` | LangGraph builder + nodes (compat facade) |
| `generation/` | LLM generation service, context, policy |
| `retrieval/` | Retrieval service wrapping `src/retrieval` |
| `grounding/` | Grounding / answer-policy checks |
| `llm/` | LLM router (LiteLLM) |
| `services/` | RAG helpers: cache policy, Qdrant, reranker, small-to-big, etc. |
| `integrations/` | Cache (Redis/semantic), embeddings, prompt manager |

**Rule:** `src/runtime` imports `src/adapters`, `src/retrieval`, `src/core`, and
`src/services` but never `telegram_bot`.

---

### `src/adapters` — Provider/SDK Adapters

Thin wrappers over provider SDKs (BGE-M3, OpenAI embeddings, LiteLLM).
No business logic; only protocol translation.

**Rule:** `src/adapters` must not import `src/runtime` or `telegram_bot`.

**Transitional exception:** `src/adapters/llm/litellm_provider.py` currently
imports `src.runtime.llm.create_litellm_chat_client` to reuse the LiteLLM
client factory. This coupling is tracked in the contract test allowlist and must
be resolved by moving the factory to `src/adapters/llm/` or a shared utility.

---

### `src/ingestion/unified` — Canonical Ingestion Pipeline

CocoIndex + Docling pipeline: file identity, parse, chunk, embed, upsert/delete
to Qdrant, retry, DLQ, state persistence in PostgreSQL.

**Rule:** ingestion imports `src/adapters` and `src/services` but never
`src/runtime` or `telegram_bot`.

---

### `telegram_bot` — Telegram Adapter

The production channel. Contains all Telegram-specific code: aiogram handlers,
dialogs, domain tools, CRM integration, HITL confirmation flows, keyboard
builders, and localization. It **may** import from `src/` freely but `src/` must
not import back into `telegram_bot`.

**Key sub-packages:**
| Package | Purpose |
|---|---|
| `agents/` | CRM tools, domain search tools, HITL interrupt, agent factory |
| `services/` | Catalog search, Kommo client, lead scoring, handoff, hot-lead |
| `graph/` | Compat facades over `src/runtime/graph` (thin re-exports) |
| `dialogs/` | User and manager menus, catalog, funnel, CRM dialogs |
| `handlers/` | Message/command handlers, phone collection |
| `integrations/` | Bot cache, memory (LangGraph checkpointer), prompt manager |
| `pipelines/` | Bot-side pipeline client |
| `middlewares/` | i18n, throttling, error handling, Langfuse middleware |

---

### `services/` — External Sidecar Services

Docker-only sidecar services. They expose HTTP APIs consumed by `src/` via
client modules in `src/services/`. They are **not** Python dependencies of the
monolith — the Python codebase calls them over HTTP.

| Service | Role |
|---|---|
| `services/bge-m3-api/` | BGE-M3 dense + sparse + ColBERT embedding sidecar |
| `services/docling/` | Document parsing and chunking sidecar |
| `services/user-base/` | Telegram user registration sidecar |

---

### `archive/` — Historical Surfaces

Code that was part of earlier iterations but is no longer part of the active
runtime. **Archived code must not be imported by any live `src/` or
`telegram_bot/` module.**

| Path | What was archived |
|---|---|
| `archive/api/` | FastAPI RAG API (moved to archive; use `src/core` directly) |
| `archive/voice/` | LiveKit voice agent (archived) |
| `archive/mini_app/` | Telegram Mini App backend + frontend (archived) |
| `archive/k8s/` | k3s manifests for core services (archived) |

---

## Import Direction (Allowed Flow)

```
telegram_bot  ──►  src/core  ──►  src/runtime  ──►  src/adapters
                       │               │
                       │               ▼
                       │          src/retrieval
                       │          src/services
                       │          src/models
                       │          src/config
                       │
                       ▼
               src/ingestion/unified  ──►  src/adapters
                                      ──►  src/services
```

**Forbidden directions:**

- `src/*` → `telegram_bot` (any direction)
- `src/adapters` → `src/runtime`
- `src/ingestion` → `src/runtime`
- anything → `archive/*` (archived code must be dead)

---

## Compatibility Shims (Temporary)

During the incremental monolith-core migration, some `telegram_bot/` paths are
thin re-export shims that forward to canonical `src/` locations:

| Shim path | Canonical location |
|---|---|
| `telegram_bot/graph/state.py` | `src/runtime/graph/state.py` |
| `telegram_bot/graph/config.py` | `src/runtime/graph/config.py` |
| `telegram_bot/scoring.py` | `src/scoring.py` |
| `telegram_bot/phone_utils.py` | `src/phone_utils.py` |
| `telegram_bot/services/content_loader.py` | `src/services/content_loader.py` |
| `telegram_bot/observability.py` | `src/observability.py` |

These shims are pinned by `tests/contract/test_runtime_phase1_modules_present_contract.py`
and must shrink over time.

---

## Canonical Entrypoints

| Use case | Entry point |
|---|---|
| Core E2E / tests / adapters | `src/core/assistant.py` → `run_assistant_request()` |
| Telegram bot | `telegram_bot/main.py` |
| Ingestion CLI | `src/ingestion/unified/cli.py` |
| BGE-M3 sidecar | `services/bge-m3-api/app.py` |
| Docling sidecar | `services/docling/` |

---

## Active vs Archived Quick Reference

| Path | Status |
|---|---|
| `src/core/` | ✅ Active — canonical assistant core |
| `src/runtime/` | ✅ Active — RAG pipeline and orchestration |
| `src/adapters/` | ✅ Active — provider/SDK adapters |
| `src/ingestion/unified/` | ✅ Active — canonical ingestion |
| `src/retrieval/` | ✅ Active — search engines, reranker |
| `src/services/` | ✅ Active — shared service clients |
| `telegram_bot/` | ✅ Active — Telegram adapter (production channel) |
| `services/bge-m3-api/` | ✅ Active — embedding sidecar |
| `services/docling/` | ✅ Active — parsing sidecar |
| `services/user-base/` | ✅ Active — user service sidecar |
| `archive/api/` | 🗃 Archived — FastAPI RAG API |
| `archive/voice/` | 🗃 Archived — LiveKit voice agent |
| `archive/mini_app/` | 🗃 Archived — Telegram Mini App |
| `archive/k8s/` | 🗃 Archived — k3s manifests |

---

## Related Documents

- [`src/core/README.md`](../../src/core/README.md) — core entrypoint contract
- [`src/runtime/README.md`](../../src/runtime/README.md) — runtime subsystem overview
- [`src/ingestion/README.md`](../../src/ingestion/README.md) — ingestion pipeline
- [`docs/PIPELINE_OVERVIEW.md`](../PIPELINE_OVERVIEW.md) — query + ingestion + voice flows
- [`DOCKER.md`](../../DOCKER.md) — Compose profiles, services, ports
- [`docs/review/PROJECT_GUIDE.md`](../review/PROJECT_GUIDE.md) — folder map for reviewers
- `tests/contract/test_canonical_structure_contract.py` — enforcing contract test
