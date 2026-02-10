---
paths: "telegram_bot/services/**/*.py, telegram_bot/integrations/**/*.py"
---

***REMOVED*** Service & Integration Patterns

Code patterns for `telegram_bot/services/` and `telegram_bot/integrations/`.

***REMOVED******REMOVED*** Directory Structure

```
telegram_bot/
├── bot.py                 ***REMOVED*** PropertyBot (~260 LOC, LangGraph pipeline + score writing)
├── config.py              ***REMOVED*** BotConfig (pydantic-settings BaseSettings)
├── observability.py       ***REMOVED*** Langfuse init, @observe decorator, PII masking
├── preflight.py           ***REMOVED*** Health checks (Redis, Qdrant, BGE-M3, LiteLLM)
├── services/              ***REMOVED*** Business logic services (LLM, search, preprocessing)
│   ├── llm.py             ***REMOVED*** LLMService (OpenAI SDK, langfuse.openai.AsyncOpenAI)
│   ├── query_analyzer.py  ***REMOVED*** QueryAnalyzer (LLM filter extraction, OpenAI SDK)
│   ├── query_preprocessor.py ***REMOVED*** HyDEGenerator + QueryPreprocessor
│   ├── filter_extractor.py ***REMOVED*** Regex filter extraction
│   ├── qdrant.py          ***REMOVED*** QdrantService (async, gRPC, batch_search_rrf, group_by)
│   ├── colbert_reranker.py ***REMOVED*** ColbertRerankerService (BGE-M3 /rerank)
│   ├── voyage.py          ***REMOVED*** VoyageService (embeddings + rerank API)
│   ├── vectorizers.py     ***REMOVED*** UserBaseVectorizer + BgeM3CacheVectorizer
│   ├── metrics.py         ***REMOVED*** PipelineMetrics (p50/p95 tracking)
│   └── redis_monitor.py   ***REMOVED*** RedisHealthMonitor (background task)
├── integrations/          ***REMOVED*** LangGraph-compatible wrappers
│   ├── cache.py           ***REMOVED*** CacheLayerManager (6-tier, Redis pipelines, ~430 LOC)
│   ├── embeddings.py      ***REMOVED*** BGEM3Embeddings + BGEM3SparseEmbeddings (LangChain)
│   ├── event_stream.py    ***REMOVED*** EventStream for graph→bot communication
│   ├── langfuse.py        ***REMOVED*** (legacy) Langfuse callback handler — replaced by @observe
│   ├── memory.py          ***REMOVED*** MemorySaver for conversation persistence
│   └── prompt_manager.py  ***REMOVED*** Langfuse Prompt Management with fallback templates
└── graph/                 ***REMOVED*** LangGraph pipeline
    ├── graph.py           ***REMOVED*** build_graph() — 9-node StateGraph assembly
    ├── state.py           ***REMOVED*** RAGState TypedDict + make_initial_state()
    ├── edges.py           ***REMOVED*** 3 routing functions
    ├── config.py          ***REMOVED*** GraphConfig (service factories)
    └── nodes/             ***REMOVED*** 8 node modules
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

***REMOVED******REMOVED******REMOVED*** LangChain Embeddings (integrations)

```python
from telegram_bot.integrations.embeddings import BGEM3Embeddings, BGEM3SparseEmbeddings

emb = BGEM3Embeddings(base_url="http://bge-m3:8000")
vector = await emb.aembed_query("text")  ***REMOVED*** 1024-dim dense

sparse = BGEM3SparseEmbeddings(base_url="http://bge-m3:8000")
sv = await sparse.aembed_query("text")   ***REMOVED*** sparse dict
```

***REMOVED******REMOVED******REMOVED*** QdrantService (gRPC + batch)

```python
from telegram_bot.services.qdrant import QdrantService

***REMOVED*** Uses prefer_grpc=True for faster connections
qdrant = QdrantService(url="http://localhost:6333", collection_name="gdrive_documents_bge")

***REMOVED*** Single hybrid search
results = await qdrant.hybrid_search_rrf(dense_vector=emb, sparse_vector=sparse, top_k=20)

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
***REMOVED*** CACHE_VERSION = "v3", keys: {tier}:v3:{hash}
***REMOVED*** Uses async Redis pipelines for batch operations (1 round-trip)
```

***REMOVED******REMOVED******REMOVED*** Prompt Manager (Langfuse)

```python
from telegram_bot.integrations.prompt_manager import get_prompt

***REMOVED*** Fetches prompt from Langfuse with fallback to hardcoded template
prompt = get_prompt(name="rag-system", fallback="You are...", variables={"domain": "real estate"})
```

***REMOVED******REMOVED******REMOVED*** GraphConfig (service factories + pipeline tuning)

```python
from telegram_bot.graph.config import GraphConfig

gc = GraphConfig.from_env()              ***REMOVED*** reads MAX_REWRITE_ATTEMPTS, REWRITE_MAX_TOKENS, etc.
llm = gc.create_llm()                    ***REMOVED*** langfuse.openai.AsyncOpenAI
emb = gc.create_embeddings()             ***REMOVED*** BGEM3Embeddings
sparse = gc.create_sparse_embeddings()   ***REMOVED*** BGEM3SparseEmbeddings
***REMOVED*** gc.max_rewrite_attempts (default 1), gc.rewrite_max_tokens (default 64)
```

***REMOVED******REMOVED*** Cache Key Versioning

`CACHE_VERSION = "v3"` in `integrations/cache.py`. Key patterns:

| Pattern | Tier |
|---------|------|
| `sem:v3:bge1024` | Semantic cache |
| `embeddings:v3:{hash}` | Dense embeddings |
| `sparse:v3:{hash}` | Sparse embeddings |
| `search:v3:{hash}` | Search results |
| `conversation:{user_id}` | Chat history |

Bump version when changing models. Old keys expire naturally.

***REMOVED******REMOVED*** I/O Patterns

- **LangGraph nodes**: Async functions with `state: dict[str, Any]` signature
- **Services**: Async (`httpx.AsyncClient`, `AsyncQdrantClient` with gRPC, `AsyncOpenAI`)
- **Search Engines (src/retrieval)**: Sync Qdrant SDK for evaluation benchmarks
- **Redis**: Async pipelines for batch operations (`async with redis.pipeline()`)
- No blocking calls in async context for bot handlers
