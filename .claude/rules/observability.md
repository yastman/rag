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

## Instrumented Services (35 traced operations)

### Root Trace

| Component | Span Name | Details |
|-----------|-----------|---------|
| `bot.py` handle_query | `telegram-rag-query` | Root span, session_id, user_id, tags |

### Graph Nodes (9 nodes, all covered)

| Node | Span Name |
|------|-----------|
| classify_node | `node-classify` |
| cache_check_node | `node-cache-check` |
| cache_store_node | `node-cache-store` |
| retrieve_node | `node-retrieve` |
| grade_node | `node-grade` |
| rerank_node | `node-rerank` |
| generate_node | `node-generate` |
| rewrite_node | `node-rewrite` |
| respond_node | `node-respond` |

### Cache (8 methods)

| Method | Span Name |
|--------|-----------|
| check_semantic | `cache-semantic-check` |
| store_semantic | `cache-semantic-store` |
| get_exact | `cache-exact-get` |
| store_exact | `cache-exact-store` |
| get_embedding | `cache-embedding-get` |
| store_embedding | `cache-embedding-store` |
| get_conversation | `cache-conversation-get` |
| store_conversation | `cache-conversation-store` |

### Services

| Service | Span Name | as_type |
|---------|-----------|---------|
| BGEM3HybridEmbeddings.aembed_hybrid | `bge-m3-hybrid-embed` | span |
| BGEM3HybridEmbeddings.aembed_hybrid_batch | `bge-m3-hybrid-embed-batch` | span |
| BGEM3Embeddings.aembed_documents | `bge-m3-dense-embed` | span |
| BGEM3SparseEmbeddings.aembed_query | `bge-m3-sparse-embed` | span |
| ColbertRerankerService.rerank | `colbert-rerank` | span |
| QdrantService.hybrid_search_rrf | `qdrant-hybrid-search-rrf` | span |
| QdrantService.batch_search_rrf | `qdrant-batch-search-rrf` | span |
| QdrantService.search_with_score_boosting | `qdrant-search-score-boosting` | span |
| VoyageService (5 methods) | `voyage-*` | generation |

### LLM Calls (auto-traced via langfuse.openai.AsyncOpenAI)

| Module | `name=` kwarg |
|--------|---------------|
| llm.py generate_answer | `generate-answer` |
| llm.py stream_answer | `stream-answer` |
| query_analyzer.py | `query-analysis` |
| query_preprocessor.py | `hyde-generate` |
| generate_node LLM call | `generate-answer` |
| rewrite_node LLM call | `rewrite-query` |

### OTEL Configuration

```yaml
OTEL_SERVICE_NAME: rag-bot  # Set in docker-compose.dev.yml bot service
```

## Langfuse Scores (All Exit Paths)

12 scores written via `_write_langfuse_scores(lf, result)` in `bot.py` after `graph.ainvoke()`:

**Latency convention:** `latency_total_ms` is **wall-time** measured via `time.perf_counter` in `handle_query` (pipeline_wall_ms), NOT sum of stages. All `latency_stages` values are in **seconds** (float) for per-stage breakdown only.

| Score | Values | Purpose |
|-------|--------|---------|
| `query_type` | 0/1/2 | CHITCHAT/SIMPLE/COMPLEX (via `_QUERY_TYPE_SCORE` mapping) |
| `latency_total_ms` | float | End-to-end wall-time latency (perf_counter, ms) |
| `semantic_cache_hit` | 0.0/1.0 | Semantic cache effectiveness |
| `embeddings_cache_hit` | 0.0/1.0 | Embeddings cache (real value from state) |
| `search_cache_hit` | 0.0/1.0 | Search results cache (real value from state) |
| `rerank_applied` | 0.0/1.0 | Whether reranking was performed |
| `rerank_cache_hit` | 0.0/1.0 | Rerank cache (not yet tracked in state, default 0.0) |
| `results_count` | 0-N | Number of retrieved documents |
| `no_results` | 0.0/1.0 | Query returned empty results |
| `llm_used` | 0.0/1.0 | LLM generation was invoked |
| `confidence_score` | 0.0-1.0 | Grade confidence (real value from state) |
| `hyde_used` | 0.0 | Not yet tracked in LangGraph state |

**Implementation:** `get_client().score_current_trace(name=..., value=...)` (Langfuse SDK v3)

## Langfuse Prompt Management

`telegram_bot/integrations/prompt_manager.py` — centralized prompt storage in Langfuse UI.

```python
from telegram_bot.integrations.prompt_manager import get_prompt

prompt = get_prompt(name="rag-system", fallback="You are...", variables={"domain": "real estate"})
```

- **API probe pre-check**: `_probe_prompt_available()` calls `api.prompts.get()` before SDK `get_prompt()` — avoids noisy `generate-label:production` warnings
- **TTL cache**: missing prompts cached in `_missing_prompts_until` (default 300s), known in `_known_prompts_until` — no repeated API calls
- Graceful fallback to hardcoded templates when Langfuse unavailable or prompt absent
- Variable substitution via `prompt.compile(**variables)`
- Missing prompt messages at DEBUG level (no production log noise)

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

## Trace Validation (#110)

`scripts/validate_traces.py` uses `@observe`, `propagate_attributes`, `update_current_trace` for headless LangGraph runs. After flush, `enrich_results_from_langfuse()` fetches scores + node spans by trace_id via Langfuse API. Reference trace `c2b95d86` — anomalous (5213s), not reproducible.

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
