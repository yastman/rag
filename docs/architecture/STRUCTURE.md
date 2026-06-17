# Canonical Project Structure and Layering Map

**Issue:** #2633 (ARCH-19), extended by #2721 (directory ownership audit)
**Status:** Authoritative after archival PRs for voice, API, k8s, and Voyage landed.
**Enforced by:** `tests/contract/test_canonical_structure_contract.py`

---

## Directory Ownership Map

Canonical table for every major directory. Answers: what it does, who owns it, whether it is active/optional/archived, what may import it, what tests cover it, and what docs describe it.

| Directory | Purpose | Owner layer | Status | Allowed imports | Tests | Docs | Action |
|---|---|---|---|---|---|---|---|
| `src/core/` | Public assistant entrypoint: `run_assistant_request()`, `AssistantResult`, typed state contracts | core | ✅ Active | `src/runtime`, `src/services`, `src/config`, `src/models` | `tests/unit/core/`, `tests/contract/test_core_*.py` | `src/core/README.md`, `docs/designs/unified-assistant-entrypoint-contract.md` | Canonical; do not add domain logic here |
| `src/runtime/` | RAG pipeline, retrieval, generation, grounding, LLM routing, orchestration | runtime | ✅ Active | `src/adapters`, `src/retrieval`, `src/core`, `src/services`, `src/config`, `src/models` | `tests/unit/runtime/`, `tests/integration/test_graph_paths.py` | `src/runtime/README.md`, `docs/PIPELINE_OVERVIEW.md` | Never import `telegram_bot` |
| `src/runtime/pipeline/` | Imperative `AssistantPipeline` — main runtime loop | runtime | ✅ Active | same as `src/runtime/` | `tests/unit/runtime/` | `src/runtime/README.md` | Primary orchestration path (ADR-0019) |
| `src/runtime/graph/` | LangGraph compat facade (builder + nodes) | runtime | ✅ Active (transitional) | same as `src/runtime/` | `tests/unit/graph/`, `tests/integration/test_graph_paths.py` | `src/runtime/README.md` | Migration target — new features go to `pipeline/` |
| `src/adapters/` | Provider/SDK adapters: BGE-M3, OpenAI embeddings, LiteLLM | adapters | ✅ Active | `src/config`, `src/models` | `tests/unit/adapters/` | `src/runtime/README.md` | Must not import `src/runtime` or `telegram_bot` |
| `src/adapters/llm/` | LiteLLM adapter | adapters | ✅ Active (transitional coupling) | `src/config` | `tests/unit/adapters/` | `docs/engineering/sdk-registry.md` | Tracked coupling in `tests/data/known_layering_violations.json`; resolve by moving factory to adapters |
| `src/ingestion/` | Ingestion infrastructure: CocoIndex flow, Docling client, chunker, indexer | ingestion | ✅ Active | `src/adapters`, `src/services`, `src/config`, `src/models` | `tests/unit/ingestion/`, `tests/integration/test_unified_ingestion_e2e.py` | `docs/INGESTION.md`, `src/ingestion/README.md` | Never import `src/runtime` or `telegram_bot` |
| `src/ingestion/unified/` | Canonical CocoIndex+Docling pipeline: file identity, upsert/delete, retry, DLQ, PostgreSQL state | ingestion | ✅ Active | `src/adapters`, `src/services`, `src/config` | `tests/unit/ingestion/`, `tests/integration/` | `docs/INGESTION.md`, `src/ingestion/unified/AGENTS.override.md` | Canonical ingestion path |
| `src/retrieval/` | Search engines, reranker, topic classifier | runtime | ✅ Active | `src/adapters`, `src/services`, `src/config`, `src/models` | `tests/unit/retrieval/`, `tests/unit/test_search_engines.py` | `src/retrieval/README.md` | |
| `src/services/` | Shared service clients: BGE-M3 HTTP client, vectorizers, content loader, handoff state | services | ✅ Active | `src/config`, `src/models` | `tests/unit/services/` | `src/runtime/README.md` | Low-level clients only; no business logic |
| `src/models/` | Shared data models (apartment/catalog model, embedding model) | core | ✅ Active | none | `tests/unit/models/` | `src/models/README.md` | Domain-specific; replace for a different vertical |
| `src/config/` | Settings (Pydantic), constants, Qdrant policy | infra | ✅ Active | none | `tests/unit/config/`, `tests/unit/test_settings*.py` | `src/config/README.md` | |
| `src/security/` | PII redaction utilities | infra | ✅ Active | `src/config` | `tests/unit/security/` | `src/security/README.md` | |
| `src/utils/` | Product events (structured logs), serialization helpers | infra | ✅ Active | `src/config` | `tests/unit/utils/` | `src/utils/README.md` | `product_events.py` is the required observability path |
| `src/contextualization/` | Contextual embedding providers (OpenAI, Groq, Claude) | ingestion | ✅ Active | `src/config`, `src/services` | `tests/unit/contextualization/` | `docs/CONTEXTUALIZED_EMBEDDINGS.md` | |
| `src/observability/` | Langfuse client wrapper, safe payloads, scores, OTel bootstrap | infra | ✅ Active (optional at runtime) | `src/config` | `tests/unit/observability/`, `tests/unit/test_observability*.py` | `docs/PIPELINE_OVERVIEW.md` | Langfuse is optional; core runs without it |
| `telegram_bot/` | Telegram adapter — the only production channel | adapter | ✅ Active | `src/*` freely | `tests/unit/` (broad), `tests/integration/`, `tests/smoke/` | `telegram_bot/README.md`, `docs/BOT_ARCHITECTURE.md` | `src/` must never import back |
| `telegram_bot/agents/` | CRM tools, domain search tools, HITL interrupt, agent factory | adapter | ✅ Active | `src/*`, `telegram_bot/services/`, `telegram_bot/graph/` | `tests/unit/agents/` | `telegram_bot/agents/README.md` | HITL wraps all sensitive CRM writes |
| `telegram_bot/services/` | Catalog search, Kommo client, lead scoring, handoff, hot-lead, filtering | adapter | ✅ Active | `src/*`, `telegram_bot/models/` | `tests/unit/services/`, `tests/unit/test_*.py` | `telegram_bot/services/README.md` | Domain-specific; replace for a different vertical |
| `telegram_bot/graph/` | Compat facades over `src/runtime/graph` (thin re-exports) | adapter | ✅ Active (transitional) | `src/runtime/graph/`, `src/*` | `tests/unit/graph/` | `telegram_bot/graph/README.md` | Shims listed in Compatibility Shims section; must shrink |
| `telegram_bot/dialogs/` | aiogram-dialogs flows: catalog, CRM, funnel, handoff, settings | adapter | ✅ Active | `telegram_bot/*`, `src/*` | `tests/unit/dialogs/` | `telegram_bot/dialogs/README.md` | |
| `telegram_bot/handlers/` | aiogram message/command handlers, phone collector | adapter | ✅ Active | `telegram_bot/*`, `src/*` | `tests/unit/handlers/` | `telegram_bot/handlers/README.md` | |
| `telegram_bot/integrations/` | Bot cache, memory (LangGraph checkpointer), prompt manager | adapter | ✅ Active | `telegram_bot/*`, `src/*` | `tests/unit/integrations/` | `telegram_bot/integrations/README.md` | |
| `telegram_bot/middlewares/` | i18n, throttling, error handling, Langfuse middleware | adapter | ✅ Active | `telegram_bot/*`, `src/*` | `tests/unit/test_middlewares*.py`, `tests/unit/middlewares/` | `telegram_bot/middlewares/README.md` | |
| `telegram_bot/keyboards/` | Inline keyboard builders | adapter | ✅ Active | `telegram_bot/*` | `tests/unit/keyboards/` | `telegram_bot/keyboards/README.md` | |
| `telegram_bot/pipelines/` | Bot-side pipeline client | adapter | ✅ Active | `telegram_bot/*`, `src/*` | `tests/unit/pipelines/` | `telegram_bot/pipelines/README.md` | |
| `telegram_bot/locales/` | Fluent i18n bundles (en, ru, uk) | adapter | ✅ Active | none | `tests/unit/test_handoff_i18n.py` | `telegram_bot/locales/README.md` | Some strings still being migrated to Fluent |
| `telegram_bot/models/` | Bot-specific Pydantic models | adapter | ✅ Active | none | — | `telegram_bot/models/README.md` | |
| `telegram_bot/constants/` | Bot constants | adapter | ✅ Active | none | `tests/unit/test_telegram_constants.py` | `telegram_bot/constants/README.md` | |
| `telegram_bot/config/` | Bot YAML configs (services, mini_app) | adapter | ✅ Active | none | `tests/unit/test_bot_config.py` | `telegram_bot/config/README.md` | |
| `services/bge-m3-api/` | BGE-M3 dense + sparse + ColBERT embedding sidecar (Docker only) | infra | ✅ Active | HTTP only — not a Python dep | `tests/unit/test_bge_m3_endpoints.py` | `services/bge-m3-api/README.md`, `docs/QDRANT_STACK.md` | |
| `services/docling/` | Document parsing and chunking sidecar (Docker only) | infra | ✅ Active | HTTP only — not a Python dep | `tests/unit/test_dockerfile_docling_sync.py` | `services/docling/README.md` | |
| `tests/unit/` | Fast unit tests (mocked/no external deps) | tests | ✅ Active | test-only | `make test-core`, `make test-unit` | `tests/README.md` | |
| `tests/contract/` | Static/structural contract tests | tests | ✅ Active | test-only | `make test-contract` | `tests/README.md` | Enforces layering, import rules, and swarm contracts |
| `tests/integration/` | Service-integration tests (real Qdrant/Redis) | tests | ✅ Active | test-only | manual / `make test-full` | `tests/README.md` | Requires live services |
| `tests/e2e_core/` | Core E2E without Telegram (Qdrant + BGE-M3) | tests | ✅ Active | test-only | `make e2e-core-live` | `tests/e2e_core/README.md` | Main product simplification proof |
| `tests/e2e/` | Full-stack pipeline and Telegram E2E | tests | ✅ Active | test-only | manual | `tests/README.md` | Requires live Telegram session |
| `tests/smoke/` | Runtime smoke tests against live services | tests | ✅ Active | test-only | manual | `tests/README.md` | |
| `tests/eval/` | RAG evaluation (RAGAS, ground truth) | tests | optional | test-only | manual | `tests/README.md` | Requires Langfuse |
| `tests/baseline/` | Langfuse baseline metrics and threshold checks | tests | optional | test-only | manual | `tests/README.md` | Requires Langfuse |
| `tests/benchmark/` | Performance comparisons (RRF vs DBSF, ColBERT, etc.) | tests | optional | test-only | manual | `tests/README.md` | |
| `tests/chaos/` | Resilience tests (service failures, LLM fallbacks) | tests | optional | test-only | manual | `tests/README.md` | |
| `tests/load/` | Concurrent throughput and cache eviction tests | tests | optional | test-only | manual | `tests/README.md` | |
| `tests/regression/` | RAG core regression tests | tests | optional | test-only | manual | `tests/README.md` | |
| `tests/fixtures/` | Shared test data, CI env stubs | tests | ✅ Active | test-only | — | — | |
| `tests/data/` | Allowlists and known-state JSON (layering violations, duplicate names) | tests | ✅ Active | test-only | — | — | |
| `scripts/` | Operational scripts: indexing, setup, validation, benchmarks, Qdrant ops | infra | ✅ Active | `src/*`, standalone | `tests/unit/scripts/` | `scripts/README.md`, `scripts/AGENTS.override.md` | See #2720 for CI/Makefile/scripts audit |
| `scripts/e2e/` | E2E runner, scenario config, Claude judge, report generation | infra | ✅ Active | `src/*` | — | `scripts/e2e/README.md` | |
| `scripts/archive/` | Superseded scripts (eval, quantization A/B, Kommo seed) | infra | 🗃 Archived | none | — | `scripts/archive/README.md` | Do not use; kept for reference |
| `docs/` | All project documentation | docs | ✅ Active | — | — | `docs/README.md` | |
| `docs/architecture/` | THIS document and architecture artifacts | docs | ✅ Active | — | — | `docs/README.md` | Canonical structure map lives here |
| `docs/designs/` | Active product simplification design docs and Stage 0 decisions | docs | ✅ Active | — | — | `docs/designs/README.md` | Source of truth for simplification work |
| `docs/adr/` | Architecture decision records | docs | ✅ Active | — | — | `docs/adr/README.md` | |
| `docs/engineering/` | Engineering process: test-writing, SDK registry, issue triage, playbooks | docs | ✅ Active | — | — | `docs/engineering/README.md` | |
| `docs/runbooks/` | Operational runbooks: bot failure, Redis cache, Qdrant, PostgreSQL WAL | docs | ✅ Active | — | — | `docs/runbooks/README.md` | |
| `docs/indexes/` | Task-oriented lookup indexes | docs | ✅ Active | — | — | `docs/indexes/README.md` | |
| `docs/review/` | Reviewer and portfolio entry points | docs | ✅ Active | — | — | `docs/review/README.md` | |
| `docs/audits/` | Point-in-time audit artifacts (config drift, endpoint inventory, etc.) | docs | ✅ Active | — | — | — | See #2719 for docs truthfulness audit |
| `docs/audit/` | Public exports audit | docs | ✅ Active | — | — | — | |
| `docs/archive/` | Archived docs (voice, API, Mini App, observability) | docs | 🗃 Archived | — | — | `docs/archive/README.md` | |
| `docs/observability/` | Trace coverage audit and cross-service tracing contract | docs | ✅ Active | — | — | — | |
| `docs/security/` | Secret scanning runbooks, filter patterns | docs | ✅ Active | — | — | — | |
| `docs/plans/` | Shared implementation plans | docs | ✅ Active | — | — | — | |
| `docs/portfolio/` | Portfolio and resume case study | docs | ✅ Active | — | — | `docs/portfolio/README.md` | |
| `docker/` | Compose helper configs (Qdrant, Postgres, monitoring, ingestion, LiveKit) | infra | ✅ Active | — | — | `docker/README.md` | |
| `archive/api/` | FastAPI RAG API | adapter | 🗃 Archived | none (must not be imported) | — | `archive/api/README.md` | Use `src/core` directly |
| `archive/voice/` | LiveKit voice agent | adapter | 🗃 Archived | none | — | `archive/voice/README.md` | |
| `archive/mini_app/` | Telegram Mini App backend + frontend | adapter | 🗃 Archived | none | — | `archive/mini_app/README.md` | |
| `archive/k8s/` | k3s manifests for core services | infra | 🗃 Archived | none | — | `archive/k8s/README.md` | Partial parity with Compose; not required |
| `archive/user-base/` | Telegram user registration sidecar | infra | 🗃 Archived | none | — | `archive/user-base/README.md` | |
| `archive/telegram_bot/` | Old bot code superseded by current `telegram_bot/` | adapter | 🗃 Archived | none | — | — | |
| `archive/evaluation/` | Old evaluation scripts superseded by `tests/eval/` and `tests/baseline/` | tests | 🗃 Archived | none | — | `archive/evaluation/README.md` | |
| `archive/schedulers/` | Lead score sync, nurturing scheduler, session summary worker | infra | 🗃 Archived | none | — | — | |
| `archive/obs/` | Old Loki/Alertmanager/Promtail configs | infra | 🗃 Archived | none | — | `archive/obs/README.md` | Moved to `docker/monitoring/` |
| `archive/observability/` | Sentry and Prometheus metrics server stubs | infra | 🗃 Archived | none | — | — | |
| `archive/services/` | Voyage embeddings service stubs | infra | 🗃 Archived | none | — | — | |
| `archive/scripts/` | Old eval and audit scripts | infra | 🗃 Archived | none | — | `archive/scripts/README.md` | |
| `archive/tests/` | Tests for archived code | tests | 🗃 Archived | none | — | — | |
| `.github/` | CI workflows, issue templates, CODEOWNERS, Dependabot | infra | ✅ Active | — | `tests/unit/test_ci_deploy_workflow.py` | `AGENTS.md` | See #2720 for CI audit |
| `.kiro/` | Agent skills, steering, and orchestration config | infra | ✅ Active | — | `tests/contract/test_kiro_swarm_skills_contract.py` | `AGENTS.md` | |
| `data/` | Local test data, demo corpus, Docling output | infra | ✅ Active | — | — | `data/README.md` | Not committed to production |
| `compose.yml` | Primary Docker Compose runtime | infra | ✅ Active | — | `tests/unit/test_compose*.py` | `DOCKER.md` | |
| `compose.core.yml` | Minimal core stack (Qdrant + Redis only) | infra | ✅ Active | — | — | `DOCKER.md` | |
| `compose.dev.yml` | Dev overrides | infra | ✅ Active | — | — | `DOCKER.md` | |
| `pyproject.toml` | Python project, deps, tools (Ruff, MyPy, pytest) | infra | ✅ Active | — | — | `docs/LOCAL-DEVELOPMENT.md` | |
| `Makefile` | All local commands | infra | ✅ Active | — | `tests/unit/test_makefile_contract.py` | `docs/LOCAL-DEVELOPMENT.md` | See #2720 for Makefile audit |
| `.env.example` | Environment variable template | infra | ✅ Active | — | `tests/contract/test_env_example_completeness_contract.py` | `docs/LOCAL-DEVELOPMENT.md` | |

**Status legend:**
- ✅ Active — part of the required runtime or test suite
- 🟡 Optional — useful but not required for the core proof (`make e2e-core-live`)
- 🗃 Archived — dead code; must not be imported by live `src/` or `telegram_bot/` modules

**Related audits:**
- Layer-boundary violations: #2712
- Docs truthfulness and product-surface map: #2719
- CI, Makefile, scripts, and automation: #2720
- Archived-but-in-src surfaces: #2694

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
│   └── docling/                # Document parsing / chunking sidecar
│   # user-base is archived under archive/user-base/
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
| `archive/user-base/` | Telegram user registration sidecar (archived) |

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
| `services/user-base/` | 🗃 Archived — user registration sidecar (`archive/user-base/`) |
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
