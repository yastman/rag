# Codebase Structure

**Analysis Date:** 2026-02-19

## Directory Layout

```
/home/user/projects/rag-fresh/
├── telegram_bot/                    # Telegram bot (LangGraph RAG + agent tools)
│   ├── bot.py                       # PropertyBot orchestrator (~600 LOC)
│   ├── config.py                    # BotConfig (Pydantic BaseSettings)
│   ├── observability.py             # Langfuse @observe, PII masking
│   ├── scoring.py                   # write_langfuse_scores() + latency breakdown
│   ├── main.py                      # Entry point with retry logic
│   ├── graph/                       # LangGraph pipeline
│   │   ├── graph.py                 # build_graph() assembler (11 nodes)
│   │   ├── state.py                 # RAGState TypedDict (25+ fields)
│   │   ├── edges.py                 # Routing functions (route_start, route_grade, etc.)
│   │   ├── config.py                # GraphConfig dataclass
│   │   ├── supervisor_state.py      # Agent conversation state
│   │   └── nodes/                   # 11 node implementations
│   │       ├── guard.py             # Toxicity + injection filtering
│   │       ├── transcribe.py        # Whisper STT via LiteLLM
│   │       ├── classify.py          # Query type detection (regex)
│   │       ├── cache.py             # cache_check + cache_store nodes
│   │       ├── retrieve.py          # Parallel BGE-M3 dense+sparse on Qdrant
│   │       ├── grade.py             # RRF score evaluation
│   │       ├── rerank.py            # ColBERT reranking (optional)
│   │       ├── generate.py          # LLM response streaming
│   │       ├── rewrite.py           # Query rewrite on low confidence
│   │       └── respond.py           # Send response to Telegram
│   ├── agents/                      # Agent factory + tools
│   │   ├── agent.py                 # create_bot_agent() SDK wrapper
│   │   ├── context.py               # BotContext DI dataclass (13 fields)
│   │   ├── rag_tool.py              # @tool rag_search (wraps build_graph)
│   │   ├── history_tool.py          # @tool history_search (4-node sub-graph)
│   │   ├── crm_tools.py             # 8 @tools for Kommo API
│   │   ├── supervisor.py            # Deprecated: use agent.py instead
│   │   └── history_graph/           # History search sub-pipeline
│   │       ├── graph.py             # 4-node history graph
│   │       ├── state.py             # HistoryState TypedDict
│   │       └── nodes.py             # History nodes (retrieve, grade, rewrite, summarize)
│   ├── services/                    # Domain services
│   │   ├── bge_m3_client.py         # BGE-M3 embeddings (dense+sparse hybrid)
│   │   ├── qdrant.py                # Qdrant gRPC client + batch ops
│   │   ├── llm.py                   # LiteLLM (Cerebras/OpenAI)
│   │   ├── colbert_reranker.py      # ColBERT reranking
│   │   ├── voyage.py                # Voyage AI embeddings (dev)
│   │   ├── llm_guard_client.py      # Content filtering (toxicity + injection)
│   │   ├── query_preprocessor.py    # Query normalization
│   │   ├── query_analyzer.py        # Query feature extraction
│   │   ├── normalizer.py            # Text normalization
│   │   ├── kommo_client.py          # Kommo CRM async httpx client (OAuth2 auto-refresh)
│   │   ├── kommo_token_store.py     # Redis-backed OAuth2 token store
│   │   ├── kommo_models.py          # Pydantic v2 CRM data models
│   │   ├── lead_scoring.py          # Lead score computation
│   │   ├── lead_scoring_store.py    # Lead score persistence (asyncpg)
│   │   ├── lead_scoring_models.py   # Lead score models (sync_status tracking)
│   │   ├── hot_lead_notifier.py     # Auto-notify on high scores
│   │   ├── nurturing_service.py     # Nurturing campaign logic
│   │   ├── nurturing_scheduler.py   # APScheduler v3 integration
│   │   ├── funnel_analytics_store.py# Funnel metrics persistence
│   │   ├── funnel_analytics_service.py # Funnel aggregation
│   │   ├── history_service.py       # Conversation history retrieval
│   │   ├── user_service.py          # User data (phones, preferences)
│   │   ├── metrics.py               # Pipeline latency metrics
│   │   ├── session_summary.py       # Session summarization
│   │   ├── response_style_detector.py # Response length control
│   │   ├── manager_menu.py          # Admin menu UI
│   │   └── redis_monitor.py         # Redis health checks
│   ├── integrations/                # External integrations
│   │   ├── cache.py                 # CacheLayerManager (6-tier Redis)
│   │   ├── embeddings.py            # BGEM3Embeddings, BGEM3SparseEmbeddings
│   │   ├── langfuse.py              # Langfuse client init + instrumentation
│   │   ├── prompt_manager.py        # System prompt templates
│   │   ├── prompt_templates.py      # Prompt definitions
│   │   ├── memory.py                # Conversation memory abstractions
│   │   └── event_stream.py          # Event streaming (unused)
│   ├── middlewares/                 # Aiogram middlewares
│   │   ├── throttling.py            # Rate limiting per user
│   │   └── error_handler.py         # Global exception handler
│   ├── models/                      # Data models
│   │   └── user.py                  # User model (Pydantic)
│   ├── dialogs/                     # Aiogram-dialog (menu UI)
│   │   └── *.py                     # Admin dialogs, callbacks
│   ├── locales/                     # i18n translations (.ftl files)
│   ├── evaluation/                  # Bot-specific evaluation
│   │   ├── evaluator.py             # LLM-as-a-Judge
│   │   └── *.py                     # Evaluation utilities
│   ├── pyproject.toml               # Service-specific deps
│   ├── uv.lock                      # Service-specific lockfile
│   └── Dockerfile                   # Bot container image
│
├── src/                             # Shared library code
│   ├── config/                      # Configuration
│   │   ├── settings.py              # Settings class (legacy, superseded by telegram_bot/config.py)
│   │   └── constants.py             # Enum constants, default values
│   ├── api/                         # FastAPI RAG API
│   │   ├── main.py                  # FastAPI app with lifespan setup
│   │   └── schemas.py               # QueryRequest, QueryResponse
│   ├── voice/                       # Voice bot (LiveKit + ElevenLabs + SIP)
│   │   ├── agent.py                 # LiveKit VoiceBot Agent + @function_tool
│   │   ├── schemas.py               # CallStatus, CallRequest, CallResponse
│   │   ├── transcript_store.py      # PostgreSQL async store (asyncpg)
│   │   └── sip_setup.py             # One-time SIP trunk provisioning
│   ├── retrieval/                   # Retrieval backends
│   │   ├── search_engines.py        # 4 variants (RRF, dense, sparse, hybrid)
│   │   └── reranker.py              # Reranking abstractions
│   ├── ingestion/                   # Document ingestion
│   │   ├── unified/                 # Unified pipeline (CocoIndex v3.2.1)
│   │   │   ├── flow.py              # CocoIndex flow definition
│   │   │   ├── cli.py               # CLI: preflight, bootstrap, run, status, reprocess
│   │   │   ├── config.py            # UnifiedConfig (Pydantic BaseSettings)
│   │   │   ├── state_manager.py     # Postgres state tracking (asyncpg)
│   │   │   ├── qdrant_writer.py     # Qdrant upsert/delete writer (sync methods)
│   │   │   ├── manifest.py          # File identity via content hash
│   │   │   ├── metrics.py           # Ingestion metrics
│   │   │   └── targets/
│   │   │       └── qdrant_hybrid_target.py # CocoIndex target connector (mutate sync)
│   │   ├── docling_client.py        # Docling parser + chunk_file_sync()
│   │   ├── chunker.py               # Text chunking strategies
│   │   ├── contextual_loader.py     # Load docs with context
│   │   ├── contextual_schema.py     # Contextual embedding schema
│   │   └── document_parser.py       # Legacy parser (deprecated)
│   ├── evaluation/                  # RAG evaluation suite
│   │   ├── evaluator.py             # LLM-as-a-Judge (RAGAS faithfulness)
│   │   ├── metrics_logger.py        # Metric aggregation
│   │   ├── config_snapshot.py       # Config capture for experiments
│   │   ├── search_engines.py        # Evaluation search variants
│   │   ├── extract_ground_truth.py  # Gold set extraction
│   │   ├── mlflow_integration.py    # MLflow experiment tracking
│   │   ├── run_ab_test.py           # A/B test runner
│   │   └── smoke_test.py            # Smoke test harness
│   ├── cache/                       # Cache implementations
│   │   ├── redis_semantic_cache.py  # Semantic caching via embeddings
│   │   └── example_usage.py         # Cache usage examples
│   ├── contextualization/           # Document contextualization
│   │   ├── base.py                  # Abstract Contextualizer
│   │   ├── openai.py                # OpenAI-based contextualization
│   │   ├── claude.py                # Anthropic Claude contextualization
│   │   └── groq.py                  # Groq-based contextualization
│   ├── models/                      # Data/ML models
│   │   ├── embedding_model.py       # Embedding abstractions
│   │   └── contextualized_embedding.py # Contextualized embeddings
│   ├── governance/                  # Model registry
│   │   └── model_registry.py        # Model versioning
│   ├── observability/               # Shared observability
│   │   └── otel_setup.py            # OpenTelemetry setup (legacy)
│   ├── security/                    # Security utilities
│   │   └── pii_redaction.py         # PII detection + masking
│   ├── utils/                       # Utility functions
│   │   └── structure_parser.py      # Parse document structure
│   └── core/                        # Core abstractions
│       └── *.py                     # Base classes, protocols
│
├── tests/                           # Test suite (pytest)
│   ├── unit/                        # Fast unit tests (~5 min parallel)
│   │   ├── conftest.py              # Shared fixtures
│   │   ├── test_*.py                # Unit test modules
│   │   ├── graph/                   # RAG pipeline node tests
│   │   ├── services/                # Service client tests
│   │   ├── agents/                  # Agent + tool tests
│   │   ├── ingestion/               # Ingestion pipeline tests
│   │   ├── integrations/            # Integration service tests
│   │   └── contextualization/       # Contextualization tests
│   ├── integration/                 # Integration tests (~5s, no Docker)
│   │   ├── test_graph_paths.py      # End-to-end graph routing
│   │   ├── test_voice_pipeline.py   # Voice bot integration
│   │   └── test_*.py
│   ├── e2e/                         # End-to-end tests (with Docker)
│   │   └── test_*.py
│   ├── chaos/                       # Chaos/failure tests
│   │   └── test_*.py
│   ├── load/                        # Load/stress tests
│   │   └── test_*.py
│   ├── baseline/                    # Regression baseline tests (Langfuse)
│   │   └── test_*.py
│   ├── eval/                        # Evaluation test datasets
│   │   └── *.json
│   ├── data/                        # Test fixtures
│   │   ├── demo/                    # Demo docs
│   │   └── test/                    # Test corpus
│   └── benchmark/                   # Benchmark tests
│       └── test_*.py
│
├── scripts/                         # Utility scripts
│   ├── eval/                        # Evaluation scripts
│   │   ├── export_traces_to_dataset.py # Export Langfuse traces
│   │   ├── validate_*.py            # Trace validators
│   │   └── *.py
│   ├── e2e/                         # E2E test scripts
│   └── *.py
│
├── docker/                          # Docker configuration
│   ├── monitoring/                  # Observability stack (Prometheus, Grafana, AlertManager)
│   │   ├── docker-compose.yml
│   │   └── rules/                   # Alert rules
│   ├── litellm/                     # LiteLLM proxy config
│   ├── postgres/                    # PostgreSQL init scripts
│   │   └── init/                    # Database schemas
│   ├── livekit/                     # LiveKit SIP config
│   ├── rclone/                      # Google Drive sync config
│   └── mlflow/                      # MLflow tracking config
│
├── docker-compose.dev.yml           # Dev services (5 core: qdrant, redis, postgres, bge-m3, litellm)
├── docker-compose.vps.yml           # VPS services (production config)
├── Dockerfile.ingestion             # Ingestion pipeline image
│
├── k8s/                             # Kubernetes manifests (VPS k3s)
│   ├── base/                        # kustomize base
│   └── overlays/                    # Environment overlays
│
├── docs/                            # Project documentation
│   ├── PIPELINE_OVERVIEW.md         # Architecture diagram
│   ├── QDRANT_STACK.md              # Vector DB details
│   ├── INGESTION.md                 # Ingestion pipeline
│   ├── ALERTING.md                  # Monitoring alerts
│   └── plans/                       # Design + implementation plans
│
├── .claude/                         # Claude Code guidance
│   ├── rules/                       # Domain-specific docs
│   │   ├── features/                # Feature modules (telegram-bot.md, voice-bot.md, etc.)
│   │   ├── build.md                 # Build tooling (uv, pre-commit, CI)
│   │   ├── docker.md                # Docker profiles + services
│   │   ├── k3s.md                   # k3s deployment
│   │   ├── git-workflow.md          # PR discipline, Renovate
│   │   └── observability.md         # Langfuse v3 + scoring
│   ├── prompts/                     # Claude prompts
│   └── skills/                      # Multi-agent coordination
│
├── .github/                         # GitHub Actions CI/CD
│   └── workflows/
│       ├── ci.yml                   # lint, test, baseline-compare
│       └── deploy.yml               # Container push, k3s deploy
│
├── .planning/                       # GSD analysis documents
│   └── codebase/                    # Codebase insights
│       ├── STACK.md                 # Technology stack
│       ├── ARCHITECTURE.md          # Architecture patterns
│       ├── STRUCTURE.md             # Directory layout (this file)
│       ├── CONVENTIONS.md           # Code style
│       ├── TESTING.md               # Test patterns
│       └── CONCERNS.md              # Technical debt
│
├── pyproject.toml                   # Root Python project (main bot + ingestion)
├── uv.lock                          # Root lockfile
├── Makefile                         # Development commands (40+ targets)
├── CLAUDE.md                        # Project instructions
├── CLAUDE.local.md                  # Local user preferences
├── DOCKER.md                        # Docker quick reference
├── README.md                        # Project overview
└── TODO.md                          # Current backlog
```

## Directory Purposes

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

## Key File Locations

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

## Naming Conventions

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

## Where to Add New Code

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

## Special Directories

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
