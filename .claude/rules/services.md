---
paths: "telegram_bot/services/**/*.py, telegram_bot/integrations/**/*.py"
---

***REMOVED*** Service & Integration Patterns

Code patterns for `telegram_bot/services/` and `telegram_bot/integrations/`.

***REMOVED******REMOVED*** Directory Structure

```
telegram_bot/
├── services/              ***REMOVED*** Business logic services (LLM, search, preprocessing)
│   ├── llm.py             ***REMOVED*** LLMService (OpenAI SDK, langfuse.openai.AsyncOpenAI)
│   ├── query_analyzer.py  ***REMOVED*** QueryAnalyzer (LLM filter extraction, OpenAI SDK)
│   ├── query_preprocessor.py ***REMOVED*** HyDEGenerator + QueryPreprocessor
│   ├── query_router.py    ***REMOVED*** Legacy QueryType routing (4-type)
│   ├── filter_extractor.py ***REMOVED*** Regex filter extraction
│   ├── qdrant.py          ***REMOVED*** QdrantService (async, Qdrant SDK)
│   ├── colbert_reranker.py ***REMOVED*** ColbertRerankerService (BGE-M3 /rerank)
│   ├── voyage.py          ***REMOVED*** VoyageService (embeddings + rerank API)
│   ├── vectorizers.py     ***REMOVED*** UserBaseVectorizer + BgeM3CacheVectorizer
│   ├── cache.py           ***REMOVED*** Legacy CacheService (retained for reference)
│   ├── metrics.py         ***REMOVED*** PipelineMetrics (p50/p95 tracking)
│   ├── redis_monitor.py   ***REMOVED*** RedisHealthMonitor (background task)
│   └── retriever.py       ***REMOVED*** RetrieverService (sync, legacy)
├── integrations/          ***REMOVED*** LangGraph-compatible wrappers
│   ├── cache.py           ***REMOVED*** CacheLayerManager (6-tier, ~430 LOC)
│   ├── embeddings.py      ***REMOVED*** BGEM3Embeddings + BGEM3SparseEmbeddings (LangChain)
│   ├── langfuse.py        ***REMOVED*** create_langfuse_handler() for LangGraph callbacks
│   └── memory.py          ***REMOVED*** MemorySaver for conversation persistence
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

***REMOVED******REMOVED******REMOVED*** CacheLayerManager (integrations)

```python
from telegram_bot.integrations.cache import CacheLayerManager

cache = CacheLayerManager(redis_url="redis://redis:6379")
await cache.initialize()
***REMOVED*** CACHE_VERSION = "v3", keys: {tier}:v3:{hash}
```

***REMOVED******REMOVED******REMOVED*** BotConfig (pydantic-settings)

```python
from telegram_bot.config import BotConfig

config = BotConfig()  ***REMOVED*** Reads from .env + env vars via AliasChoices
***REMOVED*** config.telegram_token, config.llm_base_url, config.domain, etc.
```

***REMOVED******REMOVED******REMOVED*** GraphConfig (service factories)

```python
from telegram_bot.graph.config import GraphConfig

gc = GraphConfig.from_env()
llm = gc.create_llm()                    ***REMOVED*** ChatLiteLLM
emb = gc.create_embeddings()             ***REMOVED*** BGEM3Embeddings
sparse = gc.create_sparse_embeddings()   ***REMOVED*** BGEM3SparseEmbeddings
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
- **Services**: Async (`httpx.AsyncClient`, `AsyncQdrantClient`, `AsyncOpenAI`)
- **Search Engines (src/retrieval)**: Sync Qdrant SDK for evaluation benchmarks
- No blocking calls in async context for bot handlers
