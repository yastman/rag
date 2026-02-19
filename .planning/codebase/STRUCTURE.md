***REMOVED*** Codebase Structure

**Analysis Date:** 2026-02-19

***REMOVED******REMOVED*** Directory Layout

```
/repo/
├── telegram_bot/                    ***REMOVED*** Telegram bot (LangGraph RAG + agent tools)
│   ├── bot.py                       ***REMOVED*** PropertyBot orchestrator (~600 LOC)
│   ├── config.py                    ***REMOVED*** BotConfig (Pydantic BaseSettings)
│   ├── observability.py             ***REMOVED*** Langfuse @observe, PII masking
│   ├── scoring.py                   ***REMOVED*** write_langfuse_scores() + latency breakdown
│   ├── main.py                      ***REMOVED*** Entry point with retry logic
│   ├── graph/                       ***REMOVED*** LangGraph pipeline
│   │   ├── graph.py                 ***REMOVED*** build_graph() assembler (11 nodes)
│   │   ├── state.py                 ***REMOVED*** RAGState TypedDict (25+ fields)
│   │   ├── edges.py                 ***REMOVED*** Routing functions (route_start, route_grade, etc.)
│   │   ├── config.py                ***REMOVED*** GraphConfig dataclass
│   │   ├── supervisor_state.py      ***REMOVED*** Agent conversation state
│   │   └── nodes/                   ***REMOVED*** 11 node implementations
│   │       ├── guard.py             ***REMOVED*** Toxicity + injection filtering
│   │       ├── transcribe.py        ***REMOVED*** Whisper STT via LiteLLM
│   │       ├── classify.py          ***REMOVED*** Query type detection (regex)
│   │       ├── cache.py             ***REMOVED*** cache_check + cache_store nodes
│   │       ├── retrieve.py          ***REMOVED*** Parallel BGE-M3 dense+sparse on Qdrant
│   │       ├── grade.py             ***REMOVED*** RRF score evaluation
│   │       ├── rerank.py            ***REMOVED*** ColBERT reranking (optional)
│   │       ├── generate.py          ***REMOVED*** LLM response streaming
│   │       ├── rewrite.py           ***REMOVED*** Query rewrite on low confidence
│   │       └── respond.py           ***REMOVED*** Send response to Telegram
│   ├── agents/                      ***REMOVED*** Agent factory + tools
│   │   ├── agent.py                 ***REMOVED*** create_bot_agent() SDK wrapper
│   │   ├── context.py               ***REMOVED*** BotContext DI dataclass (13 fields)
│   │   ├── rag_tool.py              ***REMOVED*** @tool rag_search (wraps build_graph)
│   │   ├── history_tool.py          ***REMOVED*** @tool history_search (4-node sub-graph)
│   │   ├── crm_tools.py             ***REMOVED*** 8 @tools for Kommo API
│   │   ├── supervisor.py            ***REMOVED*** Deprecated: use agent.py instead
│   │   └── history_graph/           ***REMOVED*** History search sub-pipeline
│   │       ├── graph.py             ***REMOVED*** 4-node history graph
│   │       ├── state.py             ***REMOVED*** HistoryState TypedDict
│   │       └── nodes.py             ***REMOVED*** History nodes (retrieve, grade, rewrite, summarize)
│   ├── services/                    ***REMOVED*** Domain services
│   │   ├── bge_m3_client.py         ***REMOVED*** BGE-M3 embeddings (dense+sparse hybrid)
│   │   ├── qdrant.py                ***REMOVED*** Qdrant gRPC client + batch ops
│   │   ├── llm.py                   ***REMOVED*** LiteLLM (Cerebras/OpenAI)
│   │   ├── colbert_reranker.py      ***REMOVED*** ColBERT reranking
│   │   ├── voyage.py                ***REMOVED*** Voyage AI embeddings (dev)
│   │   ├── llm_guard_client.py      ***REMOVED*** Content filtering (toxicity + injection)
│   │   ├── query_preprocessor.py    ***REMOVED*** Query normalization
│   │   ├── query_analyzer.py        ***REMOVED*** Query feature extraction
│   │   ├── normalizer.py            ***REMOVED*** Text normalization
│   │   ├── kommo_client.py          ***REMOVED*** Kommo CRM async httpx client (OAuth2 auto-refresh)
│   │   ├── kommo_token_store.py     ***REMOVED*** Redis-backed OAuth2 token store
│   │   ├── kommo_models.py          ***REMOVED*** Pydantic v2 CRM data models
│   │   ├── lead_scoring.py          ***REMOVED*** Lead score computation
│   │   ├── lead_scoring_store.py    ***REMOVED*** Lead score persistence (asyncpg)
│   │   ├── lead_scoring_models.py   ***REMOVED*** Lead score models (sync_status tracking)
│   │   ├── hot_lead_notifier.py     ***REMOVED*** Auto-notify on high scores
│   │   ├── nurturing_service.py     ***REMOVED*** Nurturing campaign logic
│   │   ├── nurturing_scheduler.py   ***REMOVED*** APScheduler v3 integration
│   │   ├── funnel_analytics_store.py***REMOVED*** Funnel metrics persistence
│   │   ├── funnel_analytics_service.py ***REMOVED*** Funnel aggregation
│   │   ├── history_service.py       ***REMOVED*** Conversation history retrieval
│   │   ├── user_service.py          ***REMOVED*** User data (phones, preferences)
│   │   ├── metrics.py               ***REMOVED*** Pipeline latency metrics
│   │   ├── session_summary.py       ***REMOVED*** Session summarization
│   │   ├── response_style_detector.py ***REMOVED*** Response length control
│   │   ├── manager_menu.py          ***REMOVED*** Admin menu UI
│   │   └── redis_monitor.py         ***REMOVED*** Redis health checks
│   ├── integrations/                ***REMOVED*** External integrations
│   │   ├── cache.py                 ***REMOVED*** CacheLayerManager (6-tier Redis)
│   │   ├── embeddings.py            ***REMOVED*** BGEM3Embeddings, BGEM3SparseEmbeddings
│   │   ├── langfuse.py              ***REMOVED*** Langfuse client init + instrumentation
│   │   ├── prompt_manager.py        ***REMOVED*** System prompt templates
│   │   ├── prompt_templates.py      ***REMOVED*** Prompt definitions
│   │   ├── memory.py                ***REMOVED*** Conversation memory abstractions
│   │   └── event_stream.py          ***REMOVED*** Event streaming (unused)
│   ├── middlewares/                 ***REMOVED*** Aiogram middlewares
│   │   ├── throttling.py            ***REMOVED*** Rate limiting per user
│   │   └── error_handler.py         ***REMOVED*** Global exception handler
│   ├── models/                      ***REMOVED*** Data models
│   │   └── user.py                  ***REMOVED*** User model (Pydantic)
│   ├── dialogs/                     ***REMOVED*** Aiogram-dialog (menu UI)
│   │   └── *.py                     ***REMOVED*** Admin dialogs, callbacks
│   ├── locales/                     ***REMOVED*** i18n translations (.ftl files)
│   ├── evaluation/                  ***REMOVED*** Bot-specific evaluation
│   │   ├── evaluator.py             ***REMOVED*** LLM-as-a-Judge
│   │   └── *.py                     ***REMOVED*** Evaluation utilities
│   ├── pyproject.toml               ***REMOVED*** Service-specific deps
│   ├── uv.lock                      ***REMOVED*** Service-specific lockfile
│   └── Dockerfile                   ***REMOVED*** Bot container image
│
├── src/                             ***REMOVED*** Shared library code
│   ├── config/                      ***REMOVED*** Configuration
│   │   ├── settings.py              ***REMOVED*** Settings class (legacy, superseded by telegram_bot/config.py)
│   │   └── constants.py             ***REMOVED*** Enum constants, default values
│   ├── api/                         ***REMOVED*** FastAPI RAG API
│   │   ├── main.py                  ***REMOVED*** FastAPI app with lifespan setup
│   │   └── schemas.py               ***REMOVED*** QueryRequest, QueryResponse
│   ├── voice/                       ***REMOVED*** Voice bot (LiveKit + ElevenLabs + SIP)
│   │   ├── agent.py                 ***REMOVED*** LiveKit VoiceBot Agent + @function_tool
│   │   ├── schemas.py               ***REMOVED*** CallStatus, CallRequest, CallResponse
│   │   ├── transcript_store.py      ***REMOVED*** PostgreSQL async store (asyncpg)
│   │   └── sip_setup.py             ***REMOVED*** One-time SIP trunk provisioning
│   ├── retrieval/                   ***REMOVED*** Retrieval backends
│   │   ├── search_engines.py        ***REMOVED*** 4 variants (RRF, dense, sparse, hybrid)
│   │   └── reranker.py              ***REMOVED*** Reranking abstractions
│   ├── ingestion/                   ***REMOVED*** Document ingestion
│   │   ├── unified/                 ***REMOVED*** Unified pipeline (CocoIndex v3.2.1)
│   │   │   ├── flow.py              ***REMOVED*** CocoIndex flow definition
│   │   │   ├── cli.py               ***REMOVED*** CLI: preflight, bootstrap, run, status, reprocess
│   │   │   ├── config.py            ***REMOVED*** UnifiedConfig (Pydantic BaseSettings)
│   │   │   ├── state_manager.py     ***REMOVED*** Postgres state tracking (asyncpg)
│   │   │   ├── qdrant_writer.py     ***REMOVED*** Qdrant upsert/delete writer (sync methods)
│   │   │   ├── manifest.py          ***REMOVED*** File identity via content hash
│   │   │   ├── metrics.py           ***REMOVED*** Ingestion metrics
│   │   │   └── targets/
│   │   │       └── qdrant_hybrid_target.py ***REMOVED*** CocoIndex target connector (mutate sync)
│   │   ├── docling_client.py        ***REMOVED*** Docling parser + chunk_file_sync()
│   │   ├── chunker.py               ***REMOVED*** Text chunking strategies
│   │   ├── contextual_loader.py     ***REMOVED*** Load docs with context
│   │   ├── contextual_schema.py     ***REMOVED*** Contextual embedding schema
│   │   └── document_parser.py       ***REMOVED*** Legacy parser (deprecated)
│   ├── evaluation/                  ***REMOVED*** RAG evaluation suite
│   │   ├── evaluator.py             ***REMOVED*** LLM-as-a-Judge (RAGAS faithfulness)
│   │   ├── metrics_logger.py        ***REMOVED*** Metric aggregation
│   │   ├── config_snapshot.py       ***REMOVED*** Config capture for experiments
│   │   ├── search_engines.py        ***REMOVED*** Evaluation search variants
│   │   ├── extract_ground_truth.py  ***REMOVED*** Gold set extraction
│   │   ├── mlflow_integration.py    ***REMOVED*** MLflow experiment tracking
│   │   ├── run_ab_test.py           ***REMOVED*** A/B test runner
│   │   └── smoke_test.py            ***REMOVED*** Smoke test harness
│   ├── cache/                       ***REMOVED*** Cache implementations
│   │   ├── redis_semantic_cache.py  ***REMOVED*** Semantic caching via embeddings
│   │   └── example_usage.py         ***REMOVED*** Cache usage examples
│   ├── contextualization/           ***REMOVED*** Document contextualization
│   │   ├── base.py                  ***REMOVED*** Abstract Contextualizer
│   │   ├── openai.py                ***REMOVED*** OpenAI-based contextualization
│   │   ├── claude.py                ***REMOVED*** Anthropic Claude contextualization
│   │   └── groq.py                  ***REMOVED*** Groq-based contextualization
│   ├── models/                      ***REMOVED*** Data/ML models
│   │   ├── embedding_model.py       ***REMOVED*** Embedding abstractions
│   │   └── contextualized_embedding.py ***REMOVED*** Contextualized embeddings
│   ├── governance/                  ***REMOVED*** Model registry
│   │   └── model_registry.py        ***REMOVED*** Model versioning
│   ├── observability/               ***REMOVED*** Shared observability
│   │   └── otel_setup.py            ***REMOVED*** OpenTelemetry setup (legacy)
│   ├── security/                    ***REMOVED*** Security utilities
│   │   └── pii_redaction.py         ***REMOVED*** PII detection + masking
│   ├── utils/                       ***REMOVED*** Utility functions
│   │   └── structure_parser.py      ***REMOVED*** Parse document structure
│   └── core/                        ***REMOVED*** Core abstractions
│       └── *.py                     ***REMOVED*** Base classes, protocols
│
├── tests/                           ***REMOVED*** Test suite (pytest)
│   ├── unit/                        ***REMOVED*** Fast unit tests (~5 min parallel)
│   │   ├── conftest.py              ***REMOVED*** Shared fixtures
│   │   ├── test_*.py                ***REMOVED*** Unit test modules
│   │   ├── graph/                   ***REMOVED*** RAG pipeline node tests
│   │   ├── services/                ***REMOVED*** Service client tests
│   │   ├── agents/                  ***REMOVED*** Agent + tool tests
│   │   ├── ingestion/               ***REMOVED*** Ingestion pipeline tests
│   │   ├── integrations/            ***REMOVED*** Integration service tests
│   │   └── contextualization/       ***REMOVED*** Contextualization tests
│   ├── integration/                 ***REMOVED*** Integration tests (~5s, no Docker)
│   │   ├── test_graph_paths.py      ***REMOVED*** End-to-end graph routing
│   │   ├── test_voice_pipeline.py   ***REMOVED*** Voice bot integration
│   │   └── test_*.py
│   ├── e2e/                         ***REMOVED*** End-to-end tests (with Docker)
│   │   └── test_*.py
│   ├── chaos/                       ***REMOVED*** Chaos/failure tests
│   │   └── test_*.py
│   ├── load/                        ***REMOVED*** Load/stress tests
│   │   └── test_*.py
│   ├── baseline/                    ***REMOVED*** Regression baseline tests (Langfuse)
│   │   └── test_*.py
│   ├── eval/                        ***REMOVED*** Evaluation test datasets
│   │   └── *.json
│   ├── data/                        ***REMOVED*** Test fixtures
│   │   ├── demo/                    ***REMOVED*** Demo docs
│   │   └── test/                    ***REMOVED*** Test corpus
│   └── benchmark/                   ***REMOVED*** Benchmark tests
│       └── test_*.py
│
├── scripts/                         ***REMOVED*** Utility scripts
│   ├── eval/                        ***REMOVED*** Evaluation scripts
│   │   ├── export_traces_to_dataset.py ***REMOVED*** Export Langfuse traces
│   │   ├── validate_*.py            ***REMOVED*** Trace validators
│   │   └── *.py
│   ├── e2e/                         ***REMOVED*** E2E test scripts
│   └── *.py
│
├── docker/                          ***REMOVED*** Docker configuration
│   ├── monitoring/                  ***REMOVED*** Observability stack (Prometheus, Grafana, AlertManager)
│   │   ├── docker-compose.yml
│   │   └── rules/                   ***REMOVED*** Alert rules
│   ├── litellm/                     ***REMOVED*** LiteLLM proxy config
│   ├── postgres/                    ***REMOVED*** PostgreSQL init scripts
│   │   └── init/                    ***REMOVED*** Database schemas
│   ├── livekit/                     ***REMOVED*** LiveKit SIP config
│   ├── rclone/                      ***REMOVED*** Google Drive sync config
│   └── mlflow/                      ***REMOVED*** MLflow tracking config
│
├── docker-compose.dev.yml           ***REMOVED*** Dev services (5 core: qdrant, redis, postgres, bge-m3, litellm)
├── docker-compose.vps.yml           ***REMOVED*** VPS services (production config)
├── Dockerfile.ingestion             ***REMOVED*** Ingestion pipeline image
│
├── k8s/                             ***REMOVED*** Kubernetes manifests (VPS k3s)
│   ├── base/                        ***REMOVED*** kustomize base
│   └── overlays/                    ***REMOVED*** Environment overlays
│
├── docs/                            ***REMOVED*** Project documentation
│   ├── PIPELINE_OVERVIEW.md         ***REMOVED*** Architecture diagram
│   ├── QDRANT_STACK.md              ***REMOVED*** Vector DB details
│   ├── INGESTION.md                 ***REMOVED*** Ingestion pipeline
│   ├── ALERTING.md                  ***REMOVED*** Monitoring alerts
│   └── plans/                       ***REMOVED*** Design + implementation plans
│
├── .claude/                         ***REMOVED*** Claude Code guidance
│   ├── rules/                       ***REMOVED*** Domain-specific docs
│   │   ├── features/                ***REMOVED*** Feature modules (telegram-bot.md, voice-bot.md, etc.)
│   │   ├── build.md                 ***REMOVED*** Build tooling (uv, pre-commit, CI)
│   │   ├── docker.md                ***REMOVED*** Docker profiles + services
│   │   ├── k3s.md                   ***REMOVED*** k3s deployment
│   │   ├── git-workflow.md          ***REMOVED*** PR discipline, Renovate
│   │   └── observability.md         ***REMOVED*** Langfuse v3 + scoring
│   ├── prompts/                     ***REMOVED*** Claude prompts
│   └── skills/                      ***REMOVED*** Multi-agent coordination
│
├── .github/                         ***REMOVED*** GitHub Actions CI/CD
│   └── workflows/
│       ├── ci.yml                   ***REMOVED*** lint, test, baseline-compare
│       └── deploy.yml               ***REMOVED*** Container push, k3s deploy
│
├── .planning/                       ***REMOVED*** GSD analysis documents
│   └── codebase/                    ***REMOVED*** Codebase insights
│       ├── STACK.md                 ***REMOVED*** Technology stack
│       ├── ARCHITECTURE.md          ***REMOVED*** Architecture patterns
│       ├── STRUCTURE.md             ***REMOVED*** Directory layout (this file)
│       ├── CONVENTIONS.md           ***REMOVED*** Code style
│       ├── TESTING.md               ***REMOVED*** Test patterns
│       └── CONCERNS.md              ***REMOVED*** Technical debt
│
├── pyproject.toml                   ***REMOVED*** Root Python project (main bot + ingestion)
├── uv.lock                          ***REMOVED*** Root lockfile
├── Makefile                         ***REMOVED*** Development commands (40+ targets)
├── CLAUDE.md                        ***REMOVED*** Project instructions
├── CLAUDE.local.md                  ***REMOVED*** Local user preferences
├── DOCKER.md                        ***REMOVED*** Docker quick reference
├── README.md                        ***REMOVED*** Project overview
└── TODO.md                          ***REMOVED*** Current backlog
```

***REMOVED******REMOVED*** Directory Purposes

**telegram_bot/:**
- Purpose: Telegram bot application with LangGraph RAG pipeline and agent-driven tool selection
- Contains: Complete bot logic, graph pipeline, services, integrations, evaluation
- Entry point: `telegram_bot/main.py` → `PropertyBot.__init__()` → `PropertyBot.start()`

**src/:**
- Purpose: Shared library code for multiple interfaces (API, voice, ingestion)
- Contains: Configuration, API schemas, voice agent, ingestion pipeline, retrieval, evaluation, models, security
- Used by: telegram_bot (shared services), src/api, src/voice, scripts

**src/api/:**
- Purpose: Synchronous FastAPI wrapper around `build_graph()` for external RAG queries
- Entry point: `uvicorn src.api.main:app --port 8080`
- Exposes: POST /query (JSON request/response), GET /health

**src/voice/:**
- Purpose: LiveKit SIP voice bot with ElevenLabs STT/TTS
- Entry point: `python -m src.voice.agent`
- Integrates: RAG API client (HTTP), Langfuse tracing via OTEL, PostgreSQL transcripts

**src/ingestion/unified/:**
- Purpose: CocoIndex v3.2.1 unified ingestion pipeline for all document sources
- Entry point: `python -m src.ingestion.unified.cli run`
- Commands: preflight, bootstrap, run, status, reprocess
- Synchronous-only (CocoIndex mutate calls sync methods)

**tests/:**
- Purpose: Comprehensive test suite organized by layer and test type
- Structure: unit (fast), integration (no Docker), e2e (Docker), chaos, load, baseline (Langfuse), eval (datasets), benchmark
- Run: `uv run pytest tests/unit/ -n auto` (parallel, ~5 min)

**docker/:**
- Purpose: Docker Compose configurations and service-specific setup files
- Profiles: core (5 svc), bot, ml, obs, ai, eval, ingest, voice, full (17 svc)
- Services: Qdrant, Redis, PostgreSQL, LiteLLM, BGE-M3, Docling, LiveKit, etc.

**k8s/:**
- Purpose: Kubernetes manifests for VPS k3s deployment
- Structure: kustomize base + overlays for dev/prod environments

**.planning/codebase/:**
- Purpose: GSD analysis documents consumed by `/gsd:plan-phase` and `/gsd:execute-phase`
- Files: STACK.md, ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md

***REMOVED******REMOVED*** Key File Locations

**Entry Points:**
- `telegram_bot/main.py`: Telegram bot startup
- `src/api/main.py`: RAG API FastAPI app
- `src/voice/agent.py`: Voice bot LiveKit agent
- `src/ingestion/unified/cli.py`: Ingestion CLI

**Configuration:**
- `telegram_bot/config.py`: BotConfig (Pydantic BaseSettings) — bot settings, domain, model selection
- `telegram_bot/graph/config.py`: GraphConfig (dataclass) — pipeline tuning (thresholds, models, timeouts)
- `src/config/settings.py`: Settings class (legacy, use BotConfig instead)
- `src/ingestion/unified/config.py`: UnifiedConfig (Pydantic BaseSettings) — ingestion settings

**Core Logic:**
- `telegram_bot/graph/graph.py`: `build_graph()` — assembles 11-node StateGraph
- `telegram_bot/graph/state.py`: RAGState TypedDict definition
- `telegram_bot/graph/edges.py`: Conditional routing logic
- `telegram_bot/graph/nodes/`: 11 node implementations (guard, transcribe, classify, cache, retrieve, grade, rerank, generate, rewrite, respond, cache_store)
- `telegram_bot/agents/agent.py`: `create_bot_agent()` SDK factory
- `telegram_bot/agents/context.py`: BotContext DI container
- `telegram_bot/agents/rag_tool.py`: RAG search tool
- `telegram_bot/agents/crm_tools.py`: 8 Kommo CRM tools

**Services:**
- `telegram_bot/services/bge_m3_client.py`: BGE-M3 dual embeddings (dense + sparse)
- `telegram_bot/services/qdrant.py`: Qdrant gRPC client
- `telegram_bot/services/kommo_client.py`: Kommo API client (OAuth2)
- `telegram_bot/integrations/cache.py`: 6-tier Redis cache manager
- `telegram_bot/services/llm.py`: LiteLLM facade

**Testing:**
- `tests/unit/conftest.py`: Shared pytest fixtures
- `tests/unit/graph/`: Graph node unit tests
- `tests/unit/agents/`: Agent factory + tool tests
- `tests/integration/test_graph_paths.py`: End-to-end pipeline routing tests
- `tests/baseline/`: Langfuse regression baseline tests

**Observability:**
- `telegram_bot/observability.py`: Langfuse @observe decorator, PII masking, CallbackHandler
- `telegram_bot/scoring.py`: `write_langfuse_scores()` metric writer

***REMOVED******REMOVED*** Naming Conventions

**Files:**
- `*_client.py`: External API clients (kommo_client.py, llm_guard_client.py)
- `*_service.py`: Domain service logic (history_service.py, lead_scoring_service.py)
- `*_node.py`: LangGraph node functions (but inside `nodes/` dir: guard.py, retrieve.py)
- `*_store.py`: Data persistence (kommo_token_store.py, transcript_store.py)
- `*_tool.py`: LLM @tool implementations (rag_tool.py, crm_tools.py)
- `conftest.py`: pytest shared fixtures
- `test_*.py`: Test modules
- `main.py`: Entry point

**Directories:**
- `*/services/`: Domain service implementations
- `*/integrations/`: External service integrations
- `*/graph/`: LangGraph pipeline
- `*/nodes/`: Pipeline node implementations
- `*/agents/`: Agent factory and tools
- `*/models/`: Data models (Pydantic)
- `*/dialogs/`: UI dialogs (aiogram-dialog)
- `*/locales/`: Translations (.ftl files)

***REMOVED******REMOVED*** Where to Add New Code

**New RAG Pipeline Node:**
1. Create `telegram_bot/graph/nodes/my_node.py` with `async def my_node(state: dict[str, Any]) -> dict[str, Any]`
2. Add to `build_graph()` in `telegram_bot/graph/graph.py` with `functools.partial()` for dependencies
3. Add edge routing in `telegram_bot/graph/edges.py` if needed
4. Write tests in `tests/unit/graph/test_my_node.py`

**New Agent Tool:**
1. Create `telegram_bot/agents/my_tool.py` with `@tool` decorated async function
2. Tool receives `BotContext` via `get_context()` or passed explicitly
3. Add to tools list in `PropertyBot._handle_query_supervisor()`
4. Write tests in `tests/unit/agents/test_my_tool.py`

**New Service:**
1. Create `telegram_bot/services/my_service.py` with async class
2. Initialize in `PropertyBot.__init__()`, store as `self._my_service`
3. Inject into BotContext or node via `functools.partial()`
4. Write tests in `tests/unit/services/test_my_service.py`

**New API Endpoint:**
1. Add to `src/api/main.py` (FastAPI app)
2. Define request/response schemas in `src/api/schemas.py`
3. Use `build_graph()` or services from lifespan context
4. Write tests in `tests/unit/api/test_my_endpoint.py`

**New Evaluation Metric:**
1. Add to `src/evaluation/evaluator.py` (LLM-as-a-Judge)
2. Register scorer in Langfuse trace
3. Log results in `src/evaluation/metrics_logger.py`
4. Write tests in `tests/unit/evaluation/`

**Shared Utility:**
1. Create in `src/utils/` or `src/core/`
2. Import from `src` package (shared across telegram_bot, api, voice)
3. Write tests in `tests/unit/utils/`

***REMOVED******REMOVED*** Special Directories

**telegram_bot/.venv/:**
- Purpose: Service-level virtual environment (isolated from root)
- Generated: Yes (by `uv sync` in telegram_bot/)
- Committed: No (in .gitignore)

**telegram_bot/locales/:**
- Purpose: i18n translations (Fluent .ftl format)
- Generated: No (manually maintained)
- Committed: Yes

**.planning/codebase/:**
- Purpose: GSD analysis documents
- Generated: Yes (by `/gsd:map-codebase`)
- Committed: Yes

**docker/monitoring/rules/:**
- Purpose: Prometheus alert rules
- Generated: No (manually maintained)
- Committed: Yes

**tests/data/:**
- Purpose: Test fixtures, demo docs, evaluation datasets
- Generated: Partially (some via scripts)
- Committed: Yes (small files)

---

*Structure analysis: 2026-02-19*
