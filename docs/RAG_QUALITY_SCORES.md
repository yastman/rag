# RAG Quality Scores

The RAG pipeline computes **14 RAG quality scores** per query via `write_langfuse_scores()` in `telegram_bot/scoring.py`. These scores are written to Langfuse for observability and product iteration.

## Score Overview

| Score | Type | Category | Description |
|-------|------|----------|-------------|
| `query_type` | CATEGORICAL | Classification | Query complexity score (0=chitchat/off-topic, 1=simple/general/faq/entity, 2=structured/complex) |
| `latency_total_ms` | NUMERIC | Latency | End-to-end latency in milliseconds |
| `semantic_cache_hit` | BOOLEAN | Cache | Whether semantic cache was hit |
| `embeddings_cache_hit` | BOOLEAN | Cache | Whether embeddings were served from cache |
| `search_cache_hit` | BOOLEAN | Cache | Whether search results were cached |
| `rerank_applied` | BOOLEAN | Retrieval | Whether reranking was applied |
| `rerank_cache_hit` | BOOLEAN | Cache | Whether rerank results were cached |
| `results_count` | NUMERIC | Retrieval | Number of retrieved documents |
| `no_results` | BOOLEAN | Retrieval | Whether search returned zero results |
| `llm_used` | BOOLEAN | Generation | Whether LLM generation was called |
| `confidence_score` | NUMERIC | Retrieval | Document relevance confidence (RRF scale) |
| `llm_ttft_ms` | NUMERIC | Latency | Time to first token in milliseconds |
| `llm_response_duration_ms` | NUMERIC | Latency | Total LLM response generation time |

## Score Categories

### Retrieval Quality Scores

| Score | What it measures | Good range | Indicates problem when |
|-------|-----------------|------------|----------------------|
| `confidence_score` | Document relevance (RRF scale) | >= 0.005 | < 0.005: documents may be irrelevant |
| `results_count` | Number of retrieved docs | 1-20 | 0: `no_results` = 1 |
| `no_results` | Zero results flag | 0 | 1: search failed or collection empty |
| `rerank_applied` | Whether reranking was needed | 0 or 1 | N/A - rerank is intentional |

### Generation Quality Scores

| Score | What it measures | Good range | Indicates problem when |
|-------|-----------------|------------|----------------------|
| `llm_used` | LLM was called | 1 | 0: query served from cache only |
| `llm_ttft_ms` | Time to first token | < 1000ms | > 5000ms: LLM provider slow |
| `llm_response_duration_ms` | Total generation time | varies | N/A - varies by response length |

### Cache Performance Scores

| Score | What it measures | Good range | Indicates problem when |
|-------|-----------------|------------|----------------------|
| `semantic_cache_hit` | Semantic cache hit | 1 (hit) | 0: new query or threshold too strict |
| `embeddings_cache_hit` | Embedding cache hit | 1 (hit) | 0: first time query or embeddings version bump |
| `search_cache_hit` | Search results cache hit | 1 (hit) | 0: new query parameters |
| `rerank_cache_hit` | Rerank cache hit | 1 (hit) | 0: first time this query+docs combination |

### Latency Scores

| Score | What it measures | Good range | Indicates problem when |
|-------|-----------------|------------|----------------------|
| `latency_total_ms` | End-to-end pipeline latency | < 3000ms | > 5000ms: retrieval or LLM slow |
| `llm_ttft_ms` | Time to first token | < 1000ms | > 5000ms: LLM provider issues |
| `llm_response_duration_ms` | LLM streaming duration | varies | N/A |

## RRF Scale Explanation

The `confidence_score` uses the **Reciprocal Rank Fusion (RRF)** scale, not cosine similarity [0-1].

RRF scores range from ~0.016 (rank 1) down to ~0.0006 (rank 180), computed as `1/(k+rank)` where k=60.

**Why this matters for thresholds:**
- A threshold of `0.005` means "rank <= 1/0.005 - 60 = 140" — documents ranked 140 or better pass
- The store guard threshold in `pipelines/client.py` uses `config.relevance_threshold_rrf` (default 0.005)
- Cache check thresholds in `CacheLayerManager` use cosine distance [0-2], NOT RRF

## How to Interpret Scores

### High cache hit rates indicate:
- Good cache coverage for repeated queries
- Appropriate cache thresholds for query types

### Low confidence with results:
- Query may not match document content
- Consider query rewrite if `rerank_applied` = 0

### High latency:
- Check `llm_ttft_ms` — if high, LLM provider issue
- Check `latency_stages` in Langfuse trace for breakdown

## Where to View Scores

1. **Langfuse UI**: Navigate to your trace → Scores tab
2. **Langfuse API**: Query scores via SDK
3. **Bot metrics**: `/metrics` command shows p50/p95 pipeline timing

## Score Data Types

| Type | Description |
|------|-------------|
| `NUMERIC` | Continuous values (latencies, counts) |
| `BOOLEAN` | 0 or 1 (flags) |
| `CATEGORICAL` | String labels (query_type, input_type) |

## Related Documentation

- [Pipeline Overview](PIPELINE_OVERVIEW.md) — pipeline flow
- [Troubleshooting Cache](TROUBLESHOOTING_CACHE.md) — cache debugging
- `.claude/rules/features/telegram-bot.md` — bot architecture
