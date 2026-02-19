---
paths: "telegram_bot/services/**/*.py, telegram_bot/integrations/**/*.py"
---

# Service & Integration Patterns

Code patterns for `telegram_bot/services/` and `telegram_bot/integrations/`.

## Directory Structure

```
telegram_bot/
├── bot.py                 # PropertyBot (~300 LOC, LangGraph orchestrator + score writing)
├── config.py              # BotConfig (pydantic-settings BaseSettings)
├── observability.py       # Langfuse init, @observe decorator, PII masking
├── preflight.py           # Health checks (Redis, Qdrant, BGE-M3, LiteLLM)
├── services/              # Business logic services (LLM, search, preprocessing)
│   ├── llm.py             # LLMService (OpenAI SDK, langfuse.openai.AsyncOpenAI)
│   ├── query_analyzer.py  # QueryAnalyzer (LLM filter extraction, OpenAI SDK)
│   ├── query_preprocessor.py # HyDEGenerator + QueryPreprocessor
│   ├── filter_extractor.py # Regex filter extraction
│   ├── qdrant.py          # QdrantService (async, gRPC, batch_search_rrf, group_by)
│   ├── bge_m3_client.py   # BGEM3Client (async) + BGEM3SyncClient — unified SDK for all BGE-M3 endpoints
│   ├── colbert_reranker.py # ColbertRerankerService (uses BGEM3Client)
│   ├── voyage.py          # VoyageService (embeddings + rerank API)
│   ├── vectorizers.py     # UserBaseVectorizer + BgeM3CacheVectorizer (uses BGEM3Client)
│   ├── metrics.py         # PipelineMetrics (p50/p95 tracking)
│   ├── redis_monitor.py   # RedisHealthMonitor (background task)
│   ├── kommo_client.py        # KommoClient (async httpx, OAuth2 auto-refresh)
│   ├── kommo_token_store.py   # KommoTokenStore (Redis hash, OAuth2 token mgmt)
│   ├── kommo_models.py        # Pydantic v2: Lead, Contact, Note, Task, Pipeline, *Create, *Update
│   ├── lead_scoring_models.py  # LeadScoreRecord, LeadScoreSyncPayload
│   ├── lead_scoring_store.py   # LeadScoringStore (asyncpg upsert, pending sync queue)
│   ├── funnel_analytics_store.py   # FunnelAnalyticsStore (daily metrics)
│   ├── funnel_analytics_service.py # FunnelAnalyticsService
│   ├── nurturing_service.py    # NurturingService
│   └── nurturing_scheduler.py  # NurturingScheduler (APScheduler v3)
├── integrations/          # LangGraph-compatible wrappers
│   ├── cache.py           # CacheLayerManager (6-tier, Redis pipelines, ~430 LOC)
│   ├── embeddings.py      # BGEM3HybridEmbeddings (uses BGEM3Client) + legacy wrappers
│   ├── event_stream.py    # EventStream for graph→bot communication
│   ├── langfuse.py        # (legacy) Langfuse callback handler — replaced by @observe
│   ├── memory.py          # MemorySaver for conversation persistence
│   └── prompt_manager.py  # Langfuse Prompt Management with fallback templates
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
from telegram_bot.integrations.prompt_manager import get_prompt

# Fetches prompt from Langfuse with fallback to hardcoded template
# Pre-checks via API probe → caches missing/known status with TTL → no SDK warning logs
prompt = get_prompt(name="rag-system", fallback="You are...", variables={"domain": "real estate"})
```

Flow: `_probe_prompt_available()` (API) → TTL cache hit/miss → `client.get_prompt()` (SDK) or fallback.
Missing prompts cached 300s to avoid repeated API calls and SDK `generate-label:production` warnings.

### GraphConfig (service factories + pipeline tuning)

```python
from telegram_bot.graph.config import GraphConfig

gc = GraphConfig.from_env()              # reads MAX_REWRITE_ATTEMPTS, SKIP_RERANK_THRESHOLD, etc.
llm = gc.create_llm()                    # langfuse.openai.AsyncOpenAI
hybrid = gc.create_hybrid_embeddings()   # BGEM3HybridEmbeddings (preferred)
sparse = gc.create_sparse_embeddings()   # BGEM3SparseEmbeddings
# gc.skip_rerank_threshold (0.012), gc.relevance_threshold_rrf (0.005)
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

**Traced spans:** `kommo-create-lead`, `kommo-get-lead`, `kommo-update-lead`, `kommo-upsert-contact`, `kommo-get-contacts`, `kommo-add-note`, `kommo-create-task`, `kommo-link-contact`, `kommo-list-pipelines`

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
