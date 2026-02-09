---
paths: "telegram_bot/services/**/*.py, telegram_bot/integrations/**/*.py"
---

# Service & Integration Patterns

Code patterns for `telegram_bot/services/` and `telegram_bot/integrations/`.

## Directory Structure

```
telegram_bot/
├── services/              # Business logic services (LLM, search, preprocessing)
│   ├── llm.py             # LLMService (OpenAI SDK, langfuse.openai.AsyncOpenAI)
│   ├── query_analyzer.py  # QueryAnalyzer (LLM filter extraction, OpenAI SDK)
│   ├── query_preprocessor.py # HyDEGenerator + QueryPreprocessor
│   ├── query_router.py    # Legacy QueryType routing (4-type)
│   ├── filter_extractor.py # Regex filter extraction
│   ├── qdrant.py          ***REMOVED***Service (async, Qdrant SDK)
│   ├── colbert_reranker.py # ColbertRerankerService (BGE-M3 /rerank)
│   ├── voyage.py          ***REMOVED***Service (embeddings + rerank API)
│   ├── vectorizers.py     # UserBaseVectorizer + BgeM3CacheVectorizer
│   ├── cache.py           # Legacy CacheService (retained for reference)
│   ├── metrics.py         # PipelineMetrics (p50/p95 tracking)
│   ├── redis_monitor.py   # RedisHealthMonitor (background task)
│   └── retriever.py       # RetrieverService (sync, legacy)
├── integrations/          # LangGraph-compatible wrappers
│   ├── cache.py           # CacheLayerManager (6-tier, ~430 LOC)
│   ├── embeddings.py      # BGEM3Embeddings + BGEM3SparseEmbeddings (LangChain)
│   ├── langfuse.py        # create_langfuse_handler() for LangGraph callbacks
│   └── memory.py          # MemorySaver for conversation persistence
└── graph/                 # LangGraph pipeline
    ├── graph.py           # build_graph() — 9-node StateGraph assembly
    ├── state.py           # RAGState TypedDict + make_initial_state()
    ├── edges.py           # 3 routing functions
    ├── config.py          # GraphConfig (service factories)
    └── nodes/             # 8 node modules
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

### LangChain Embeddings (integrations)

```python
from telegram_bot.integrations.embeddings import BGEM3Embeddings, BGEM3SparseEmbeddings

emb = BGEM3Embeddings(base_url="http://bge-m3:8000")
vector = await emb.aembed_query("text")  # 1024-dim dense

sparse = BGEM3SparseEmbeddings(base_url="http://bge-m3:8000")
sv = await sparse.aembed_query("text")   # sparse dict
```

### CacheLayerManager (integrations)

```python
from telegram_bot.integrations.cache import CacheLayerManager

cache = CacheLayerManager(redis_url="redis://redis:6379")
await cache.initialize()
# CACHE_VERSION = "v3", keys: {tier}:v3:{hash}
```

### BotConfig (pydantic-settings)

```python
from telegram_bot.config import BotConfig

config = BotConfig()  # Reads from .env + env vars via AliasChoices
# config.telegram_token, config.llm_base_url, config.domain, etc.
```

### GraphConfig (service factories)

```python
from telegram_bot.graph.config import GraphConfig

gc = GraphConfig.from_env()
llm = gc.create_llm()                    # ChatLiteLLM
emb = gc.create_embeddings()             # BGEM3Embeddings
sparse = gc.create_sparse_embeddings()   # BGEM3SparseEmbeddings
```

## Cache Key Versioning

`CACHE_VERSION = "v3"` in `integrations/cache.py`. Key patterns:

| Pattern | Tier |
|---------|------|
| `sem:v3:bge1024` | Semantic cache |
| `embeddings:v3:{hash}` | Dense embeddings |
| `sparse:v3:{hash}` | Sparse embeddings |
| `search:v3:{hash}` | Search results |
| `conversation:{user_id}` | Chat history |

Bump version when changing models. Old keys expire naturally.

## I/O Patterns

- **LangGraph nodes**: Async functions with `state: dict[str, Any]` signature
- **Services**: Async (`httpx.AsyncClient`, `AsyncQdrantClient`, `AsyncOpenAI`)
- **Search Engines (src/retrieval)**: Sync Qdrant SDK for evaluation benchmarks
- No blocking calls in async context for bot handlers
