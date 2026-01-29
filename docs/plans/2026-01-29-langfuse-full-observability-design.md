# Langfuse Full Observability Design

**Date:** 2026-01-29
**Status:** Ready for implementation
**Author:** Claude + User collaboration

## Overview

Complete observability setup: all Docker services running locally, full Langfuse tracing across the RAG pipeline, quality scores for baseline comparison, and e2e test validation.

## Current State

### Docker Services (15 containers)

| Service | Port | Status |
|---------|------|--------|
| PostgreSQL | 5432 | ✅ Ready |
| Redis | 6379 | ✅ Ready |
| Qdrant | 6333 | ✅ Ready |
| BGE-M3 | 8000 | ✅ Ready |
| BM42 | 8002 | ✅ Ready |
| USER-base | 8003 | ✅ Ready |
| Docling | 5001 | ✅ Ready |
| LightRAG | 9621 | ✅ Ready |
| ClickHouse | 8123 | ✅ Ready |
| MinIO | 9090 | ✅ Ready |
| Redis-Langfuse | 6380 | ✅ Ready |
| Langfuse Worker | - | ✅ Ready |
| Langfuse Web | 3001 | ✅ Ready |
| MLflow | 5000 | ✅ Ready |
| LiteLLM | 4000 | ✅ Ready |

### Langfuse Integration Status

**Already instrumented (11 spans):**

| Service | Spans | Type |
|---------|-------|------|
| VoyageService | 5 | `as_type="generation"` + `update_current_generation()` |
| QdrantService | 2 | `@observe` |
| CacheService | 4 | `@observe` |

**NOT instrumented (critical gaps):**

| Service | Methods | Impact |
|---------|---------|--------|
| Bot handlers | `handle_query()` | No root trace — spans are disconnected |
| LLMService | `stream_answer()`, `generate_answer()` | No LLM latency/tokens visibility |
| QueryAnalyzer | `analyze()` | No filter extraction tracing |
| QueryRouter | `classify_query()` | No classification decision tracing |

**Main problem:** `handle_query()` in `bot.py:167` has no `@observe` — all child spans are currently disconnected, not forming a unified trace.

## Best Practices 2026 (from Exa + Langfuse docs)

### 1. Root Trace on Entry Point

```python
from langfuse.decorators import observe, langfuse_context

@observe()  # Root trace - all child spans auto-connect
async def handle_query(message: Message):
    langfuse_context.update_current_trace(
        name="telegram-message",
        user_id=str(message.from_user.id),
        session_id=f"chat:{message.chat.id}",
        tags=["telegram", "rag"],
    )
```

### 2. Nested Spans with `as_type`

```python
@observe(name="llm-generate", as_type="generation")  # LLM calls
@observe(name="qdrant-search", as_type="retrieval")   # Vector search
@observe(name="cache-check")                          # Generic spans
```

### 3. LiteLLM Auto-Integration

Already configured in `docker/litellm/config.yaml`:
```yaml
litellm_settings:
  callbacks: ["langfuse_otel"]
```

### 4. Scores for Quality Tracking

```python
langfuse.score(
    trace_id=langfuse_context.get_current_trace_id(),
    name="cache_hit",
    value=1.0 if cache_hit else 0.0,
)
```

## Implementation Phases

### Phase 0: Preflight Check (30 min)

| Task | Command | Success Criteria |
|------|---------|------------------|
| Start Docker stack | `docker compose -f docker-compose.dev.yml up -d` | All 15 services healthy |
| Check Langfuse UI | `open http://localhost:3001` | Login works |
| Create API keys | Langfuse UI → Settings → API Keys | `pk-lf-*`, `sk-lf-*` in `.env` |
| Smoke test | `make test-smoke` | All tests green |

### Phase 1: Root Trace (1 hour)

| File | Change |
|------|--------|
| `telegram_bot/bot.py` | Add `@observe()` on `handle_query()` |
| `telegram_bot/bot.py` | Add `langfuse_context.update_current_trace()` with user_id, session_id, tags |

**Test:** Send bot message, verify trace appears in Langfuse UI with child spans.

### Phase 2: LLM Observability (1 hour)

| File | Change |
|------|--------|
| `telegram_bot/services/llm.py` | `@observe(name="llm-generate-answer", as_type="generation")` |
| `telegram_bot/services/llm.py` | `@observe(name="llm-stream-answer", as_type="generation")` |
| `telegram_bot/services/llm.py` | `update_current_observation()` with input/output/usage |
| `telegram_bot/services/query_analyzer.py` | `@observe(name="query-analyzer", as_type="generation")` |
| `telegram_bot/services/query_router.py` | `@observe(name="query-router")` on `classify_query()` |

**Test:** `pytest tests/unit/services/test_llm_observability.py -v`

### Phase 3: Scores & Infrastructure Metrics (1 hour)

| File | Change |
|------|--------|
| `telegram_bot/bot.py` | Add `langfuse.score()` at end of handle_query |
| `tests/baseline/collector.py` | Add `collect_infrastructure_metrics()` |
| `tests/baseline/collector.py` | Redis INFO (hit_rate, evictions) |
| `tests/baseline/collector.py` | Qdrant /metrics parsing |

**Scores to track:**

| Score Name | Type | Description |
|------------|------|-------------|
| `semantic_cache_hit` | BOOLEAN | 1.0 if cache hit |
| `results_count` | NUMERIC | Number of documents found |
| `query_type` | NUMERIC | 0=CHITCHAT, 1=SIMPLE, 2=COMPLEX |
| `rerank_applied` | BOOLEAN | 1.0 if rerank was applied |
| `latency_total_ms` | NUMERIC | Total processing time |

### Phase 4: E2E Validation (1 hour)

| File | Change |
|------|--------|
| `tests/e2e/test_langfuse_traces.py` | New test: verify trace structure |
| `tests/baseline/test_e2e_baseline.py` | Test: compare current vs baseline |
| `Makefile` | Add `test-e2e-traces` target |

**Success criteria:**
- Each e2e test creates trace in Langfuse
- Trace contains all 8 expected spans
- Scores are recorded correctly
- `make baseline-compare` shows diff

### Phase 5: Data Masking (30 min)

| File | Change |
|------|--------|
| `telegram_bot/services/__init__.py` | Add `configure_langfuse_masking()` |
| `telegram_bot/main.py` | Call masking config at startup |

```python
def mask_pii(data: dict) -> dict:
    """Mask user IDs, phone numbers, emails before sending to Langfuse."""
    return masked_data

from langfuse import Langfuse
langfuse = Langfuse(mask=mask_pii)
```

## Files to Modify

```
telegram_bot/
├── bot.py                          # Phase 1, 3: Root trace + scores
├── main.py                         # Phase 5: Masking config
└── services/
    ├── llm.py                      # Phase 2: @observe on generate/stream
    ├── query_analyzer.py           # Phase 2: @observe on analyze
    └── query_router.py             # Phase 2: @observe on classify_query

tests/
├── baseline/
│   ├── collector.py                # Phase 3: Infrastructure metrics
│   └── test_e2e_baseline.py        # Phase 4: Baseline comparison
├── e2e/
│   └── test_langfuse_traces.py     # Phase 4: Trace validation (NEW)
└── unit/services/
    └── test_llm_observability.py   # Phase 2: Unit tests (NEW)

Makefile                            # Phase 4: New targets
```

## Target Trace Structure

```
telegram-rag-query (TRACE)
│
├── Metadata:
│   ├── user_id: "123456789"
│   ├── session_id: "chat:987654321"
│   └── tags: ["telegram", "rag", "production"]
│
├── query-router (SPAN)
│   └── output: {type: "COMPLEX"}
│
├── cache-semantic-check (SPAN)
│   └── output: {hit: false, latency_ms: 12}
│
├── voyage-embed-query (GENERATION)
│   ├── model: "voyage-4-lite"
│   └── usage: {input: 15, output: 1024}
│
├── cache-search-check (SPAN)
│   └── output: {hit: false}
│
├── qdrant-hybrid-search-rrf (SPAN)
│   └── output: {results: 10, latency_ms: 45}
│
├── voyage-rerank (GENERATION)
│   ├── model: "rerank-2.5"
│   └── output: {reranked: 3}
│
├── llm-generate-answer (GENERATION)  ← Via LiteLLM OTEL
│   ├── model: "gpt-oss-120b"
│   └── usage: {input: 1200, output: 350, cost: 0.002}
│
├── cache-semantic-store (SPAN)
│   └── latency_ms: 8
│
└── Scores:
    ├── semantic_cache_hit: 0.0
    ├── results_count: 10.0
    ├── query_type: 2.0 (COMPLEX)
    └── latency_total_ms: 1250.0
```

## Definition of Done

| Criterion | How to Verify |
|-----------|---------------|
| All Docker services healthy | `docker ps --format "{{.Names}}: {{.Status}}"` |
| Langfuse UI accessible | `curl http://localhost:3001/api/public/health` |
| Root trace created | Send bot message → trace in UI |
| All 8 spans in trace | Langfuse UI → Trace → Observations |
| LLM calls traced | Span `llm-generate-answer` with usage |
| Scores recorded | Langfuse UI → Trace → Scores tab |
| E2E test passes | `pytest tests/e2e/test_langfuse_traces.py` |
| Baseline comparison | `make baseline-compare` no regressions |
| Unit tests | `pytest tests/unit/ -v` (1584+ tests) |

## References

- [Langfuse Python Decorators](https://langfuse.com/docs/sdk/python/decorators)
- [Langfuse Trace IDs & Distributed Tracing](https://langfuse.com/docs/observability/features/trace-ids-and-distributed-tracing)
- [LiteLLM Langfuse OTEL Integration](https://docs.litellm.ai/docs/observability/langfuse_otel_integration)
- [Best Practices: LLM Evaluation and Observability](https://github.com/Dicklesworthstone/claude_code_agent_farm/blob/main/best_practices_guides/LLM_EVALUATION_AND_OBSERVABILITY_BEST_PRACTICES.md)
