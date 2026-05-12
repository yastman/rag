# Observability and Storage Index

Quick orientation for Langfuse traces, Qdrant, and Redis/cache investigations. Links to runbooks and canonical docs instead of duplicating operational procedures.

## Langfuse Traces

Use this path when traces are missing, gaps appear, or you need to validate scoring.

### Start Here

- **Runbook**: [`../runbooks/LANGFUSE_TRACING_GAPS.md`](../runbooks/LANGFUSE_TRACING_GAPS.md)
- **Quality scoring**: [`../RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md)

### Common Investigations

| Question | Where to Look |
|---|---|
| Are traces being exported? | `telegram_bot/integrations/langfuse_client.py` and middleware trace root |
| What spans are emitted? | Search for `span=` or `trace=` in `telegram_bot/graph/`, `telegram_bot/services/`, `src/api/` |
| Is scoring configured? | `src/evaluation/` and `telegram_bot/services/scoring.py` |
| Trace validation command | `make validate-traces-fast` |

### Fast Search

```bash
# Langfuse spans and scoring in bot and API
rg -n "langfuse|trace|span|score|observation" telegram_bot/ src/api/ src/evaluation/

# Ingestion trace contract
rg -n "ingestion-cli|ingestion-flow|ingestion-qdrant" src/ingestion/unified/
```

## Qdrant

Use this path for collection health, vector search issues, schema drift, or missing points.

### Start Here

- **Runbook**: [`../runbooks/QDRANT_TROUBLESHOOTING.md`](../runbooks/QDRANT_TROUBLESHOOTING.md)
- **Stack reference**: [`../QDRANT_STACK.md`](../QDRANT_STACK.md)

### Common Investigations

| Question | Where to Look |
|---|---|
| Which collections exist? | `curl -fsS http://localhost:6333/collections` |
| Is the runtime collection healthy? | `curl -fsS http://localhost:6333/collections/gdrive_documents_bge` |
| Did bootstrap create the right schema? | `uv run python -m src.ingestion.unified.cli schema-check --require-colbert` |
| Is ColBERT coverage sufficient? | `uv run python -m src.ingestion.unified.cli coverage-check --min-ratio 0.995` |
| Are points actually present? | `curl -fsS http://localhost:6333/collections/gdrive_documents_bge | python3 -m json.tool` |

### Collections Overview

| Collection | Purpose | Owner |
|---|---|---|
| `gdrive_documents_bge` | Default document chunks (dense + sparse + ColBERT) | Unified ingestion |
| `gdrive_documents_bge_active` | Alias for blue/green cutover | Bot startup (`QdrantService._ensure_alias`) |
| `apartments` | Apartment listings (top-level payload) | `scripts/apartments/setup_collection.py` |
| `conversation_history` | User session history vectors | `telegram_bot/services/history_service.py` |

### Fast Search

```bash
# Qdrant runtime integration
rg -n "qdrant|collection|vector|hybrid|rrf|colbert" telegram_bot/services/ src/ingestion/unified/ src/retrieval/

# Collection policy
rg -n "resolve_collection_name|quantization" src/config/
```

## Redis and Cache

Use this path for cache degradation, eviction, latency, or semantic cache misses.

### Start Here

- **Runbook**: [`../runbooks/REDIS_CACHE_DEGRADATION.md`](../runbooks/REDIS_CACHE_DEGRADATION.md)
- **Cache architecture**: [`../TROUBLESHOOTING_CACHE.md`](../TROUBLESHOOTING_CACHE.md)

### Common Investigations

| Question | Where to Look |
|---|---|
| Is Redis reachable? | `redis-cli -p 6379 -a "$REDIS_PASSWORD" ping` |
| Are cache keys present? | `SCAN 0 MATCH 'sem:v8:bge1024:*' COUNT 100` in `redis-cli` |
| Which tier is missing? | `cache.get_metrics()` in bot logs or `telegram_bot/integrations/cache.py` |
| Why is everything a miss? | Check `grade_confidence` threshold uses RRF scale, not cosine similarity |
| Cache version stale after model change? | Bump `CACHE_VERSION` or `SEMANTIC_CACHE_VERSION` in `integrations/cache.py` |

### Cache Tiers

| Tier | Type | TTL | Purpose |
|---|---|---|---|
| Semantic | RedisVL SemanticCache | Query-dependent | LLM response caching |
| Embeddings | RedisVL EmbeddingsCache | 7 days | Dense embedding cache |
| Query bundle | RedisVL EmbeddingsCache | 7 days | BGE-M3 dense + sparse + ColBERT cache (see [ADR-0004](../adr/0004-redisvl-semantic-cache.md)) |
| Sparse | Redis exact | 7 days | Sparse embedding cache |
| Search | Redis exact | 2 hours | Search results cache |
| Rerank | Redis exact | 2 hours | Reranked results cache |

### Fast Search

```bash
# Cache implementation
rg -n "CacheLayerManager|SemanticCache|EmbeddingsCache" telegram_bot/integrations/cache.py

# Cache usage in pipelines
rg -n "cache|semantic|embeddings" telegram_bot/pipelines/ telegram_bot/services/

# Redis integration beyond cache
rg -n "redis|Redis" telegram_bot/integrations/ telegram_bot/services/
```

## LiteLLM Proxy

Use this path for LLM connection failures or proxy errors.

- **Runbook**: [`../runbooks/LITEllm_FAILURE.md`](../runbooks/LITEllm_FAILURE.md)
- **Compose service**: `litellm` (profile `bot` and `voice`)
- **Local URL**: http://localhost:4000

Quick check:

```bash
curl -fsS http://localhost:4000/health
```

## Postgres

Use this path for WAL recovery or replication issues.

- **Runbook**: [`../runbooks/POSTGRESQL_WAL_RECOVERY.md`](../runbooks/POSTGRESQL_WAL_RECOVERY.md)
- **Compose service**: `postgres` (default/unprofiled)
- **Used by**: Lead scoring, graph checkpoints, unified ingestion state, user data
