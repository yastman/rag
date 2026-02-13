---
paths: "telegram_bot/observability.py, tests/baseline/**/*.py"
---

# Observability & Baseline

Langfuse v3 — single source of truth for LLM metrics, cost tracking, and regression detection.

## Quick Commands

```bash
make baseline-smoke                          # Smoke tests with Langfuse tracing
make baseline-load                           # Load tests with Langfuse tracing
make baseline-compare BASELINE_TAG=main-latest CURRENT_SESSION=ci-abc-job-1
make baseline-set TAG=main-latest SESSION_ID=smoke-abc-20260128
make baseline-check                          # Smoke + compare against main-latest
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
3. **Automated compare:** `make baseline-compare BASELINE_TAG=main-latest CURRENT_SESSION=smoke-new`

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
| LLM calls | +15% | Alert if call count increases (widened from 5% per #168) |

Config: `tests/baseline/thresholds.yaml` (includes `go_no_go` section for validate_traces.py)

## Instrumented Services (35 traced operations)

### Root Trace

| Component | Span Name | Details |
|-----------|-----------|---------|
| `bot.py` handle_query | `telegram-rag-query` | Root span, session_id, user_id, tags |

### Entry Point Pattern (Orphan Prevention)

All entry points that invoke @observe-decorated code MUST use `traced_pipeline` or `propagate_attributes`.
Without this, each @observe call creates a separate root trace (session=None, userId=None).

Rule: `traced_pipeline` → `@observe(root)` → nested `@observe(children)`

| Entry Point | File | session_id format |
|-------------|------|-------------------|
| Telegram bot | bot.py:handle_query | chat-{hash}-{YYYYMMDD} |
| Validation | scripts/validate_traces.py | validate-{run_id[:8]} |
| Smoke tests | tests/smoke/test_langgraph_smoke.py | smoke-test-{YYYYMMDD} |
| Integration | tests/integration/test_graph_paths.py | test-{path-name} |

Usage:

    from telegram_bot.observability import traced_pipeline
    with traced_pipeline(session_id="...", user_id="..."):
        result = await graph.ainvoke(state)

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

### Payload Bloat Prevention (#143)

6 heavy nodes use `@observe(capture_input=False, capture_output=False)` to disable auto-capture of full LangGraph state (documents, embeddings, messages, audio bytes). Instead, they log curated metadata via `get_client().update_current_span(input={...}, output={...})`.

| Heavy Node | Curated Input | Curated Output |
|------------|---------------|----------------|
| retrieve_node | query_preview, query_hash, query_type, top_k | results_count, top_score, min_score, search_cache_hit, duration_ms |
| generate_node | query_preview, query_hash, context_docs_count, streaming_enabled | response_length, llm_provider_model, llm_ttft_ms, token_usage, duration_ms |
| cache_check_node | query_preview, query_hash, query_type | cache_hit, embeddings_cache_hit, hit_layer, duration_ms |
| cache_store_node | query_preview, query_hash, response_length | stored, stored_semantic, stored_conversation, duration_ms |
| respond_node | response_length, response_sent, has_message | respond_skipped, respond_delivered, used_markdown, duration_ms |
| transcribe_node | audio_size_bytes, voice_language, stt_model, voice_duration_s | stt_duration_ms, text_length, text_preview |

Light nodes (classify, grade, rerank, rewrite) keep default auto-capture — their state is small.

**Pattern:**
```python
@observe(name="node-retrieve", capture_input=False, capture_output=False)
async def retrieve_node(state, ...):
    lf = get_client()
    lf.update_current_span(input={"query_preview": query[:120], ...})
    # ... node logic ...
    lf.update_current_span(output={"results_count": len(results), ...})
```

**Forbidden keys** in curated spans: `documents`, `query_embedding`, `sparse_embedding`, `state`, `messages`, `voice_audio`.

### Error Span Tracking (#103 P1.2)

4 nodes call `get_client().update_current_span(level=..., status_message=...)` on failure:

| Node | Level | Trigger | Fallback |
|------|-------|---------|----------|
| generate_node | ERROR | LLM call failed | Document summary fallback |
| generate_node | WARNING | Streaming failed | Non-streaming fallback |
| rewrite_node | ERROR | LLM rewrite failed | Keep original query |
| rerank_node | ERROR | ColBERT failed | Score-sort fallback |
| respond_node | ERROR | Telegram send failed | (logged, no retry) |

**Langfuse UI:** Filter spans by `level=ERROR` to find degraded queries.

**Pattern:**
```python
from telegram_bot.observability import get_client
except Exception as e:
    get_client().update_current_span(
        level="ERROR",
        status_message=f"Description: {str(e)[:200]}",
    )
```

**Graceful degradation:** `_NullLangfuseClient.update_current_span()` is a no-op when Langfuse disabled.

### Cache (9 methods)

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
| store_conversation_batch | `cache-conversation-batch-store` |

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

14 scores written via `_write_langfuse_scores(lf, result)` + 3 judge scores (async) in `bot.py` after `graph.ainvoke()`:

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
| `llm_ttft_ms` | float | Time to first token (ms), streaming only |
| `llm_response_duration_ms` | float | Full LLM response wall-time (ms) |

### LLM-as-a-Judge Scores (async, online sampling)

Written by `run_online_judge()` via `asyncio.create_task()` — fire-and-forget, never blocks response.

| Score | Values | Purpose |
|-------|--------|---------|
| `judge_faithfulness` | 0.0–1.0 | Answer grounded in context (no hallucinations) |
| `judge_answer_relevance` | 0.0–1.0 | Answer useful for the question |
| `judge_context_relevance` | 0.0–1.0 | Retrieved docs relevant to question |
| `judge_*_error` | CATEGORICAL | Written on judge failure (instead of 0.0) |

Controlled by `JUDGE_SAMPLE_RATE` (default 0.0 = off). Batch mode: `make eval-judge`.

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

## Trace Validation (#110, #143)

`scripts/validate_traces.py` uses `@observe`, `propagate_attributes`, `update_current_trace` for headless LangGraph runs. After flush, `enrich_results_from_langfuse()` fetches scores + node spans by trace_id via Langfuse API.

Go/No-Go thresholds are config-driven via `tests/baseline/thresholds.yaml` `go_no_go` section (#168).

Go/No-Go criterion `generate_p50_lt_2s` (renamed from `ttft_p50_lt_2s` in #143) measures full generation latency in non-streaming validation mode. True TTFT requires a streaming phase (see #144).

## Baseline Module (#167)

Per-trace computation with session isolation. No aggregate API calls — fetches traces by `session_id` / `tag`, computes metrics from observation-level data.

```
tests/baseline/
├── collector.py       # LangfuseMetricsCollector + SessionMetrics (per-trace computation)
├── manager.py         # BaselineManager + BaselineSnapshot (compare logic)
├── cli.py             # CLI: compare (--baseline-tag, --current-session, --output), set-baseline
├── thresholds.yaml    # Regression detection thresholds
├── conftest.py        # Fixtures
└── test_*.py          # Tests (25 passing)
```

**Session isolation:** CI uses `ci-{sha[:8]}-{job}-{run_attempt}` session IDs. Baseline identified by `main-latest` Langfuse tag. Bootstrap: exit 0 + JSON artifact when no baseline exists.

**CLI flags:** `--baseline-tag` (Langfuse tag), `--current-session` (session_id), `--output` (JSON artifact, required). Old `--hours`/`--baseline`/`--current` removed.
