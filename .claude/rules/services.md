---
paths: "telegram_bot/services/**/*.py, telegram_bot/integrations/**/*.py, telegram_bot/pipelines/**/*.py"
---

***REMOVED*** Service & Integration Patterns

Code patterns for `telegram_bot/services/` and `telegram_bot/integrations/`.

***REMOVED******REMOVED*** Directory Structure

```
telegram_bot/
├── bot.py                 ***REMOVED*** PropertyBot (thin router: client→pipeline, manager→agent)
├── config.py              ***REMOVED*** BotConfig (pydantic-settings BaseSettings)
├── observability.py       ***REMOVED*** Langfuse init, @observe decorator, PII masking
├── preflight.py           ***REMOVED*** Health checks (Redis, Qdrant, BGE-M3, LiteLLM)
├── pipelines/             ***REMOVED*** Deterministic orchestration (no agent loop)
│   ├── __init__.py
│   └── client.py          ***REMOVED*** run_client_pipeline(), detect_agent_intent() (***REMOVED***567)
├── services/              ***REMOVED*** Business logic services
│   ├── types.py           ***REMOVED*** PipelineResult dataclass (***REMOVED***567)
│   ├── generate_response.py ***REMOVED*** Shared LLM generation (streaming, style, fallback)
│   ├── llm.py             ***REMOVED*** LLMService (OpenAI SDK, langfuse.openai.AsyncOpenAI)
│   ├── query_analyzer.py  ***REMOVED*** QueryAnalyzer (LLM filter extraction)
│   ├── query_preprocessor.py ***REMOVED*** HyDEGenerator + QueryPreprocessor
│   ├── filter_extractor.py ***REMOVED*** Regex filter extraction
│   ├── normalizer.py      ***REMOVED*** Text normalization
│   ├── qdrant.py          ***REMOVED*** QdrantService (async, gRPC, batch_search_rrf, group_by)
│   ├── bge_m3_client.py   ***REMOVED*** BGEM3Client (async) + BGEM3SyncClient
│   ├── colbert_reranker.py ***REMOVED*** ColbertRerankerService (uses BGEM3Client)
│   ├── voyage.py          ***REMOVED*** VoyageService (embeddings + rerank API)
│   ├── vectorizers.py     ***REMOVED*** UserBaseVectorizer + BgeM3CacheVectorizer
│   ├── small_to_big.py    ***REMOVED*** Small-to-big context expansion
│   ├── history_service.py ***REMOVED*** Conversation history retrieval
│   ├── session_summary.py / session_summary_worker.py  ***REMOVED*** Session compression
│   ├── metrics.py         ***REMOVED*** PipelineMetrics (p50/p95 tracking)
│   ├── redis_monitor.py   ***REMOVED*** RedisHealthMonitor (background task)
│   ├── user_service.py    ***REMOVED*** User profile management
│   ├── response_style_detector.py  ***REMOVED*** Detect response style preference
│   ├── llm_guard_client.py         ***REMOVED*** LLM Guard integration
│   ├── draft_streamer.py           ***REMOVED*** Draft message streaming to Telegram
│   ├── ingestion_cocoindex.py      ***REMOVED*** Ingestion service client
│   ├── manager_menu.py             ***REMOVED*** Manager menu handlers
│   ├── hot_lead_notifier.py        ***REMOVED*** Hot lead Telegram notifications
│   ├── kommo_client.py        ***REMOVED*** KommoClient (async httpx, OAuth2 auto-refresh)
│   ├── kommo_token_store.py   ***REMOVED*** KommoTokenStore (Redis hash, OAuth2 token mgmt)
│   ├── kommo_tokens.py        ***REMOVED*** Token helpers
│   ├── kommo_models.py        ***REMOVED*** Pydantic v2: Lead, Contact, Note, Task, Pipeline
│   ├── lead_scoring_models.py  ***REMOVED*** LeadScoreRecord, LeadScoreSyncPayload
│   ├── lead_scoring_store.py   ***REMOVED*** LeadScoringStore (asyncpg upsert, pending sync)
│   ├── lead_scoring.py         ***REMOVED*** Lead scoring logic
│   ├── lead_score_sync.py      ***REMOVED*** Kommo sync background task
│   ├── funnel_lead_scoring.py  ***REMOVED*** Funnel-based scoring
│   ├── funnel_analytics_store.py   ***REMOVED*** FunnelAnalyticsStore (daily metrics)
│   ├── funnel_analytics_service.py ***REMOVED*** FunnelAnalyticsService
│   ├── nurturing_service.py    ***REMOVED*** NurturingService
│   ├── topic_manager.py         ***REMOVED*** Forum topic create/archive (supergroup topics)
│   ├── topic_service.py         ***REMOVED*** TopicService — topic routing for manager notifications
│   └── nurturing_scheduler.py  ***REMOVED*** NurturingScheduler (APScheduler v3)
├── integrations/          ***REMOVED*** LangGraph-compatible wrappers
│   ├── cache.py           ***REMOVED*** CacheLayerManager (6-tier, Redis pipelines)
│   ├── embeddings.py      ***REMOVED*** BGEM3HybridEmbeddings + legacy wrappers
│   ├── event_stream.py    ***REMOVED*** EventStream for graph→bot communication
│   ├── langfuse.py        ***REMOVED*** (legacy) Langfuse callback handler — replaced by @observe
│   ├── memory.py          ***REMOVED*** MemorySaver for conversation persistence
│   ├── prompt_manager.py  ***REMOVED*** Langfuse Prompt Management with fallback templates
│   └── prompt_templates.py ***REMOVED*** Hardcoded fallback prompt templates
└── graph/                 ***REMOVED*** LangGraph pipeline
    ├── graph.py           ***REMOVED*** build_graph() — 11-node StateGraph assembly
    ├── state.py           ***REMOVED*** RAGState TypedDict + make_initial_state()
    ├── edges.py           ***REMOVED*** 4 routing functions (incl. route_guard)
    ├── config.py          ***REMOVED*** GraphConfig (service factories, guard_mode)
    └── nodes/             ***REMOVED*** 9 node modules (incl. guard.py — content filtering)
```

***REMOVED******REMOVED*** Key Patterns

***REMOVED******REMOVED******REMOVED*** OpenAI SDK (LLM services)

All LLM-calling services use `langfuse.openai.AsyncOpenAI`:

```python
from langfuse.openai import AsyncOpenAI

self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=2, timeout=30.0)
response = await self.client.chat.completions.create(
    model=self.model, messages=[...],
    name="operation-name",  ***REMOVED*** type: ignore[call-overload]  ***REMOVED*** langfuse kwarg
)
```

***REMOVED******REMOVED******REMOVED*** Embeddings (integrations)

```python
from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

***REMOVED*** Preferred: single /encode/hybrid call, shared httpx.AsyncClient
emb = BGEM3HybridEmbeddings(base_url="http://bge-m3:8000")
dense, sparse = await emb.aembed_hybrid("text")  ***REMOVED*** (list[float], dict) in 1 call
vector = await emb.aembed_query("text")           ***REMOVED*** dense only (LangChain compat)
```

***REMOVED******REMOVED******REMOVED*** QdrantService (gRPC + batch)

```python
from telegram_bot.services.qdrant import QdrantService

***REMOVED*** Uses prefer_grpc=True for faster connections
qdrant = QdrantService(url="http://localhost:6333", collection_name="gdrive_documents_bge")

***REMOVED*** Single hybrid search
results = await qdrant.hybrid_search_rrf(dense_vector=emb, sparse_vector=sparse, top_k=20)

***REMOVED*** Server-side ColBERT reranking (***REMOVED***569) — nested prefetch: RRF → MaxSim rescore
results = await qdrant.hybrid_search_rrf_colbert(
    dense_vector=emb, colbert_query=colbert_vecs, sparse_vector=sparse, top_k=20
)

***REMOVED*** Batch search (single round-trip via query_batch_points)
results = await qdrant.batch_search_rrf(queries=[...])

***REMOVED*** Group-by for diverse results
results = await qdrant.hybrid_search_rrf(dense_vector=emb, sparse_vector=sparse, group_by="doc_id")
```

***REMOVED******REMOVED******REMOVED*** CacheLayerManager (Redis pipelines)

```python
from telegram_bot.integrations.cache import CacheLayerManager

cache = CacheLayerManager(redis_url="redis://redis:6379")
await cache.initialize()
***REMOVED*** CACHE_VERSION = "v5", keys: {tier}:v5:{hash}
***REMOVED*** Uses async Redis pipelines for batch operations (1 round-trip)
```

***REMOVED******REMOVED******REMOVED*** Prompt Manager (Langfuse)

```python
from telegram_bot.integrations.prompt_manager import get_prompt, get_prompt_with_config

***REMOVED*** Text only (backwards compatible)
prompt = get_prompt(name="rag-system", fallback="You are...", variables={"domain": "real estate"})

***REMOVED*** Text + config (temperature, max_tokens editable in Langfuse UI)
prompt_text, config = get_prompt_with_config(name="generate", fallback="...", variables={"domain": "..."})
***REMOVED*** config = {"temperature": 0.7, "max_tokens": 512} or {} if fallback
```

Flow: `_probe_prompt_available()` (API) → TTL cache hit/miss → `client.get_prompt()` (SDK) or fallback.
Missing prompts cached 1h to avoid repeated API calls and SDK `generate-label:production` warnings.

**Seed prompts:** `uv run python scripts/seed_langfuse_prompts.py` — seeds 11 prompts with config (temperature, max_tokens) from code fallbacks. `--force` to overwrite.

***REMOVED******REMOVED******REMOVED*** GraphConfig (service factories + pipeline tuning)

```python
from telegram_bot.graph.config import GraphConfig

gc = GraphConfig.from_env()              ***REMOVED*** reads MAX_REWRITE_ATTEMPTS, SKIP_RERANK_THRESHOLD, etc.
llm = gc.create_llm()                    ***REMOVED*** langfuse.openai.AsyncOpenAI
hybrid = gc.create_hybrid_embeddings()   ***REMOVED*** BGEM3HybridEmbeddings (preferred)
sparse = gc.create_sparse_embeddings()   ***REMOVED*** BGEM3SparseEmbeddings
***REMOVED*** gc.skip_rerank_threshold (0.018), gc.relevance_threshold_rrf (0.005)
```

***REMOVED******REMOVED*** Cache Key Versioning

`CACHE_VERSION = "v5"` in `integrations/cache.py`. Key patterns:

| Pattern | Tier |
|---------|------|
| `sem:v5:bge1024` | Semantic cache |
| `embeddings:v5:{hash}` | Dense embeddings |
| `sparse:v5:{hash}` | Sparse embeddings |
| `search:v5:{hash}` | Search results |
| `conversation:{user_id}` | Chat history |

Bump version when changing models. Old keys expire naturally.

***REMOVED******REMOVED******REMOVED*** Kommo CRM Client (***REMOVED***413)

```python
from telegram_bot.services.kommo_client import KommoClient
from telegram_bot.services.kommo_token_store import KommoTokenStore

***REMOVED*** Token store — Redis-backed OAuth2 with auto-refresh (5-min buffer before expiry)
token_store = KommoTokenStore(redis=redis, subdomain="mycompany", client_id=..., client_secret=...)

***REMOVED*** Client — async httpx, auto-refresh on 401, all methods @observe-traced
kommo = KommoClient(subdomain="mycompany", token_store=token_store)
lead = await kommo.create_lead(LeadCreate(name="New deal", budget=50000))
contact = await kommo.upsert_contact("+1234567890", ContactCreate(first_name="John"))
await kommo.link_contact_to_lead(lead.id, contact.id)
await kommo.close()  ***REMOVED*** close httpx client
```

**Token init fallback (***REMOVED***678):** `bot.py` init chain: `KOMMO_AUTH_CODE` → `token_store.seed_env_token()` (seeds Redis from `KOMMO_ACCESS_TOKEN` env) → check existing Redis → disable. Env vars: `KOMMO_CLIENT_ID`, `KOMMO_CLIENT_SECRET`, `KOMMO_REDIRECT_URI`, `KOMMO_ACCESS_TOKEN`.

**get_valid_token() guard (***REMOVED***682):** Skips token refresh if `refresh_token` empty — returns `access_token` as-is. Prevents 401 errors on seeded tokens without refresh capability.

**Traced spans:** `kommo-create-lead`, `kommo-get-lead`, `kommo-update-lead`, `kommo-upsert-contact`, `kommo-get-contacts`, `kommo-add-note`, `kommo-create-task`, `kommo-link-contact`, `kommo-list-pipelines`

**Token seed fallback (***REMOVED***678, ***REMOVED***686):** Init chain order: `KOMMO_AUTH_CODE` present → exchange; else check Redis → tokens exist → proceed; else `KOMMO_ACCESS_TOKEN` set → `token_store.seed_env_token(token)` → proceed; else disable CRM. `seed_env_token()` stores access token with empty refresh_token and expires_at=0 so `get_valid_token()` returns it as-is (no refresh attempted).

***REMOVED******REMOVED******REMOVED*** CRM Services (***REMOVED***384, ***REMOVED***390)

```python
from telegram_bot.services.lead_scoring_store import LeadScoringStore
from telegram_bot.services.nurturing_service import NurturingService
from telegram_bot.services.funnel_analytics_service import FunnelAnalyticsService

***REMOVED*** Lead scoring — asyncpg, upsert with sync_status tracking
store = LeadScoringStore(pool=asyncpg_pool)
await store.upsert_score(user_id, score_record)
pending = await store.get_pending_sync()  ***REMOVED*** for Kommo sync

***REMOVED*** Nurturing — APScheduler v3 for batch scheduling
nurturing = NurturingService(...)
scheduler = NurturingScheduler(nurturing, interval_minutes=config.nurturing_interval)

***REMOVED*** Funnel — daily conversion/dropoff snapshots
funnel = FunnelAnalyticsService(store=FunnelAnalyticsStore(pool))
```

**DB tables:** `lead_scores`, `lead_score_sync_audit`, `nurturing_jobs`, `funnel_metrics_daily`, `scheduler_leases`

***REMOVED******REMOVED*** I/O Patterns

- **LangGraph nodes**: Async functions with `state: dict[str, Any]` signature
- **Services**: Async (`httpx.AsyncClient`, `AsyncQdrantClient` with gRPC, `AsyncOpenAI`)
- **Search Engines (src/retrieval)**: Sync Qdrant SDK for evaluation benchmarks
- **Redis**: Async pipelines for batch operations (`async with redis.pipeline()`)
- No blocking calls in async context for bot handlers

***REMOVED******REMOVED*** Apartments Domain (***REMOVED***632)

```
telegram_bot/services/
├── apartment_models.py           ***REMOVED*** ApartmentRecord, view normalization, confidence scoring
├── apartment_filter_extractor.py ***REMOVED*** Regex parser: rooms, price, complex, view, floor, area
├── apartments_service.py         ***REMOVED*** ApartmentsService — hybrid search with payload filtering
├── favorites_service.py          ***REMOVED*** User apartment favorites (asyncpg)
├── content_loader.py             ***REMOVED*** Services YAML config loader (cached)
```

**Two-stage routing:**
1. **Fast path** (0 LLM calls): `ApartmentFilterExtractor` → regex → payload-filtered hybrid search → direct response
2. **Agent escalation**: LOW confidence or special signals → agent with `apartment_search` @tool

**Qdrant:** Collection with 10 payload indexes. Top-level filters (no `metadata.` prefix). Payload: rooms, price_usd, complex_name, city, district, view, floor, area_m2, property_type, status.

**Scripts:** `scripts/apartments/ingest.py` (CSV → BGE-M3 → Qdrant), `scripts/apartments/setup_collection.py`

***REMOVED******REMOVED*** Hot Lead Notifier

`telegram_bot/services/hot_lead_notifier.py` — sends Telegram notifications to `MANAGER_IDS` when `lead_score >= MANAGER_HOT_LEAD_THRESHOLD` (default 60). Redis deduplication with TTL (default 3600s).

***REMOVED******REMOVED*** Session Summary Worker

`telegram_bot/services/session_summary.py` + `session_summary_worker.py` — LLM-generated structured CRM note from conversation dialog. Pydantic output schema. Async background processing.

***REMOVED******REMOVED*** Response Style Detector

`telegram_bot/services/response_style_detector.py` — zero-latency regex-based style/difficulty classifier. Determines response format (simple, detailed, structured) without LLM call. Used in `generate_response()`.
