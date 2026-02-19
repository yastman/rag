# Architecture

**Analysis Date:** 2026-02-19

## Pattern Overview

**Overall:** Multi-layer contextual RAG system with LangGraph state machine pipeline, agent-based tool routing, and pluggable embeddings/retrieval backends.

**Key Characteristics:**
- **LangGraph StateGraph** for 11-node RAG pipeline with conditional routing
- **Agent SDK factory** (`create_agent`) for tool selection and conversation memory
- **Dependency injection** via `BotContext` dataclass passed through agent tools
- **Hybrid search** with RRF (reciprocal rank fusion) + optional ColBERT reranking
- **Multi-tier caching** (Redis) with embeddings + search result + dense response caches
- **Langfuse observability** with 35 observations/trace, 25 scored metrics, PII masking
- **Telegram + FastAPI + LiveKit** interfaces for text, voice, and API access

## Layers

**Presentation Layer:**
- Purpose: User interaction via Telegram bot, HTTP API, or Voice (LiveKit)
- Location: `telegram_bot/bot.py`, `src/api/main.py`, `src/voice/agent.py`
- Contains: Command handlers, message routing, voice transcription UI
- Depends on: Agent layer, LangGraph pipeline
- Used by: Telegram users, API clients, voice callers

**Agent/Tool Layer:**
- Purpose: LLM-driven tool selection and multi-turn conversation
- Location: `telegram_bot/agents/agent.py`, `telegram_bot/agents/context.py`, `telegram_bot/agents/rag_tool.py`, `telegram_bot/agents/history_tool.py`, `telegram_bot/agents/crm_tools.py`
- Contains: `create_bot_agent()` SDK factory, BotContext DI, 8 CRM tools, RAG search, history search
- Depends on: LangGraph pipeline, CRM client, history service
- Used by: Bot handle_query, conversation flows

**RAG Pipeline Layer (LangGraph):**
- Purpose: 11-node state machine for query processing, retrieval, and response generation
- Location: `telegram_bot/graph/graph.py`, `telegram_bot/graph/state.py`, `telegram_bot/graph/nodes/`
- Contains: START → guard → transcribe → classify → cache_check → retrieve → grade → rerank → generate → cache_store → respond → END
- Depends on: Services layer (embeddings, Qdrant, cache, LLM)
- Used by: Agent tools, API endpoints

**Services Layer:**
- Purpose: Domain logic for embeddings, vector search, caching, LLM calls, content filtering
- Location: `telegram_bot/services/`, `telegram_bot/integrations/`
- Contains:
  - Embeddings: `bge_m3_client.py` (BGE-M3 dual-stack dense+sparse), `voyage.py` (Voyage API)
  - Vector DB: `qdrant.py` (gRPC async client, batch queries)
  - Cache: `integrations/cache.py` (6-tier CacheLayerManager)
  - LLM: `llm.py` (LiteLLM via Cerebras/OpenAI)
  - Reranker: `colbert_reranker.py` (ColBERT scoring)
  - Content filter: `llm_guard_client.py` (toxicity + injection detection)
  - CRM: `kommo_client.py` (OAuth2 auto-refresh), `kommo_token_store.py` (Redis-backed tokens)
  - Query processing: `query_preprocessor.py`, `query_analyzer.py`, `normalizer.py`
  - Analytics: `lead_scoring.py`, `funnel_analytics_service.py`, `nurturing_scheduler.py`
- Depends on: External APIs (BGE-M3, Qdrant, Redis, OpenAI, Kommo, etc.)
- Used by: RAG pipeline, Agent tools

**Configuration Layer:**
- Purpose: Load and validate environment configuration
- Location: `telegram_bot/config.py`, `telegram_bot/graph/config.py`, `src/config/settings.py`
- Contains: BotConfig (Pydantic BaseSettings), GraphConfig (dataclass), Settings (legacy)
- Depends on: Environment variables, `.env` file
- Used by: Bot initialization, graph assembly

**Data/Model Layer:**
- Purpose: Data models and state schemas
- Location: `telegram_bot/graph/state.py`, `telegram_bot/models/`, `src/models/`, `telegram_bot/services/kommo_models.py`
- Contains: RAGState (TypedDict with 25+ fields), Pydantic models for CRM, embeddings, evaluations
- Depends on: Pydantic v2
- Used by: RAG pipeline, services, API responses

**Ingestion Pipeline:**
- Purpose: Parse documents, chunk, embed, and index into Qdrant
- Location: `src/ingestion/unified/` (CocoIndex v3.2.1), legacy at `src/ingestion/`
- Contains: Document parser (Docling), chunker, BGE-M3/Voyage embeddings, Qdrant writer, state manager
- Depends on: Docling, CocoIndex, BGE-M3/Voyage, Qdrant
- Used by: Administrative CLI, scheduled sync

**Observability Layer:**
- Purpose: Trace collection, scoring, and PII masking
- Location: `telegram_bot/observability.py`, `telegram_bot/scoring.py`
- Contains: `@observe` decorator, `propagate_attributes` context manager, `write_langfuse_scores()`, PII redaction
- Depends on: Langfuse SDK v3
- Used by: All layers (decorator-based, non-invasive)

## Data Flow

**Text Query (main path):**

1. User sends `/start` or text message → `PropertyBot.handle_query(message)` (throttled + error-handled)
2. Delegate to `_handle_query_supervisor()` → build tools list
3. Create `BotContext` (DI container with embeddings, Qdrant, cache, LLM, etc.)
4. Call `create_bot_agent()` → LLM routes to tool: `rag_search | history_search | 8 CRM tools | direct response`
5. Tool executes via `BotContext` injection → **RAG Pipeline** (`build_graph().ainvoke(state)`)
   - **guard_node** → regex toxicity + injection detection (LLM-based optional)
   - **classify_node** → detect CHITCHAT/OFF_TOPIC (regex)
   - **cache_check_node** → check 3-tier cache (embeddings, search, response)
   - **retrieve_node** → parallel BGE-M3 dense + sparse on Qdrant (RRF merge)
   - **grade_node** → score results by RRF threshold (0.005), set `grade_confidence`
   - **rerank_node** → ColBERT (if enabled and confidence < 0.012)
   - **generate_node** → LiteLLM streaming to Telegram (aiogram edit_text)
   - **rewrite_node** → optional query rewrite if grade < threshold
   - **cache_store_node** → write response to cache
   - **respond_node** → send final Markdown response
6. Write Langfuse scores (14 RAG metrics + 4 history + 3 supervisor + 4 CRM)
7. Return response text → bot sends via Telegram

**Voice Query path:**

1. User sends voice `.ogg` file → `PropertyBot.handle_voice(message)`
2. Download `.ogg` bytes → inject into initial `RAGState` with `voice_audio=bytes, input_type="voice"`
3. **transcribe_node** → Whisper API via LiteLLM (auto language detection via `VOICE_LANGUAGE`)
4. **guard_node** → same toxicity check
5. (Remaining 9 nodes same as text path)
6. Render response with transcription preview (if `SHOW_TRANSCRIPTION=true`)

**API Query path (RAG API, no agent):**

1. POST `/query` with `QueryRequest` → `src/api/main.py`
2. Build `RAGState` directly (no agent layer)
3. Call `build_graph().ainvoke(state)` (same 11-node pipeline)
4. Return `QueryResponse` JSON → client

**Voice Bot path (LiveKit + SIP):**

1. User `/call → Telegram → LiveKit API dispatch
2. LiveKit SIP Agent answers call → ElevenLabs STT (80ms)
3. Agent calls RAG API (POST `/query`, receives JSON response)
4. Generate response → ElevenLabs TTS (75ms) → SIP stream

**State Management:**

- **RAGState** (25+ fields): Flows through all 11 nodes, each node mutates subsets
- **Agent messages**: Langchain HumanMessage + AIMessage list for conversation history
- **Checkpointer**: Optional Postgres/Redis for conversation persistence (LangGraph checkpoint mechanism)
- **Cache**: 6-tier manager (embedding cache → search cache → response cache)

## Key Abstractions

**RAGState (TypedDict):**
- Purpose: Unified state schema for all pipeline nodes
- Examples: `telegram_bot/graph/state.py`
- Pattern: Typed dictionary with 25+ fields (messages, user_id, query_type, documents, response, latency_stages, etc.)

**BotContext (dataclass):**
- Purpose: Dependency injection container for agent tools
- Examples: `telegram_bot/agents/context.py`
- Pattern: Dataclass with lazy imports of services, injected via `config["configurable"]["bot_context"]`

**Node functions (StateGraph nodes):**
- Purpose: Encapsulate transformation logic for single RAG step
- Examples: `telegram_bot/graph/nodes/guard.py`, `retrieve.py`, `generate.py`
- Pattern: `async def node_name(state: dict[str, Any]) -> dict[str, Any]` with partial dependencies

**Tool functions (@tool decorated):**
- Purpose: LLM-callable actions that execute sub-pipelines
- Examples: `telegram_bot/agents/rag_tool.py`, `history_tool.py`, `crm_tools.py`
- Pattern: `@tool` decorator + async function + BotContext injection via `get_context()`

**Service clients (async httpx/gRPC):**
- Purpose: Encapsulate external API communication
- Examples: `BGEM3HybridEmbeddings`, `QdrantService`, `KommoClient`
- Pattern: Async Python classes with error handling, token refresh, batch operations

**CacheLayerManager (6-tier):**
- Purpose: Efficient multi-level caching to reduce external API calls
- Examples: `telegram_bot/integrations/cache.py`
- Pattern: Embedding cache (TTL) → Search cache (TTL) → Response cache (TTL)

## Entry Points

**Telegram Bot:**
- Location: `telegram_bot/main.py`
- Triggers: `python -m telegram_bot.main` or Docker entrypoint
- Responsibilities: Load BotConfig, initialize PropertyBot, start aiogram Dispatcher, handle interrupts

**RAG API:**
- Location: `src/api/main.py`
- Triggers: `uvicorn src.api.main:app --host 0.0.0.0 --port 8080` or Docker entrypoint
- Responsibilities: FastAPI lifespan setup (cache, embeddings, Qdrant, LLM), POST /query handler, GET /health

**Voice Bot (LiveKit):**
- Location: `src/voice/agent.py`
- Triggers: `python -m src.voice.agent` or Docker entrypoint
- Responsibilities: LiveKit server initialization, webhook for agent dispatch, RAG API client

**Ingestion CLI:**
- Location: `src/ingestion/unified/cli.py`
- Triggers: `python -m src.ingestion.unified.cli preflight|bootstrap|run|status|reprocess`
- Responsibilities: Validate Docling, initialize Postgres, run CocoIndex flow, manage indexing state

## Error Handling

**Strategy:** Layered fallbacks with Langfuse error spans

**Patterns:**
- **Node-level**: Try service call → catch → log error span → set state error flags (`retrieval_backend_error`, `embedding_error`) → continue
- **Guard**: Injection detected → respond with blocking message (GUARD_MODE=hard) or flag (soft) or log (log)
- **LLM**: OpenAI 429/timeout → use fallback model or reuse cached response
- **Embeddings**: BGE-M3 timeout → exponential backoff (3 attempts, 5s + 10s + 20s)
- **Rerank**: ColBERT unavailable → skip and generate from top-k RRF results
- **Cache**: Redis connection lost → skip cache, hit primary services (Qdrant, LLM)
- **Voice**: Whisper empty transcription → user-friendly message "Голосовое не содержит речи."

## Cross-Cutting Concerns

**Logging:** Structured JSON logging with `logging_config.py` (json format or text), log level via `LOG_LEVEL` env var, file output via `LOG_FILE` env var

**Validation:** Pydantic v2 models for config, API schemas, CRM responses; runtime checks for null/empty fields

**Authentication:**
- Telegram: `TELEGRAM_BOT_TOKEN` (bot must be owned)
- Kommo: OAuth2 auto-refresh with Redis-backed token store (`KommoTokenStore`)
- OpenAI/Cerebras: API key via `OPENAI_API_KEY` (LiteLLM routing)
- Langfuse: SDK key + public key for tracing
- Voice: LiveKit API key/secret, Elevenlabs API key for STT/TTS

**Rate Limiting:** ThrottlingMiddleware per user (Telegram) with 1.5s TTL, admin bypass via `ADMIN_IDS` env var

**Conversation State:** LangGraph checkpointer (Postgres or Redis) persists agent messages between requests, enables multi-turn context

**Observability:**
- Langfuse `@observe` spans on 6 heavy nodes (retrieve, grade, rerank, generate, respond, tools)
- Error spans on 4 nodes (guard, retrieve, rerank, generate)
- 25 scored metrics: 14 RAG (cache_hit, grade_confidence, rerank_applied, latency, etc.) + 4 history + 3 supervisor + 4 CRM
- PII masking on user queries and responses (regex-based phone, email, names)

---

*Architecture analysis: 2026-02-19*
