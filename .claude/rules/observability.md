---
paths: "telegram_bot/observability.py, tests/baseline/**/*.py"
---

# Observability & Baseline

Langfuse v3 — single source of truth for LLM metrics, cost tracking, and regression detection.

## Quick Commands

```bash
make baseline-smoke                          # Smoke tests with Langfuse tracing
make baseline-load                           # Load tests with Langfuse tracing
make baseline-compare BASELINE_TAG=smoke-abc-20260128 CURRENT_TAG=smoke-def-20260128
make baseline-set TAG=smoke-abc-20260128     # Set current as new baseline
```

## Langfuse UI

- **Local:** http://localhost:3001
- **Traces:** See all LLM calls, latency, cost
- **Sessions:** Group traces by test run (smoke-*, load-*)

## Thresholds (regression detection)

| Metric | Threshold | Description |
|--------|-----------|-------------|
| LLM p95 latency | +20% | Alert if latency increases |
| Total cost | +10% | Alert if cost increases |
| Cache hit rate | -10% | Alert if cache effectiveness drops |
| LLM calls | +5% | Alert if call count increases |

Config: `tests/baseline/thresholds.yaml`

## Instrumented Services

| Service | Trace Name | Tracked |
|---------|------------|---------|
| VoyageService.embed_query | voyage-embed-query | tokens, latency |
| VoyageService.embed_documents | voyage-embed-documents | tokens, latency |
| VoyageService.rerank | voyage-rerank | latency, top_k |
| QdrantService.hybrid_search_rrf | qdrant-hybrid-search-rrf | latency, results |
| QdrantService.search_with_score_boosting | qdrant-search-score-boosting | latency, results |
| CacheService.check_semantic_cache | cache-semantic-check | hit/miss, latency |
| CacheService.store_semantic_cache | cache-semantic-store | latency |
| CacheService.get_cached_search | cache-search-check | hit/miss, latency |
| CacheService.get_cached_rerank | cache-rerank-check | hit/miss, latency, layer |
| LLMService.generate_answer | llm-generate-answer | model, tokens, latency |
| QueryRouter.classify_query | query-router | query_type (CHITCHAT/SIMPLE/COMPLEX) |
| QueryAnalyzer.analyze | query-analyzer | filters, tokens |
| PropertyBot.handle_query | telegram-message | root trace, user_id, session_id |
| LLMService (via LiteLLM) | Auto (OTEL) | tokens, cost, latency |

## Langfuse Scores (All Exit Paths)

All 10 scores written via try/finally accumulator pattern in `handle_query`:

| Score | Values | Purpose |
|-------|--------|---------|
| `query_type` | 0/1/2 | CHITCHAT/SIMPLE/COMPLEX |
| `latency_total_ms` | float | End-to-end request latency |
| `semantic_cache_hit` | 0.0/1.0 | Semantic cache effectiveness |
| `embeddings_cache_hit` | 0.0/1.0 | Embeddings cache effectiveness |
| `search_cache_hit` | 0.0/1.0 | Search results cache |
| `rerank_applied` | 0.0/1.0 | Whether reranking was performed |
| `rerank_cache_hit` | 0.0/1.0 | Rerank cache effectiveness |
| `results_count` | 0-N | Number of retrieved documents |
| `no_results` | 0.0/1.0 | Query returned empty results |
| `llm_used` | 0.0/1.0 | LLM generation was invoked |

## Langfuse v3 Stack (docker-compose.dev.yml)

| Service | Port | Purpose |
|---------|------|---------|
| langfuse | 3001 | Web UI + API |
| langfuse-worker | - | Background processing |
| clickhouse | 8123, 9009 | Analytics storage |
| minio | 9090, 9091 | S3 events/media |
| redis-langfuse | 6380 | Langfuse queues (separate from app Redis) |

## Baseline Module

```
tests/baseline/
├── collector.py       # LangfuseMetricsCollector (API + Qdrant + Redis)
├── manager.py         # BaselineManager + BaselineSnapshot
├── cli.py             # CLI: compare, set-baseline, report
├── thresholds.yaml    # Regression detection thresholds
├── conftest.py        # Fixtures
└── test_*.py          # Tests (16 passing)
```
