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

## Langfuse UI Workflow

**Local URL:** http://localhost:3001

### Debugging a Slow Query

1. **Find the trace:** Filter by `user_id` or `session_id` (format: `chat-{hash}-{YYYYMMDD}`)
2. **Check the timeline:** Expand trace to see nested spans with durations
3. **Identify bottleneck:** Look for spans with >500ms (red highlighted)
4. **Check cache metrics:** Look at `cache-semantic-check`, `cache-search-check` spans for hit/miss

### Comparing Baseline Runs

1. **Run smoke tests:** `make baseline-smoke` (generates session like `smoke-abc123-20260202`)
2. **View in UI:** Sessions → filter by `smoke-*` → compare latency/cost columns
3. **Automated compare:** `make baseline-compare BASELINE_TAG=smoke-old CURRENT_TAG=smoke-new`

### Finding Cache Problems

1. **Filter:** Traces → Name = `cache-semantic-check`
2. **Group by output:** Check `hit: true/false` distribution
3. **Low hit rate?** Check distance thresholds in `CacheLayerManager`

### Tracking Costs

1. **Dashboard:** Overview → Cost by model/day
2. **Per-user:** Traces → filter by `user_id` → sum costs
3. **Regression check:** Costs tab shows trend line

### Session ID Format

All traces use unified format: `{type}-{hash}-{YYYYMMDD}`

| Type | Example | Use Case |
|------|---------|----------|
| `chat` | `chat-a1b2c3d4-20260202` | Telegram conversations |
| `smoke` | `smoke-abc123-20260202` | Smoke test runs |
| `load` | `load-def456-20260202` | Load test runs |
| `ci` | `ci-sha-20260202` | CI pipeline runs |

### Key Filters

| Filter | Example | Purpose |
|--------|---------|---------|
| Session | `chat-*` | All chat sessions |
| User | `123456789` | Specific user traces |
| Tags | `telegram,rag` | Production queries |
| Name | `llm-generate-answer` | LLM generation only |
| Score | `semantic_cache_hit=1` | Cache hits only |

## Thresholds (regression detection)

| Metric | Threshold | Description |
|--------|-----------|-------------|
| LLM p95 latency | +20% | Alert if latency increases |
| Total cost | +10% | Alert if cost increases |
| Cache hit rate | -10% | Alert if cache effectiveness drops |
| LLM calls | +5% | Alert if call count increases |

Config: `tests/baseline/thresholds.yaml`

## Instrumented Services

### @observe Tracing (Langfuse decorator)

Cache and graph nodes use `@observe` decorator for automatic span creation:

| Component | Decorator | Tracked |
|-----------|-----------|---------|
| cache_check_node | `@observe(name="cache_check")` | hit/miss, embedding latency |
| cache_store_node | `@observe(name="cache_store")` | store latency |
| retrieve_node | `@observe(name="retrieve")` | search latency, results count |
| CacheLayerManager.check_semantic | `@observe` | hit/miss, latency |
| CacheLayerManager.store_semantic | `@observe` | latency |

### Service-level Traces

| Service | Trace Name | Tracked |
|---------|------------|---------|
| VoyageService.embed_query | voyage-embed-query | tokens, latency |
| VoyageService.embed_documents | voyage-embed-documents | tokens, latency |
| VoyageService.rerank | voyage-rerank | latency, top_k |
| QdrantService.hybrid_search_rrf | qdrant-hybrid-search-rrf | latency, results |
| QdrantService.batch_search_rrf | qdrant-batch-search-rrf | latency, batch_size |
| QdrantService.search_with_score_boosting | qdrant-search-score-boosting | latency, results |
| CacheLayerManager.get_exact("search") | cache-search-check | hit/miss, latency |
| CacheLayerManager.get_exact("rerank") | cache-rerank-check | hit/miss, latency, layer |
| LLMService.generate_answer | llm-generate-answer | model, tokens, latency |
| classify_node | query-classify | query_type (6-type taxonomy) |
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

## Langfuse Prompt Management

`telegram_bot/integrations/prompt_manager.py` — centralized prompt storage in Langfuse UI.

```python
from telegram_bot.integrations.prompt_manager import get_prompt

prompt = get_prompt(name="rag-system", fallback="You are...", variables={"domain": "real estate"})
```

- Prompts cached client-side (`cache_ttl` param)
- Graceful fallback to hardcoded templates when Langfuse unavailable
- Variable substitution via `prompt.compile(**variables)`

## Langfuse v3 Stack (docker-compose.dev.yml)

| Service | Port | Purpose |
|---------|------|---------|
| langfuse | 3001 | Web UI + API |
| langfuse-worker | - | Background processing |
| clickhouse | 8123, 9009 | Analytics storage |
| minio | 9090, 9091 | S3 events/media |
| redis-langfuse | 6380 | Langfuse queues (separate from app Redis) |

**Bot service env vars** (docker-compose.dev.yml):
```yaml
LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY:-}   # optional, empty disables tracing
LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY:-}
LANGFUSE_HOST: http://langfuse:3000
```

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
