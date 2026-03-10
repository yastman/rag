---
paths: "telegram_bot/services/**/*.py, telegram_bot/integrations/**/*.py, telegram_bot/pipelines/**/*.py"
---

# Service & Integration Patterns

Code patterns for `telegram_bot/services/` and `telegram_bot/integrations/`.

## Directory Structure

```
telegram_bot/
├── bot.py                 # PropertyBot (thin router: client→pipeline, manager→agent)
├── config.py              # BotConfig (pydantic-settings BaseSettings)
├── observability.py       # Langfuse init, @observe decorator, PII masking
├── preflight.py           # Health checks (Redis, Qdrant, BGE-M3, LiteLLM)
├── pipelines/             # Deterministic orchestration (no agent loop)
│   ├── __init__.py
│   └── client.py          # run_client_pipeline(), detect_agent_intent() (#567)
├── services/              # Business logic services
│   ├── types.py           # PipelineResult dataclass (#567)
│   ├── generate_response.py # Shared LLM generation (streaming, style, fallback)
│   ├── llm.py             # LLMService (OpenAI SDK, langfuse.openai.AsyncOpenAI)
│   ├── query_analyzer.py  # QueryAnalyzer (LLM filter extraction)
│   ├── query_preprocessor.py # HyDEGenerator + QueryPreprocessor
│   ├── filter_extractor.py # Regex filter extraction
│   ├── normalizer.py      # Text normalization
│   ├── qdrant.py          # QdrantService (async, gRPC, batch_search_rrf, group_by)
│   ├── bge_m3_client.py   # BGEM3Client (async) + BGEM3SyncClient
│   ├── colbert_reranker.py # ColbertRerankerService (uses BGEM3Client)
│   ├── voyage.py          # VoyageService (embeddings + rerank API)
│   ├── vectorizers.py     # UserBaseVectorizer + BgeM3CacheVectorizer
│   ├── small_to_big.py    # Small-to-big context expansion
│   ├── history_service.py # Conversation history retrieval
│   ├── session_summary.py / session_summary_worker.py  # Session compression
│   ├── metrics.py         # PipelineMetrics (p50/p95 tracking)
│   ├── redis_monitor.py   # RedisHealthMonitor (background task)
│   ├── user_service.py    # User profile management
│   ├── response_style_detector.py  # Detect response style preference
│   ├── llm_guard_client.py         # LLM Guard integration
│   ├── draft_streamer.py           # Draft message streaming to Telegram
│   ├── ingestion_cocoindex.py      # Ingestion service client
│   ├── manager_menu.py             # Manager menu handlers
│   ├── hot_lead_notifier.py        # Hot lead Telegram notifications
│   ├── kommo_client.py        # KommoClient (async httpx, OAuth2 auto-refresh)
│   ├── kommo_token_store.py   # KommoTokenStore (Redis hash, OAuth2 token mgmt)
│   ├── kommo_tokens.py        # Token helpers
│   ├── kommo_models.py        # Pydantic v2: Lead, Contact, Note, Task, Pipeline
│   ├── lead_scoring_models.py  # LeadScoreRecord, LeadScoreSyncPayload
│   ├── lead_scoring_store.py   # LeadScoringStore (asyncpg upsert, pending sync)
│   ├── lead_scoring.py         # Lead scoring logic
│   ├── lead_score_sync.py      # Kommo sync background task
│   ├── funnel_lead_scoring.py  # Funnel-based scoring
│   ├── funnel_analytics_store.py   # FunnelAnalyticsStore (daily metrics)
│   ├── funnel_analytics_service.py # FunnelAnalyticsService
│   ├── nurturing_service.py    # NurturingService
│   ├── topic_manager.py         # Forum topic create/archive (supergroup topics)
│   ├── topic_service.py         # TopicService — topic routing for manager notifications
│   └── nurturing_scheduler.py  # NurturingScheduler (APScheduler v3)
├── integrations/          # LangGraph-compatible wrappers
│   ├── cache.py           # CacheLayerManager (6-tier, Redis pipelines)
│   ├── embeddings.py      # BGEM3HybridEmbeddings + legacy wrappers
│   ├── event_stream.py    # EventStream for graph→bot communication
│   ├── langfuse.py        # (legacy) Langfuse callback handler — replaced by @observe
│   ├── memory.py          # MemorySaver for conversation persistence
│   ├── prompt_manager.py  # Langfuse Prompt Management with fallback templates
│   └── prompt_templates.py # Hardcoded fallback prompt templates
└── graph/                 # LangGraph pipeline
    ├── graph.py           # build_graph() — 11-node StateGraph assembly
    ├── state.py           # RAGState TypedDict + make_initial_state()
    ├── edges.py           # 4 routing functions (incl. route_guard)
    ├── config.py          # GraphConfig (service factories, guard_mode)
    └── nodes/             # 9 node modules (incl. guard.py — content filtering)
```

## Key Patterns

### OpenAI SDK (LLM services)

All LLM-calling services use `langfuse.openai.AsyncOpenAI`:

```python
from langfuse.openai import AsyncOpenAI

self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=2, timeout=30.0)
response = await self.client.chat.completions.create(
    model=self.model, messages=[...],
    name="operation-name",  # type: ignore[call-overload]  # langfuse kwarg
)
```

### Embeddings (integrations)

```python
from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

# Preferred: single /encode/hybrid call, shared httpx.AsyncClient
emb = BGEM3HybridEmbeddings(base_url="http://bge-m3:8000")
dense, sparse = await emb.aembed_hybrid("text")  # (list[float], dict) in 1 call
vector = await emb.aembed_query("text")           # dense only (LangChain compat)
```

### QdrantService (gRPC + batch)

```python
from telegram_bot.services.qdrant import QdrantService

# Uses prefer_grpc=True for faster connections
qdrant = QdrantService(url="http://localhost:6333", collection_name="gdrive_documents_bge")

# Single hybrid search
results = await qdrant.hybrid_search_rrf(dense_vector=emb, sparse_vector=sparse, top_k=20)

# Server-side ColBERT reranking (#569) — nested prefetch: RRF → MaxSim rescore
results = await qdrant.hybrid_search_rrf_colbert(
    dense_vector=emb, colbert_query=colbert_vecs, sparse_vector=sparse, top_k=20
)

# Batch search (single round-trip via query_batch_points)
results = await qdrant.batch_search_rrf(queries=[...])

# Group-by for diverse results
results = await qdrant.hybrid_search_rrf(dense_vector=emb, sparse_vector=sparse, group_by="doc_id")
```

### CacheLayerManager (Redis pipelines)

```python
from telegram_bot.integrations.cache import CacheLayerManager

cache = CacheLayerManager(redis_url="redis://redis:6379")
await cache.initialize()
# CACHE_VERSION = "v5", keys: {tier}:v5:{hash}
# Uses async Redis pipelines for batch operations (1 round-trip)
```

### Prompt Manager (Langfuse)

```python
from telegram_bot.integrations.prompt_manager import get_prompt, get_prompt_with_config

# Text only (backwards compatible)
prompt = get_prompt(name="rag-system", fallback="You are...", variables={"domain": "real estate"})

# Text + config (temperature, max_tokens editable in Langfuse UI)
prompt_text, config = get_prompt_with_config(name="generate", fallback="...", variables={"domain": "..."})
# config = {"temperature": 0.7, "max_tokens": 512} or {} if fallback
```

Flow: `_probe_prompt_available()` (API) → TTL cache hit/miss → `client.get_prompt()` (SDK) or fallback.
Missing prompts cached 1h to avoid repeated API calls and SDK `generate-label:production` warnings.

**Seed prompts:** `uv run python scripts/seed_langfuse_prompts.py` — seeds 11 prompts with config (temperature, max_tokens) from code fallbacks. `--force` to overwrite.

### GraphConfig (service factories + pipeline tuning)

```python
from telegram_bot.graph.config import GraphConfig

gc = GraphConfig.from_env()              # reads MAX_REWRITE_ATTEMPTS, SKIP_RERANK_THRESHOLD, etc.
llm = gc.create_llm()                    # langfuse.openai.AsyncOpenAI
hybrid = gc.create_hybrid_embeddings()   # BGEM3HybridEmbeddings (preferred)
sparse = gc.create_sparse_embeddings()   # BGEM3SparseEmbeddings
# gc.skip_rerank_threshold (0.018), gc.relevance_threshold_rrf (0.005)
```

## Cache Key Versioning

`CACHE_VERSION = "v5"` in `integrations/cache.py`. Key patterns:

| Pattern | Tier |
|---------|------|
| `sem:v5:bge1024` | Semantic cache |
| `embeddings:v5:{hash}` | Dense embeddings |
| `sparse:v5:{hash}` | Sparse embeddings |
| `search:v5:{hash}` | Search results |
| `conversation:{user_id}` | Chat history |

Bump version when changing models. Old keys expire naturally.

### Kommo CRM Client (#413)

```python
from telegram_bot.services.kommo_client import KommoClient
from telegram_bot.services.kommo_token_store import KommoTokenStore

# Token store — Redis-backed OAuth2 with auto-refresh (5-min buffer before expiry)
token_store = KommoTokenStore(redis=redis, subdomain="mycompany", client_id=..., client_secret=...)

# Client — async httpx, auto-refresh on 401, all methods @observe-traced
kommo = KommoClient(subdomain="mycompany", token_store=token_store)
lead = await kommo.create_lead(LeadCreate(name="New deal", budget=50000))
contact = await kommo.upsert_contact("+1234567890", ContactCreate(first_name="John"))
await kommo.link_contact_to_lead(lead.id, contact.id)
await kommo.close()  # close httpx client
```

**Token init fallback (#678):** `bot.py` init chain: `KOMMO_AUTH_CODE` → `token_store.seed_env_token()` (seeds Redis from `KOMMO_ACCESS_TOKEN` env) → check existing Redis → disable. Env vars: `KOMMO_CLIENT_ID`, `KOMMO_CLIENT_SECRET`, `KOMMO_REDIRECT_URI`, `KOMMO_ACCESS_TOKEN`.

**get_valid_token() guard (#682):** Skips token refresh if `refresh_token` empty — returns `access_token` as-is. Prevents 401 errors on seeded tokens without refresh capability.

**Traced spans:** `kommo-create-lead`, `kommo-get-lead`, `kommo-update-lead`, `kommo-upsert-contact`, `kommo-get-contacts`, `kommo-add-note`, `kommo-create-task`, `kommo-link-contact`, `kommo-list-pipelines`

**Token seed fallback (#678, #686):** Init chain order: `KOMMO_AUTH_CODE` present → exchange; else check Redis → tokens exist → proceed; else `KOMMO_ACCESS_TOKEN` set → `token_store.seed_env_token(token)` → proceed; else disable CRM. `seed_env_token()` stores access token with empty refresh_token and expires_at=0 so `get_valid_token()` returns it as-is (no refresh attempted).

### CRM Services (#384, #390)

```python
from telegram_bot.services.lead_scoring_store import LeadScoringStore
from telegram_bot.services.nurturing_service import NurturingService
from telegram_bot.services.funnel_analytics_service import FunnelAnalyticsService

# Lead scoring — asyncpg, upsert with sync_status tracking
store = LeadScoringStore(pool=asyncpg_pool)
await store.upsert_score(user_id, score_record)
pending = await store.get_pending_sync()  # for Kommo sync

# Nurturing — APScheduler v3 for batch scheduling
nurturing = NurturingService(...)
scheduler = NurturingScheduler(nurturing, interval_minutes=config.nurturing_interval)

# Funnel — daily conversion/dropoff snapshots
funnel = FunnelAnalyticsService(store=FunnelAnalyticsStore(pool))
```

**DB tables:** `lead_scores`, `lead_score_sync_audit`, `nurturing_jobs`, `funnel_metrics_daily`, `scheduler_leases`

## I/O Patterns

- **LangGraph nodes**: Async functions with `state: dict[str, Any]` signature
- **Services**: Async (`httpx.AsyncClient`, `AsyncQdrantClient` with gRPC, `AsyncOpenAI`)
- **Search Engines (src/retrieval)**: Sync Qdrant SDK for evaluation benchmarks
- **Redis**: Async pipelines for batch operations (`async with redis.pipeline()`)
- No blocking calls in async context for bot handlers

## Apartments Domain (#632)

```
telegram_bot/services/
├── apartment_models.py           # ApartmentRecord, view normalization, confidence scoring
├── apartment_filter_extractor.py # Regex parser: rooms, price, complex, view, floor, area
├── apartments_service.py         # ApartmentsService — hybrid search with payload filtering
├── favorites_service.py          # User apartment favorites (asyncpg)
├── content_loader.py             # Services YAML config loader (cached)
```

**Two-stage routing:**
1. **Fast path** (0 LLM calls): `ApartmentFilterExtractor` → regex → payload-filtered hybrid search → direct response
2. **Agent escalation**: LOW confidence or special signals → agent with `apartment_search` @tool

**Qdrant:** Collection with 10 payload indexes. Top-level filters (no `metadata.` prefix). Payload: rooms, price_usd, complex_name, city, district, view, floor, area_m2, property_type, status.

**Scripts:** `scripts/apartments/ingest.py` (CSV → BGE-M3 → Qdrant), `scripts/apartments/setup_collection.py`

## Hot Lead Notifier

`telegram_bot/services/hot_lead_notifier.py` — sends Telegram notifications to `MANAGER_IDS` when `lead_score >= MANAGER_HOT_LEAD_THRESHOLD` (default 60). Redis deduplication with TTL (default 3600s).

## Session Summary Worker

`telegram_bot/services/session_summary.py` + `session_summary_worker.py` — LLM-generated structured CRM note from conversation dialog. Pydantic output schema. Async background processing.

## Response Style Detector

`telegram_bot/services/response_style_detector.py` — zero-latency regex-based style/difficulty classifier. Determines response format (simple, detailed, structured) without LLM call. Used in `generate_response()`.
