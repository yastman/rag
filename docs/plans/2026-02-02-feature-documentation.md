# Feature Documentation System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create `.claude/rules/features/` documentation system with auto-loading via `paths:` frontmatter so Claude Code automatically receives feature context.

**Architecture:** 9 markdown files in `.claude/rules/features/`, each with YAML frontmatter specifying glob patterns. When user works with matching files, Claude loads relevant documentation automatically.

**Tech Stack:** Markdown, YAML frontmatter, Claude Code rules system

---

## Task 1: Create Directory Structure

**Files:**
- Create: `.claude/rules/features/` (directory)

**Step 1: Create features directory**

```bash
mkdir -p .claude/rules/features
```

**Step 2: Verify directory exists**

Run: `ls -la .claude/rules/`
Expected: `features/` directory listed

**Step 3: Commit**

```bash
git add .claude/rules/features/.gitkeep 2>/dev/null || touch .claude/rules/features/.gitkeep && git add .claude/rules/features/.gitkeep
git commit -m "chore: create features documentation directory"
```

---

## Task 2: Write caching.md

**Files:**
- Create: `.claude/rules/features/caching.md`

**Step 1: Create caching.md**

```markdown
---
paths: "**/cache*.py, src/cache/**"
---

# Caching System

6-tier caching system for RAG pipeline optimization.

## Purpose

Reduce API calls, latency, and costs by caching at multiple levels:
- Semantic cache for LLM responses
- Embeddings cache for query vectors
- Search results cache
- Rerank results cache
- QueryAnalyzer results cache
- Sparse embeddings cache

## Architecture

```
Query → SemanticCache check → [HIT: return cached]
                           → [MISS: Embeddings → Search → Rerank → LLM → cache result]
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/cache.py` | 33 | CacheService main class |
| `telegram_bot/services/cache.py` | 30 | CACHE_SCHEMA_VERSION |
| `src/cache/redis_semantic_cache.py` | - | Legacy implementation |

## Cache Tiers

| Tier | Cache Type | TTL | Key Pattern |
|------|------------|-----|-------------|
| 1 | Semantic (LLM responses) | 48h | `sem:v2:{vectorizer_id}` |
| 1 | Embeddings (query vectors) | 7d | `emb:v2:{hash}` |
| 2 | QueryAnalyzer results | 24h | `analysis:v2:{hash}` |
| 2 | Search results | 2h | `search:v2:{index_ver}:{hash}` |
| 2 | Rerank results | 2h | `rerank:v2:{hash}` |
| 2 | Sparse embeddings | 7d | `sparse:v2:{model}:{hash}` |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `semantic_cache_ttl` | 48h | LLM response cache lifetime |
| `embeddings_cache_ttl` | 7d | Query embedding cache lifetime |
| `distance_threshold` | 0.20 | Cosine distance for semantic match (lower = stricter) |
| `CACHE_SCHEMA_VERSION` | "v2" | Bump when changing models |

## Distance Thresholds

| Query Type | Threshold | Similarity |
|------------|-----------|------------|
| Exact (IDs, corpus) | 0.05 | 95% required |
| Semantic (general) | 0.10 | 90% required |

## How It Works

1. **Initialize:** `CacheService(redis_url)` connects to Redis
2. **Check semantic cache:** Query embedding → Redis vector search
3. **On HIT:** Return cached response (optionally personalize via CESC)
4. **On MISS:** Full RAG pipeline → store result with TTL

## Common Patterns

### Check semantic cache

```python
from telegram_bot.services.cache import CacheService

cache = CacheService(redis_url="redis://localhost:6379")
await cache.initialize(vectorizer)  # Pass embedding function

# Check cache
cached = await cache.check_semantic_cache(query, threshold=0.10)
if cached:
    return cached["response"]
```

### Store in cache

```python
await cache.store_semantic_cache(
    query=query,
    response=llm_response,
    metadata={"query_type": "semantic"}
)
```

### Version bumping

When changing embedding models:

```python
# telegram_bot/services/cache.py:30
CACHE_SCHEMA_VERSION = "v3"  # Was "v2"
```

Old keys expire naturally via TTL.

## Dependencies

- Container: `dev-redis` (6379)
- Library: `redisvl` (lazy-loaded to avoid 7.5s import)

## Testing

```bash
pytest tests/unit/test_cache.py -v
pytest tests/unit/test_semantic_cache.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Redis connection refused` | `docker compose -f docker-compose.dev.yml up -d redis` |
| Cache pollution after model change | Bump `CACHE_SCHEMA_VERSION` |
| False positive hits | Lower `distance_threshold` |
| High miss rate | Raise `distance_threshold` or increase TTL |

## Development Guide

### Adding new cache tier

1. Add TTL parameter to `CacheService.__init__`
2. Add key pattern constant (e.g., `NEW_CACHE_PREFIX = "new:v2:"`)
3. Implement `check_new_cache()` and `store_new_cache()` methods
4. Add metrics tracking in `self.metrics["new"]`
5. Write tests in `tests/unit/test_cache.py`

### Monitoring cache effectiveness

```python
# Get hit/miss stats
stats = cache.get_metrics()
# {"semantic": {"hits": 42, "misses": 18}, ...}
```
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/caching.md`
Expected: YAML frontmatter with `paths:` visible

**Step 3: Commit**

```bash
git add .claude/rules/features/caching.md
git commit -m "docs(features): add caching system documentation"
```

---

## Task 3: Write search-retrieval.md

**Files:**
- Create: `.claude/rules/features/search-retrieval.md`

**Step 1: Create search-retrieval.md**

```markdown
---
paths: "src/retrieval/**, **/qdrant*.py, **/retriever*.py"
---

# Search & Retrieval

Hybrid search with RRF fusion, Qdrant vector database, and reranking.

## Purpose

Retrieve relevant documents using combination of dense (semantic) and sparse (keyword) vectors with intelligent fusion and reranking.

## Architecture

```
Query → Dense Embedding (Voyage) + Sparse Embedding (BM42)
     → Qdrant Prefetch (dense + sparse)
     → RRF Fusion
     → [Optional] Voyage Rerank
     → Results
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `src/retrieval/search_engines.py` | 56 | BaseSearchEngine ABC |
| `src/retrieval/search_engines.py` | 78 | BaselineSearchEngine |
| `telegram_bot/services/qdrant.py` | 19 | QdrantService (async) |
| `telegram_bot/services/retriever.py` | 12 | RetrieverService (sync, legacy) |

## Search Engine Variants

| Engine | Recall@1 | Latency | Description |
|--------|----------|---------|-------------|
| HybridRRFColBERT | 94% | ~1.0s | Dense + Sparse + ColBERT (default) |
| DBSFColBERT | 91% | ~0.7s | 7% faster variant |
| HybridRRF | 92% | ~0.8s | Without ColBERT |
| Baseline | 91.3% | ~0.65s | Dense only |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dense_weight` | 0.6 | RRF weight for dense vectors |
| `sparse_weight` | 0.4 | RRF weight for sparse vectors |
| `prefetch_multiplier` | 3 | Overfetch ratio for RRF |
| `use_quantization` | true | Enable Binary Quantization |

## RRF Weights by Query Type

| Query Type | Dense | Sparse | Example |
|------------|-------|--------|---------|
| Semantic | 0.6 | 0.4 | "уютная квартира с видом" |
| Exact | 0.2 | 0.8 | "корпус 5", "ID 12345" |

## Common Patterns

### Hybrid search with RRF

```python
from telegram_bot.services.qdrant import QdrantService

qdrant = QdrantService(
    url="http://localhost:6333",
    collection_name="contextual_bulgaria_voyage",
)

results = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,      # From VoyageService
    sparse_vector=sparse_embedding,    # From BM42
    filters={"city": "Несебр"},
    top_k=10,
    dense_weight=0.6,
    sparse_weight=0.4,
)
```

### Qdrant SDK nested prefetch (sync)

```python
from qdrant_client import models

response = client.query_points(
    collection_name="documents",
    prefetch=[
        models.Prefetch(query=dense_vector, using="dense", limit=100),
        models.Prefetch(query=sparse_vector, using="bm42", limit=100),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=top_k,
)
```

### Score boosting (freshness)

```python
results = await qdrant.search_with_score_boosting(
    dense_vector=query_embedding,
    freshness_boost=True,
    freshness_field="created_at",
    freshness_scale_days=7,
)
```

### MMR diversity reranking

```python
diverse_results = qdrant.mmr_rerank(
    points=results,
    embeddings=result_embeddings,
    lambda_mult=0.5,  # 0=diversity, 1=relevance
    top_k=5,
)
```

## Filter Building

```python
# Exact match
filters = {"city": "Несебр"}

# Range filter
filters = {"price": {"gte": 50000, "lte": 100000}}

# Combined
filters = {
    "city": "Бургас",
    "rooms": 2,
    "price": {"lt": 80000}
}
```

## Binary Quantization

Enabled by default for 40x faster search, 75% less RAM:

```python
# Disable for A/B testing
results = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,
    quantization_ignore=True,  # Use full vectors
)
```

## Dependencies

- Container: `dev-qdrant` (6333, 6334 gRPC)
- Collections: `contextual_bulgaria_voyage`, `legal_documents`

## Testing

```bash
pytest tests/unit/test_qdrant_service.py -v
pytest tests/unit/test_search_engines.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Qdrant timeout` | Enable `use_quantization=True` |
| Low recall | Check embedding model matches collection |
| Empty results | Verify collection name, check filters |

## Development Guide

### Adding new search engine

1. Create class in `src/retrieval/search_engines.py`
2. Inherit from `BaseSearchEngine`
3. Implement `search()` and `get_name()` methods
4. Add to `SearchEngine` enum in `src/config/settings.py`
5. Write benchmark in `src/evaluation/`
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/search-retrieval.md`
Expected: YAML frontmatter with `paths:` visible

**Step 3: Commit**

```bash
git add .claude/rules/features/search-retrieval.md
git commit -m "docs(features): add search and retrieval documentation"
```

---

## Task 4: Write query-processing.md

**Files:**
- Create: `.claude/rules/features/query-processing.md`

**Step 1: Create query-processing.md**

```markdown
---
paths: "**/query*.py, **/filter*.py"
---

# Query Processing

Query routing, analysis, preprocessing, and filter extraction.

## Purpose

Classify queries to skip unnecessary RAG steps, extract structured filters, and normalize text for optimal search.

## Architecture

```
Query → QueryRouter (CHITCHAT/SIMPLE/COMPLEX)
     → [CHITCHAT: canned response, skip RAG]
     → [SIMPLE: light RAG, skip rerank]
     → [COMPLEX: full RAG + rerank]
     → QueryPreprocessor (translit, weights)
     → QueryAnalyzer (LLM filter extraction)
     → Search with filters
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/query_router.py` | 17 | QueryType enum |
| `telegram_bot/services/query_router.py` | 107 | classify_query() |
| `telegram_bot/services/query_analyzer.py` | 14 | QueryAnalyzer (LLM) |
| `telegram_bot/services/query_preprocessor.py` | 11 | QueryPreprocessor |
| `telegram_bot/services/filter_extractor.py` | 7 | FilterExtractor (regex) |

## Query Types

| Type | Action | Example |
|------|--------|---------|
| CHITCHAT | Skip RAG, return canned response | "Привет!", "Спасибо" |
| SIMPLE | Light RAG, skip rerank | "сколько стоит", "2 комнаты" |
| COMPLEX | Full RAG + rerank | "уютная квартира с видом на море" |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| Chitchat patterns | 30+ regex | Greetings, thanks, farewells |
| Simple patterns | 5+ regex | Price, room queries |
| Translit map | 20+ cities | Latin → Cyrillic |

## Common Patterns

### Query routing

```python
from telegram_bot.services.query_router import classify_query, QueryType, get_chitchat_response

query_type = classify_query(query)

if query_type == QueryType.CHITCHAT:
    response = get_chitchat_response(query)
    return response  # Skip RAG entirely

if query_type == QueryType.SIMPLE:
    # Light RAG, skip rerank
    pass
```

### Query preprocessing

```python
from telegram_bot.services.query_preprocessor import QueryPreprocessor

pp = QueryPreprocessor()
result = pp.analyze("apartments in Sunny Beach корпус 5")
# {
#   "original_query": "apartments in Sunny Beach корпус 5",
#   "normalized_query": "apartments in Солнечный берег корпус 5",
#   "rrf_weights": {"dense": 0.2, "sparse": 0.8},
#   "cache_threshold": 0.05,
#   "is_exact": True
# }
```

### LLM filter extraction

```python
from telegram_bot.services.query_analyzer import QueryAnalyzer

analyzer = QueryAnalyzer(api_key=key, base_url=url)
result = await analyzer.analyze("квартира до 80000 евро в Несебре")
# {
#   "filters": {"price": {"lt": 80000}, "city": "Несебр"},
#   "semantic_query": "квартира"
# }
```

### Regex filter extraction (fallback)

```python
from telegram_bot.services.filter_extractor import FilterExtractor

extractor = FilterExtractor()
filters = extractor.extract_filters("2-комнатная до 100к")
# {"rooms": 2, "price": {"lt": 100000}}
```

## Available Filters

| Filter | Type | Example |
|--------|------|---------|
| `price` | range | `{"lt": 100000}`, `{"gte": 50000, "lte": 80000}` |
| `rooms` | int | `2` |
| `city` | string | `"Несебр"` |
| `area` | range | `{"gte": 50}` |
| `floor` | int | `4` |
| `distance_to_sea` | range | `{"lte": 500}` |
| `maintenance` | range | `{"lte": 12.0}` |
| `bathrooms` | int | `2` |
| `furniture` | string | `"Есть"` |
| `year_round` | string | `"Да"` |

## Transliteration Map

| Latin | Cyrillic |
|-------|----------|
| Sunny Beach | Солнечный берег |
| Nesebar | Несебър |
| Burgas | Бургас |
| Sveti Vlas | Святой Влас |

## Rerank Decision

```python
from telegram_bot.services.query_router import needs_rerank

if needs_rerank(query_type, result_count):
    results = await voyage.rerank(query, results)
```

Skip rerank when:
- `query_type == SIMPLE`
- `result_count <= 2`

## Dependencies

- LLM: via LiteLLM for QueryAnalyzer
- Langfuse: @observe decorators

## Testing

```bash
pytest tests/unit/test_query_router.py -v
pytest tests/unit/test_query_analyzer.py -v
pytest tests/unit/test_query_preprocessor.py -v
pytest tests/unit/test_filter_extractor.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Chitchat not detected | Add pattern to CHITCHAT_PATTERNS |
| Wrong translit | Add to TRANSLIT_MAP |
| LLM filter extraction failed | Falls back to regex extractor |

## Development Guide

### Adding new chitchat pattern

```python
# telegram_bot/services/query_router.py
CHITCHAT_PATTERNS = [
    ...
    r"^new pattern\b",  # Add here
]
```

### Adding new filter

1. Add to QueryAnalyzer system prompt
2. Add extraction method to FilterExtractor
3. Add to Qdrant filter building
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/query-processing.md`
Expected: YAML frontmatter visible

**Step 3: Commit**

```bash
git add .claude/rules/features/query-processing.md
git commit -m "docs(features): add query processing documentation"
```

---

## Task 5: Write embeddings.md

**Files:**
- Create: `.claude/rules/features/embeddings.md`

**Step 1: Create embeddings.md**

```markdown
---
paths: "**/embed*.py, **/vector*.py, **/voyage*.py, services/bge-m3-api/**, services/bm42/**, services/user-base/**"
---

# Embeddings

Voyage AI, USER-base, BGE-M3, and BM42 embedding services.

## Purpose

Generate dense and sparse embeddings for semantic search and caching.

## Architecture

```
Document Indexing: Voyage voyage-4-large (1024-dim) + BM42 sparse
Query Embedding:   Voyage voyage-4-lite (1024-dim) + BM42 sparse
Semantic Cache:    USER-base (768-dim, Russian optimized)
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/voyage.py` | 26 | VoyageService class |
| `telegram_bot/services/vectorizers.py` | 18 | UserBaseVectorizer |
| `services/bge-m3-api/app.py` | 41 | BGE-M3 FastAPI endpoints |
| `services/bm42/main.py` | 22 | BM42 FastAPI service |
| `services/user-base/main.py` | 20 | USER-base FastAPI service |

## Embedding Models

| Model | Dim | Use Case | Container |
|-------|-----|----------|-----------|
| voyage-4-large | 1024 | Document indexing | API |
| voyage-4-lite | 1024 | Query embedding | API |
| deepvk/USER-base | 768 | Russian semantic cache | dev-user-base:8003 |
| BGE-M3 | 1024 | Dense + sparse + ColBERT | dev-bge-m3:8000 |
| BM42 | sparse | Keyword matching | dev-bm42:8002 |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `VOYAGE_BATCH_SIZE` | 128 | Texts per API request |
| `MATRYOSHKA_DIMS` | (2048,1024,512,256) | Available dimensions |
| Retry attempts | 6 | With exponential backoff |

## Common Patterns

### VoyageService (recommended)

```python
from telegram_bot.services.voyage import VoyageService

service = VoyageService(
    api_key=api_key,
    model_docs="voyage-4-large",    # For indexing
    model_queries="voyage-4-lite",  # For queries (asymmetric)
    model_rerank="rerank-2.5",
)

# Async (recommended)
query_vec = await service.embed_query("search text")
doc_vecs = await service.embed_documents(["doc1", "doc2"])
results = await service.rerank("query", documents, top_k=5)

# Sync wrappers
query_vec = service.embed_query_sync("search text")
```

### UserBaseVectorizer (Russian cache)

```python
from telegram_bot.services.vectorizers import UserBaseVectorizer

vectorizer = UserBaseVectorizer(base_url="http://localhost:8003")

# Async
embedding = await vectorizer.aembed("двухкомнатная квартира")

# Sync
embedding = vectorizer.embed("двухкомнатная квартира")
```

### BGE-M3 API (hybrid)

```python
import httpx

async with httpx.AsyncClient() as client:
    # Dense only
    resp = await client.post("http://localhost:8000/encode/dense",
        json={"texts": ["text"]})
    dense = resp.json()["dense_vecs"]

    # Sparse only
    resp = await client.post("http://localhost:8000/encode/sparse",
        json={"texts": ["text"]})
    sparse = resp.json()["lexical_weights"]

    # All three (most efficient)
    resp = await client.post("http://localhost:8000/encode/hybrid",
        json={"texts": ["text"]})
    result = resp.json()  # dense_vecs, lexical_weights, colbert_vecs
```

### BM42 sparse

```python
resp = await client.post("http://localhost:8002/embed",
    json={"text": "search query"})
sparse = resp.json()  # {"indices": [...], "values": [...]}
```

## Asymmetric Retrieval

Documents indexed with `voyage-4-large` (high quality, one-time cost).
Queries embedded with `voyage-4-lite` (fast, cheap, continuous).
Both share embedding space → compatible for search.

## Matryoshka Embeddings

Voyage-4 supports variable dimensions:

```python
# Lower dimensions for faster search
embedding = await service.embed_query(text, output_dimension=512)
```

## Dependencies

| Container | Port | RAM | Purpose |
|-----------|------|-----|---------|
| dev-bge-m3 | 8000 | 4GB | Dense + sparse + ColBERT |
| dev-bm42 | 8002 | 1GB | BM42 sparse |
| dev-user-base | 8003 | 2GB | Russian semantic |

## Testing

```bash
pytest tests/unit/test_voyage_service.py -v
pytest tests/unit/test_vectorizers.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Voyage API 429` | Use CacheService, add delays |
| `Connection refused :8003` | `docker compose up -d user-base` |
| Slow BGE-M3 | Check OMP_NUM_THREADS=4 |

## Development Guide

### Adding new embedding model

1. Create FastAPI service in `services/new-model/`
2. Add Dockerfile with model pre-download
3. Add to `docker-compose.dev.yml`
4. Create client class in `telegram_bot/services/`
5. Add tests
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/embeddings.md`
Expected: YAML frontmatter visible

**Step 3: Commit**

```bash
git add .claude/rules/features/embeddings.md
git commit -m "docs(features): add embeddings documentation"
```

---

## Task 6: Write llm-integration.md

**Files:**
- Create: `.claude/rules/features/llm-integration.md`

**Step 1: Create llm-integration.md**

```markdown
---
paths: "**/llm*.py, docker/litellm/**, src/contextualization/**"
---

# LLM Integration

LiteLLM proxy, model routing, fallbacks, and answer generation.

## Purpose

Route LLM requests through LiteLLM proxy with automatic fallback chain and observability.

## Architecture

```
Bot → LLMService → LiteLLM Proxy (:4000) → Cerebras/Groq/OpenAI
                                        → Langfuse OTEL tracing
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `docker/litellm/config.yaml` | 1 | Model list, router settings |
| `telegram_bot/services/llm.py` | 15 | LLMService class |
| `src/contextualization/base.py` | - | BaseContextualizer |
| `src/contextualization/openai.py` | - | OpenAI implementation |

## Model Routing

| Model Name | Provider | Actual Model |
|------------|----------|--------------|
| `gpt-4o-mini` | Cerebras | zai-glm-4.7 (primary) |
| `gpt-4o-mini-fallback` | Groq | llama-3.1-70b |
| `gpt-4o-mini-openai` | OpenAI | gpt-4o-mini |

## Fallback Chain

```
Cerebras → [error] → Groq → [error] → OpenAI
```

Configured in `docker/litellm/config.yaml`:

```yaml
router_settings:
  fallbacks:
    - gpt-4o-mini: [gpt-4o-mini-fallback, gpt-4o-mini-openai]
  retry_policy:
    retry_count: 2
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LLM_BASE_URL` | http://litellm:4000 | LiteLLM proxy URL |
| `LLM_MODEL` | gpt-4o-mini | Model alias |
| `max_tokens` | 1024 | Response length limit |
| `temperature` | 0.0 | For deterministic responses |

## Common Patterns

### LLMService usage

```python
from telegram_bot.services.llm import LLMService

llm = LLMService(
    api_key=litellm_key,
    base_url="http://localhost:4000",
    model="gpt-4o-mini",
)

# Generate answer from context
answer = await llm.generate_answer(
    question="Какие квартиры в Несебре?",
    context_chunks=search_results,
    system_prompt=None,  # Uses default Bulgarian RE prompt
)
```

### Streaming response

```python
async for chunk in llm.generate_stream(question, context):
    await message.edit_text(accumulated + chunk)
```

### Custom system prompt

```python
answer = await llm.generate_answer(
    question=query,
    context_chunks=results,
    system_prompt="Ты эксперт по недвижимости. Отвечай кратко.",
)
```

## Default System Prompt

```
Ты - ассистент по недвижимости в Болгарии.
Отвечай на вопросы пользователя на основе предоставленного контекста.
Если информации недостаточно, честно скажи об этом.
Всегда указывай цены в евро и расстояния в метрах.
Будь вежливым и полезным.
Форматируй ответ с Markdown: используй **жирный** для важного, • для списков.
```

## Langfuse Integration

LiteLLM sends traces to Langfuse via OTEL:

```yaml
litellm_settings:
  callbacks: ["langfuse_otel"]
```

All LLM calls appear in Langfuse UI at http://localhost:3001

## Dependencies

- Container: `dev-litellm` (4000), 512MB RAM
- Requires: `dev-langfuse` for tracing
- Environment: `CEREBRAS_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`

## Testing

```bash
pytest tests/unit/test_llm_service.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `LiteLLM unhealthy` | Wait 30s, check `docker logs dev-litellm` |
| All providers fail | Check API keys in `.env` |
| Slow responses | Cerebras is fastest, check fallback didn't trigger |

## Development Guide

### Adding new LLM provider

1. Add model to `docker/litellm/config.yaml`:
```yaml
- model_name: gpt-4o-mini-new
  litellm_params:
    model: provider/model-name
    api_key: os.environ/NEW_API_KEY
```

2. Add to fallback chain if needed
3. Add API key to `.env`
4. Restart LiteLLM: `docker compose restart litellm`
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/llm-integration.md`
Expected: YAML frontmatter visible

**Step 3: Commit**

```bash
git add .claude/rules/features/llm-integration.md
git commit -m "docs(features): add LLM integration documentation"
```

---

## Task 7: Write telegram-bot.md

**Files:**
- Create: `.claude/rules/features/telegram-bot.md`

**Step 1: Create telegram-bot.md**

```markdown
---
paths: "telegram_bot/*.py, telegram_bot/middlewares/**"
---

# Telegram Bot

PropertyBot handlers, middlewares, and message processing.

## Purpose

Telegram interface for Bulgarian property search with streaming responses and rate limiting.

## Architecture

```
User Message → ThrottlingMiddleware → ErrorMiddleware
            → PropertyBot.handle_query()
            → [Routing → Cache → Search → LLM]
            → Markdown Response
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/bot.py` | 35 | PropertyBot class |
| `telegram_bot/main.py` | - | Entry point |
| `telegram_bot/config.py` | - | BotConfig dataclass |
| `telegram_bot/middlewares/throttling.py` | 17 | ThrottlingMiddleware |
| `telegram_bot/middlewares/error_handler.py` | 16 | ErrorHandlerMiddleware |

## Bot Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | on_start | Welcome message |
| `/help` | on_help | Usage instructions |
| `/clear` | on_clear | Clear conversation |
| `/stats` | on_stats | Cache statistics |

## Middlewares

### ThrottlingMiddleware

Rate limiting with TTL cache:

```python
ThrottlingMiddleware(
    rate_limit=1.5,      # Seconds between requests
    admin_ids=[123456],  # Exempt from throttling
)
```

- Uses `cachetools.TTLCache(maxsize=10_000, ttl=rate_limit)`
- Admins bypass throttling
- Returns "⏱ Слишком частые запросы" on throttle

### ErrorHandlerMiddleware

Centralized error handling:

```python
# Catches all exceptions
# Logs with exc_info=True
# Returns user-friendly message
"❌ Произошла ошибка при обработке запроса."
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | - | Bot token from @BotFather |
| `rate_limit` | 1.5s | Throttling window |
| `user_context_ttl` | 30 days | CESC context lifetime |
| `cesc_extraction_frequency` | 3 | Extract prefs every N queries |

## Service Dependencies

```python
# Initialized in PropertyBot.__init__
self.cache_service = CacheService(redis_url)
self.voyage_service = VoyageService(api_key)
self.qdrant_service = QdrantService(url, collection)
self.llm_service = LLMService(api_key, base_url)
self.query_analyzer = QueryAnalyzer(api_key, base_url)
self.user_context_service = UserContextService(cache, llm)
self.cesc_personalizer = CESCPersonalizer(llm)
```

## Message Flow

1. **Receive message** → Middlewares (throttle, error)
2. **Classify query** → CHITCHAT/SIMPLE/COMPLEX
3. **Check cache** → Return cached if hit
4. **Preprocess** → Translit, weights
5. **Analyze** → Extract filters
6. **Search** → Qdrant hybrid RRF
7. **Rerank** → Voyage rerank (if COMPLEX)
8. **Generate** → LLM answer
9. **Cache** → Store response
10. **Reply** → Markdown formatted

## Response Formatting

```python
# Bot uses Markdown parse_mode
await message.answer(response, parse_mode="Markdown")
```

Supported:
- `**bold**` for emphasis
- `• item` for lists
- Prices in euros, distances in meters

## Dependencies

- Container: `dev-bot`, 512MB RAM
- Requires: redis, qdrant, litellm, bm42, user-base

## Testing

```bash
pytest tests/unit/test_bot.py -v
pytest tests/unit/test_middlewares.py -v
make e2e-test  # Full E2E with real Telegram
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Bot not responding | Check `docker logs dev-bot` |
| `TELEGRAM_BOT_TOKEN` invalid | Get new token from @BotFather |
| Services unhealthy | Check depends_on containers |

## Development Guide

### Adding new command

1. Add handler method to `PropertyBot`:
```python
async def on_newcmd(self, message: Message):
    await message.answer("Response")
```

2. Register in `_register_handlers()`:
```python
self.dp.message.register(self.on_newcmd, Command("newcmd"))
```

3. Add test in `tests/unit/test_bot.py`

### Adding new middleware

1. Create class in `telegram_bot/middlewares/`
2. Inherit from `BaseMiddleware`
3. Implement `__call__` method
4. Register in `bot.py._setup_middlewares()`
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/telegram-bot.md`
Expected: YAML frontmatter visible

**Step 3: Commit**

```bash
git add .claude/rules/features/telegram-bot.md
git commit -m "docs(features): add Telegram bot documentation"
```

---

## Task 8: Write user-personalization.md

**Files:**
- Create: `.claude/rules/features/user-personalization.md`

**Step 1: Create user-personalization.md**

```markdown
---
paths: "**/cesc*.py, **/user_context*.py"
---

# User Personalization (CESC)

Context-Enabled Semantic Cache with user preferences.

## Purpose

Personalize cached responses based on user history and preferences without re-running full RAG.

## Architecture

```
Query → is_personalized_query()?
     → [NO: return generic cached response]
     → [YES: load user context → CESCPersonalizer → adapted response]
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/cesc.py` | 14 | PERSONAL_MARKERS patterns |
| `telegram_bot/services/cesc.py` | 39 | is_personalized_query() |
| `telegram_bot/services/cesc.py` | 72 | CESCPersonalizer class |
| `telegram_bot/services/user_context.py` | 12 | UserContextService |

## CESC Flow

1. **Check personalization needed:** `is_personalized_query(query, context)`
2. **Skip if generic:** Return cached response as-is
3. **Load context:** `user_context_service.get_context(user_id)`
4. **Personalize:** `cesc_personalizer.personalize(cached, context, query)`
5. **Return adapted response**

## Personal Markers

Triggers personalization:

| Pattern | Example |
|---------|---------|
| `\bмне\b` | "покажи мне квартиры" |
| `\bмой бюджет\b` | "в рамках моего бюджета" |
| `\bкак в прошлый раз\b` | "как в прошлый раз" |
| `\bfor me\b` | "find for me" |

## User Context Structure

```json
{
  "user_id": 123456,
  "language": "ru",
  "preferences": {
    "cities": ["Несебр", "Бургас"],
    "budget_max": 80000,
    "property_types": ["apartment"],
    "rooms": 2
  },
  "profile_summary": "Интересуется: Несебр, Бургас. Бюджет до 80000€",
  "interaction_count": 15,
  "last_queries": ["...", "..."],
  "created_at": "2026-01-15T...",
  "updated_at": "2026-02-02T..."
}
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `context_ttl` | 30 days | Redis storage lifetime |
| `extraction_frequency` | 3 | Extract preferences every N queries |

## Common Patterns

### Check if personalization needed

```python
from telegram_bot.services.cesc import is_personalized_query

if is_personalized_query(query, user_context):
    # Run CESC personalization
    pass
else:
    # Return generic cached response
    pass
```

### Get user context

```python
from telegram_bot.services.user_context import UserContextService

service = UserContextService(cache_service, llm_service)
context = await service.get_context(user_id)
```

### Update from query

```python
# Extracts preferences every 3rd query
context = await service.update_from_query(user_id, query)
```

### Personalize response

```python
from telegram_bot.services.cesc import CESCPersonalizer

personalizer = CESCPersonalizer(llm_service)

if personalizer.should_personalize(user_context):
    response = await personalizer.personalize(
        cached_response=cached,
        user_context=context,
        query=query,
    )
```

## Preference Extraction

LLM extracts preferences from queries:

```
Query: "квартира в Несебре до 70000"
Extracted: {"cities": ["Несебр"], "budget_max": 70000}
```

Preferences merge over time:
- Cities: accumulate (deduplicated)
- Scalars (budget, rooms): overwrite

## Dependencies

- Redis: user context storage (`user_context:{user_id}`)
- LLM: preference extraction, personalization

## Testing

```bash
pytest tests/unit/test_cesc.py -v
pytest tests/unit/test_user_context.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Context not persisting | Check Redis connection |
| Over-personalization | Tune personal markers |
| Extraction failing | Falls back to empty preferences |

## Development Guide

### Adding new personal marker

```python
# telegram_bot/services/cesc.py
PERSONAL_MARKERS = [
    ...
    r"\bnew pattern\b",
]
```

### Adding new preference field

1. Add to extraction prompt in `UserContextService`
2. Add to `_merge_preferences()` logic
3. Add to `CESCPersonalizer` prompt template
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/user-personalization.md`
Expected: YAML frontmatter visible

**Step 3: Commit**

```bash
git add .claude/rules/features/user-personalization.md
git commit -m "docs(features): add user personalization (CESC) documentation"
```

---

## Task 9: Write ingestion.md

**Files:**
- Create: `.claude/rules/features/ingestion.md`

**Step 1: Create ingestion.md**

```markdown
---
paths: "src/ingestion/**"
---

# Document Ingestion

Parsing, chunking, and indexing documents into Qdrant.

## Purpose

Convert PDF/DOCX/CSV documents into searchable vector embeddings in Qdrant.

## Architecture

```
Document → Parser (PyMuPDF/Docling) → Chunker (semantic/fixed)
        → VoyageIndexer (dense + BM42 sparse) → Qdrant upsert
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `src/ingestion/document_parser.py` | 45 | ParserCache |
| `src/ingestion/document_parser.py` | 80+ | UniversalDocumentParser |
| `src/ingestion/chunker.py` | 34 | DocumentChunker |
| `src/ingestion/chunker.py` | 230 | chunk_csv_by_rows() |
| `src/ingestion/voyage_indexer.py` | 47 | VoyageIndexer |

## Parser Selection

| Format | Parser | Speed |
|--------|--------|-------|
| PDF | PyMuPDF | 377x faster than Docling |
| DOCX | Docling | Universal converter |
| CSV | chunk_csv_by_rows() | Row-per-chunk |

## Chunking Strategies

| Strategy | Use Case | Description |
|----------|----------|-------------|
| SEMANTIC | Legal docs | Respects sections, chapters |
| FIXED_SIZE | General | 1024 chars with 256 overlap |
| SLIDING_WINDOW | Dense coverage | Overlapping windows |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 1024 | Target chars per chunk |
| `overlap` | 256 | Overlap between chunks |
| `VOYAGE_BATCH_SIZE` | 128 | Texts per API request |

## Common Patterns

### Parse document

```python
from src.ingestion.document_parser import UniversalDocumentParser

parser = UniversalDocumentParser(use_cache=True)
doc = parser.parse_file("document.pdf")
print(doc.content)
```

### Chunk text

```python
from src.ingestion.chunker import DocumentChunker, ChunkingStrategy

chunker = DocumentChunker(
    chunk_size=1024,
    overlap=256,
    strategy=ChunkingStrategy.SEMANTIC,
)

chunks = chunker.chunk_text(
    text=doc.content,
    document_name="legal_code.pdf",
    article_number="doc_001",
)
```

### Chunk CSV (row-per-chunk)

```python
from src.ingestion.chunker import chunk_csv_by_rows

chunks = chunk_csv_by_rows(
    csv_path=Path("properties.csv"),
    document_name="bulgaria_properties",
)
# Each row becomes one chunk with structured metadata
```

### Index to Qdrant

```python
from src.ingestion.voyage_indexer import VoyageIndexer

indexer = VoyageIndexer(
    qdrant_url="http://localhost:6333",
    voyage_api_key=api_key,
    voyage_model="voyage-4-large",
)

stats = await indexer.index_chunks(
    chunks=chunks,
    collection_name="contextual_bulgaria_voyage",
)
print(f"Indexed {stats.indexed_chunks} chunks")
```

## CSV Metadata Extraction

Automatic field mapping:

| CSV Column | Metadata Field | Type |
|------------|----------------|------|
| Название | title | string |
| Город | city | string |
| Цена (€) | price | int |
| Комнат | rooms | int |
| Площадь (м²) | area | float |
| Этаж | floor | int |
| До моря (м) | distance_to_sea | int |

## Parser Cache

MD5-based caching to skip re-parsing:

```python
parser = UniversalDocumentParser(use_cache=True)
# First call: parses and caches
# Second call: returns from .cache/parser/
```

## Qdrant Collection Setup

VoyageIndexer creates collection with:
- Dense vectors: 1024-dim, cosine distance
- Sparse vectors: BM42
- Scalar Int8 quantization (4x compression)

## Dependencies

- Container: `dev-docling` (5001), 4GB RAM
- Voyage API for embeddings
- Qdrant for storage

## Testing

```bash
pytest tests/unit/test_chunker.py -v
pytest tests/unit/test_document_parser.py -v
pytest tests/unit/test_voyage_indexer.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| PyMuPDF import error | `pip install pymupdf` (not `fitz`) |
| Docling slow | Use PyMuPDF for PDFs |
| Voyage 429 | Add delays, reduce batch size |

## Development Guide

### Adding new document format

1. Add parser method to `UniversalDocumentParser`
2. Update `parse_file()` extension detection
3. Add tests with sample document

### Adding new chunking strategy

1. Add to `ChunkingStrategy` enum
2. Implement `_chunk_new_strategy()` method
3. Add case to `chunk_text()`
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/ingestion.md`
Expected: YAML frontmatter visible

**Step 3: Commit**

```bash
git add .claude/rules/features/ingestion.md
git commit -m "docs(features): add ingestion documentation"
```

---

## Task 10: Write evaluation.md

**Files:**
- Create: `.claude/rules/features/evaluation.md`

**Step 1: Create evaluation.md**

```markdown
---
paths: "src/evaluation/**, tests/baseline/**"
---

# Evaluation & Experiments

Search metrics, RAGAS, MLflow, and A/B testing.

## Purpose

Measure search quality, track experiments, and detect regressions.

## Architecture

```
Queries + Ground Truth → SearchEvaluator → Metrics
                      → MLflow logging → Experiment tracking
                      → Langfuse comparison → Regression detection
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `src/evaluation/evaluator.py` | 20 | SearchEvaluator class |
| `src/evaluation/ragas_evaluation.py` | - | RAGAS integration |
| `src/evaluation/mlflow_integration.py` | - | MLflow setup |
| `src/evaluation/run_ab_test.py` | - | A/B test runner |
| `tests/baseline/collector.py` | - | LangfuseMetricsCollector |
| `tests/baseline/thresholds.yaml` | - | Regression thresholds |

## Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Recall@1 | Correct in top-1 | >90% |
| Recall@5 | Correct in top-5 | >95% |
| NDCG@10 | Ranking quality | >0.95 |
| MRR | Mean Reciprocal Rank | >0.90 |
| Precision@K | Relevant in top-K | varies |

## Regression Thresholds

From `tests/baseline/thresholds.yaml`:

| Metric | Threshold | Alert if |
|--------|-----------|----------|
| LLM p95 latency | +20% | Latency increases |
| Total cost | +10% | Cost increases |
| Cache hit rate | -10% | Cache less effective |
| LLM calls | +5% | More calls needed |

## Common Patterns

### Evaluate search engine

```python
from src.evaluation.evaluator import SearchEvaluator

evaluator = SearchEvaluator("ground_truth_articles.json")

metrics = evaluator.evaluate_query(
    query={"query": "статья 185", "expected_article": "185"},
    search_results=results,
    k_values=[1, 3, 5, 10],
)
# {"recall@1": 1, "ndcg@10": 0.98, "mrr": 1.0, ...}
```

### Run A/B test

```bash
python src/evaluation/run_ab_test.py \
    --engine-a HybridRRF \
    --engine-b HybridRRFColBERT \
    --queries test_queries.json
```

### Compare baselines

```bash
make baseline-compare \
    BASELINE_TAG=smoke-abc-20260128 \
    CURRENT_TAG=smoke-def-20260202
```

### Set new baseline

```bash
make baseline-set TAG=smoke-def-20260202
```

## MLflow Tracking

```python
import mlflow

with mlflow.start_run(run_name="hybrid_rrf_v2"):
    mlflow.log_param("search_engine", "HybridRRFColBERT")
    mlflow.log_metric("recall_at_1", 0.94)
    mlflow.log_metric("latency_p95", 1.2)
```

UI: http://localhost:5000

## RAGAS Evaluation

```python
from src.evaluation.ragas_evaluation import evaluate_with_ragas

scores = await evaluate_with_ragas(
    questions=questions,
    answers=answers,
    contexts=contexts,
    ground_truths=ground_truths,
)
# {"faithfulness": 0.92, "answer_relevancy": 0.88, ...}
```

## LightRAG (Experimental)

Graph-based retrieval for complex queries:

```python
# Container: dev-lightrag (9621)
# Uses OpenAI for graph construction
# Experimental, not in main pipeline
```

## Dependencies

- Container: `dev-mlflow` (5000)
- Container: `dev-lightrag` (9621) - experimental
- Langfuse for trace comparison

## Testing

```bash
pytest tests/unit/test_evaluator.py -v
pytest tests/baseline/ -v
make baseline-smoke
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| MLflow connection | `docker compose up -d mlflow` |
| Missing ground truth | Generate with `create_golden_set.py` |
| RAGAS timeout | Reduce batch size |

## Development Guide

### Adding new metric

1. Add calculation method to `SearchEvaluator`
2. Include in `evaluate_query()` return dict
3. Add to MLflow logging
4. Update baseline thresholds if needed

### Creating golden set

```bash
python src/evaluation/create_golden_set.py \
    --input queries.txt \
    --output ground_truth.json
```
```

**Step 2: Verify file created**

Run: `head -20 .claude/rules/features/evaluation.md`
Expected: YAML frontmatter visible

**Step 3: Commit**

```bash
git add .claude/rules/features/evaluation.md
git commit -m "docs(features): add evaluation documentation"
```

---

## Task 11: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add features reference to Modular Docs section**

Find the "Modular Docs" section and add features reference:

```markdown
## Modular Docs

See `.claude/rules/` for domain-specific documentation:

| File | Scope | Loads when working with |
|------|-------|------------------------|
| `features/caching.md` | Cache system, TTL, thresholds | `**/cache*.py` |
| `features/search-retrieval.md` | Hybrid RRF, Qdrant | `src/retrieval/**` |
| `features/query-processing.md` | Routing, analysis | `**/query*.py` |
| `features/embeddings.md` | Voyage, BGE-M3, BM42 | `**/embed*.py, services/**` |
| `features/llm-integration.md` | LiteLLM, fallbacks | `**/llm*.py, docker/litellm/**` |
| `features/telegram-bot.md` | Handlers, middlewares | `telegram_bot/*.py` |
| `features/user-personalization.md` | CESC, user context | `**/cesc*.py` |
| `features/ingestion.md` | Parsing, chunking | `src/ingestion/**` |
| `features/evaluation.md` | Metrics, A/B tests | `src/evaluation/**` |
| `services.md` | VoyageService, QdrantService, Cache patterns | `telegram_bot/services/**/*.py` |
| `search.md` | Search engines, Qdrant query_points | `src/retrieval/**/*.py` |
| `testing.md` | Unit tests, E2E, baseline | `tests/**/*.py` |
| `observability.md` | Langfuse, instrumentation | `telegram_bot/observability.py` |
| `docker.md` | LiteLLM, docker-compose, bot | `docker/**/*` |
| `skills.md` | Superpowers workflow, план реализации | `docs/plans/**/*.md` |
```

**Step 2: Verify CLAUDE.md updated**

Run: `grep -A 5 "features/caching" CLAUDE.md`
Expected: Features table visible

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add features documentation reference to CLAUDE.md"
```

---

## Task 12: Test paths: Auto-loading

**Files:**
- Test: `.claude/rules/features/*.md`

**Step 1: Verify all files have correct frontmatter**

```bash
for f in .claude/rules/features/*.md; do
    echo "=== $f ==="
    head -3 "$f"
done
```

Expected: Each file starts with `---` and has `paths:` line

**Step 2: Count total lines per file**

```bash
wc -l .claude/rules/features/*.md
```

Expected: Each file < 500 lines

**Step 3: Verify no paths overlap**

Manual check that paths don't conflict:
- `caching.md`: `**/cache*.py`
- `search-retrieval.md`: `src/retrieval/**`
- `query-processing.md`: `**/query*.py`
- etc.

**Step 4: Final commit with all features**

```bash
git add -A
git commit -m "docs(features): complete feature documentation system

- 9 feature docs in .claude/rules/features/
- Auto-loading via paths: frontmatter
- Updated CLAUDE.md with references"
```

---

## Summary

| Task | Files | Description |
|------|-------|-------------|
| 1 | directory | Create features/ directory |
| 2 | caching.md | 6-tier cache documentation |
| 3 | search-retrieval.md | Hybrid RRF, Qdrant docs |
| 4 | query-processing.md | Routing, analysis docs |
| 5 | embeddings.md | Voyage, BGE-M3, BM42 docs |
| 6 | llm-integration.md | LiteLLM, fallbacks docs |
| 7 | telegram-bot.md | Handlers, middlewares docs |
| 8 | user-personalization.md | CESC documentation |
| 9 | ingestion.md | Parsing, chunking docs |
| 10 | evaluation.md | Metrics, A/B tests docs |
| 11 | CLAUDE.md | Add features reference |
| 12 | test | Verify auto-loading works |

**Total:** 9 new documentation files, ~3000 lines
