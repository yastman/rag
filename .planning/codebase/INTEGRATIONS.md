# External Integrations

**Analysis Date:** 2026-02-19

## APIs & External Services

**LLM Providers:**
- Cerebras (gpt-oss-120b) - Primary via LiteLLM (`zai-glm-4.7` model)
  - SDK/Client: `langfuse.openai.AsyncOpenAI` (wraps OpenAI SDK)
  - Auth: `CEREBRAS_API_KEY` (via `LLM_API_KEY` or `OPENAI_API_KEY`)
  - Endpoint: `https://api.cerebras.ai/v1` (configurable via `LLM_BASE_URL`)

- Groq (llama-3.1-70b) - Fallback via LiteLLM
  - SDK/Client: langfuse.openai.AsyncOpenAI
  - Auth: `GROQ_API_KEY`

- OpenAI (gpt-4o-mini) - Fallback via LiteLLM
  - SDK/Client: langfuse.openai.AsyncOpenAI
  - Auth: `OPENAI_API_KEY`

- Anthropic Claude (optional) - Direct client
  - SDK/Client: `anthropic.Anthropic`
  - Auth: `ANTHROPIC_API_KEY`

**Embeddings & Ranking:**
- Voyage AI (`voyageai>=0.3.0`) - Legacy embeddings + reranking
  - Models: `voyage-4-large` (docs), `voyage-4-lite` (queries), `rerank-2.5` (reranking)
  - Auth: `VOYAGE_API_KEY`
  - Config: `VOYAGE_EMBED_MODEL`, `VOYAGE_CACHE_MODEL`, `VOYAGE_RERANK_MODEL`, `VOYAGE_EMBEDDING_DIM`
  - Note: Optional; replaced by BGE-M3 local API in dev/VPS

- BGE-M3 (local API, via `FlagEmbedding`) - Dense + sparse embeddings
  - Endpoint: `http://localhost:8000` (dev) or `http://bge-m3:8000` (Docker)
  - Models: BGE-M3 dense (1024-dim), BGE-M3 sparse (BM42 indices)
  - Client: `BGEM3Client` (async httpx, from `telegram_bot/services/bge_m3_client.py`)
  - Endpoints: `/encode/dense`, `/encode/sparse`, `/encode/hybrid` (batch)
  - Config: `BGE_M3_URL`, `BGE_M3_TIMEOUT` (120s default)
  - Reranking: ColBERT via same BGE-M3 API endpoint

**STT (Speech-to-Text):**
- Whisper (via LiteLLM) - Voice transcription
  - Model: `whisper` (OpenAI's Whisper via LiteLLM)
  - Auth: `OPENAI_API_KEY`
  - Config: `STT_MODEL`, `VOICE_LANGUAGE` (ISO code, default `ru`)
  - Endpoint: via LiteLLM proxy (:4000)

- ElevenLabs (optional, voice profile) - TTS for voice bot
  - SDK: `livekit-plugins-elevenlabs`
  - Auth: `ELEVENLABS_API_KEY`

**Real Estate Data (optional):**
- Google Drive (legacy) - Document sourcing (via gdrive_indexer, replaced by CocoIndex)
  - Auth: Service account credentials

## Data Storage

**Vector Database:**
- Qdrant v1.16.2+ - Primary vector search backend
  - Connection: `http://localhost:6333` (HTTP) or gRPC `:6334`
  - Protocol: gRPC preferred (async, batch operations)
  - Client: `qdrant-client>=1.16.2` (AsyncQdrantClient from `telegram_bot/services/qdrant.py`)
  - Collections:
    - `gdrive_documents_bge` (prod) - BGE-M3 embeddings, 1024-dim dense
    - `contextual_bulgaria_voyage` (dev) - 192 real estate docs, Voyage embeddings
    - `legal_documents` (dev) - 1,294 Ukrainian Criminal Code docs, BGE-M3
    - `conversation_history` - Chat history snippets
  - Features: Group-by for diversity, quantization (scalar/binary), BM42 sparse indices
  - Config: `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, `QDRANT_TIMEOUT` (30s)

**Relational Database:**
- PostgreSQL 17 (pgvector extension) - Metadata, CRM state, voice transcripts
  - Connection: `postgresql://postgres:password@postgres:5432`
  - Client: `asyncpg>=0.31.0`
  - Tables:
    - `lead_scores` - CRM lead scoring with sync_status
    - `lead_score_sync_audit` - Audit trail for Kommo sync
    - `nurturing_jobs` - APScheduler job history
    - `funnel_metrics_daily` - Daily funnel snapshots
    - `scheduler_leases` - Distributed lock for multi-instance scheduling
  - Voice profile: voice_database_url for transcripts
  - Config: `POSTGRES_PASSWORD`, `REALESTATE_DATABASE_URL` (CRM), `VOICE_DATABASE_URL`

**Caching & State:**
- Redis 8.6.0 - Session cache, embedding cache, semantic similarity cache
  - Connection: `redis://localhost:6379`
  - Protocol: Async pipelines via `redis>=7.1.0`
  - Password: `REDIS_PASSWORD` (required)
  - Memory config: 512MB default with LFU eviction
  - Cache tiers (6-tier CacheLayerManager):
    - Semantic cache (distance-based)
    - Exact match cache (query hash)
    - Embedding cache (dense vectors)
    - Sparse embedding cache (BM42 weights)
    - Search results cache (RRF scores)
    - Conversation history cache (user session)
  - TTL: Semantic default 3600s (configurable via `SEMANTIC_CACHE_TTL_DEFAULT`)
  - LangGraph checkpointing: Redis backend via `langgraph-checkpoint-redis`
  - Config: `REDIS_URL`, `REDIS_PASSWORD`, `SEMANTIC_CACHE_THRESHOLD`

**File Storage (optional):**
- Local filesystem only - No S3 integration in core bot
- Voice profile uses Minio (S3-compatible) via docker-compose.dev.yml (Langfuse storage)

## Authentication & Identity

**Telegram User Auth:**
- Telegram Bot API - Implicit auth via `TELEGRAM_BOT_TOKEN`
  - Framework: aiogram 3.25.0
  - User context: `message.from_user.id` (9-10 digit user ID)
  - Session scope: user_id + session_id (chat-{hash}-{YYYYMMDD} format)

**CRM (Kommo) OAuth2 (#413):**
- Kommo CRM API v4 - OAuth2 with auto-refresh
  - Client: `KommoClient` (async httpx) from `telegram_bot/services/kommo_client.py`
  - Token store: `KommoTokenStore` (Redis-backed) from `telegram_bot/services/kommo_token_store.py`
  - Auth flow:
    - Client credentials: `KOMMO_CLIENT_ID`, `KOMMO_CLIENT_SECRET`
    - Auth code: `KOMMO_AUTH_CODE` (initial, then auto-refresh)
    - Redirect URI: `KOMMO_REDIRECT_URI`
    - Subdomain: `KOMMO_SUBDOMAIN` (e.g., "mycompany")
  - Token refresh: Automatic on 401, cached in Redis with 5-min refresh buffer
  - Scope: Leads, contacts, tasks, notes, pipelines
  - Config: All KOMMO_* env vars (see .env.example)

**Qdrant API Key (optional):**
- Qdrant cloud or secured deployments
  - Auth: `QDRANT_API_KEY` (optional, for cloud instances)

## Monitoring & Observability

**Error Tracking & Tracing:**
- Langfuse v3 - LLM observability and baseline regression detection
  - Client: `langfuse.openai.AsyncOpenAI` (for tracing LLM calls)
  - SDK: `langfuse>=3.14.0` (for @observe decorator, scores, prompt management)
  - Auth: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
  - Endpoint: `http://localhost:3001` (dev, docker-compose.dev.yml)
  - Features:
    - Automatic tracing via CallbackHandler
    - 35 observations per trace (14 RAG + 4 history + 3 supervisor + 4 CRM + judge scores)
    - 25 scores (semantic cache hit, embeddings cache, rerank applied, LLM latency, etc.)
    - Managed evaluators for LLM-as-a-Judge (faithfulness, relevance)
    - Prompt management (versioned templates with fallback)
    - Session ID format: `chat-{hash}-{YYYYMMDD}` (Telegram), `validate-{run_id}` (validation)
  - Graceful disable: When `LANGFUSE_SECRET_KEY` is empty, all tracing is no-op
  - Config: `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`

**Logs:**
- Docker container logs - Via `docker logs dev-bot --tail 50` or `docker logs vps-bot`
- Structured JSON logging - Via `telegram_bot/logging_config.py` (custom logger format)
- Loki (optional, obs profile) - Log aggregation via docker-compose.dev.yml
  - Storage: ClickHouse (time-series analytics)
  - Collection: Promtail (tails Docker container logs)
  - Retention: Default 72 hours
  - Queries: Via Grafana UI

## CI/CD & Deployment

**Hosting:**
- Docker Compose (dev) - Local development, docker-compose.dev.yml
- k3s cluster (prod) - VPS at 95.111.252.29, manifests in `k8s/`
- Docker images built via `docker buildx bake` (parallel multi-target build)

**CI Pipeline:**
- GitHub Actions (.github/workflows/ci.yml)
  - `lint` job - Ruff + MyPy strict type checking
  - `test-fast` job - Unit tests with pytest-split sharding (4 shards)
  - `test-nightly` job - Chaos/load/E2E tests (scheduled)
  - `baseline-compare` job - Langfuse regression detection (PR-only)
- Pre-commit hooks - Git hook automation via pre-commit 3.8.0+
  - ruff-check (--fix) → ruff-format → trailing-whitespace → check-yaml/json/toml

**Secrets Management:**
- .env files (git-ignored) - Development secrets
- GitHub Secrets (Actions) - CI/production secrets
- Redis-backed KommoTokenStore - OAuth2 tokens (auto-refresh)
- No hardcoded credentials in code or docker-compose

## Webhooks & Callbacks

**Incoming Webhooks:**
- Telegram bot message handler - Long-polling via aiogram.Dispatcher
  - No webhook endpoint exposed (polling-based)
  - Callback handlers for:
    - User messages (text, voice, document)
    - Inline buttons (feedback like/dislike)
    - Commands (/start, /help, /clear, /stats, /metrics)

**Outgoing Webhooks:**
- Telegram Bot API - Message delivery
  - HTTP POST to `api.telegram.org/botTOKEN/sendMessage`
  - Methods: `send_message`, `edit_text`, `send_voice`, `add_reaction`, etc.
  - Client: aiogram.Bot (async, built-in retry)

- Kommo CRM API - Lead/contact/task creation
  - HTTP POST/PATCH to `{subdomain}.kommo.com/api/v4/leads`, `/contacts`, `/tasks`, `/notes`
  - Retry: Exponential backoff via tenacity (3 attempts, 1-8s jitter)
  - Methods: All 9 @tools in `telegram_bot/agents/crm_tools.py`

- Langfuse API - Trace submission
  - Async batching, auto-flush on batch size or timeout
  - Event streaming during trace execution

- LiveKit API (voice profile) - Room/participant management
  - WebRTC signaling via `livekit.RoomServiceClient`
  - URL: `ws://localhost:7880` (dev) or production endpoint
  - Auth: `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`

## Environment Configuration

**Required env vars:**
- `TELEGRAM_BOT_TOKEN` - Telegram bot credential
- `CEREBRAS_API_KEY` - LLM provider (or `GROQ_API_KEY`, `OPENAI_API_KEY`)
- `LITELLM_MASTER_KEY` - LiteLLM proxy authentication
- CRM (optional): `KOMMO_LEAD_SCORE_FIELD_ID`, `KOMMO_LEAD_BAND_FIELD_ID`

**Optional but recommended:**
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` - Enable tracing (disables gracefully if absent)
- `OPENAI_API_KEY` - Whisper STT fallback
- `REDIS_PASSWORD` - Redis authentication
- `POSTGRES_PASSWORD` - Postgres authentication

**Secrets location:**
- Development: `.env` file (git-ignored, copy from `.env.example`)
- GitHub Actions: Encrypted GitHub Secrets (`Settings → Secrets`)
- VPS: Environment variables in k3s ConfigMap/Secret (k8s manifests)
- Never commit: `.env`, `credentials.json`, service account keys, API tokens

## CRM Integration (Kommo)

**Lead Scoring:**
- Async lead scoring store (PostgreSQL, asyncpg)
- Sync queue for Kommo custom field updates
- Fields: `KOMMO_LEAD_SCORE_FIELD_ID`, `KOMMO_LEAD_BAND_FIELD_ID`

**Nurturing:**
- APScheduler v3 batch scheduling
- Interval: `NURTURING_INTERVAL_MINUTES` env var
- DB table: `nurturing_jobs`, `scheduler_leases` (distributed lock)

**Funnel Analytics:**
- Daily conversion/dropoff snapshots
- Cron: `FUNNEL_ROLLUP_CRON` env var
- DB table: `funnel_metrics_daily`

---

*Integration audit: 2026-02-19*
