# Langfuse Full Observability Design

**Date:** 2026-01-29
**Status:** Ready for implementation
**Author:** Claude + User collaboration

## Overview

Complete observability setup with **cache-first pipeline**: all Docker services running locally, full Langfuse tracing across the RAG pipeline, quality scores for baseline comparison, and e2e test validation.

**Key principle:** "Log everything, but with masking" — all inputs/outputs go through PII redaction before Langfuse.

## Cache-First Pipeline (User → Response)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TELEGRAM UPDATE (Entry Span)                                               │
│  request_id, chat_id, lang, tenant, pipeline_version                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. QUERY ROUTER                                                            │
│  CHITCHAT → instant response (skip RAG)                                     │
│  SIMPLE/COMPLEX → continue pipeline                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. EXACT CACHE (KV)                                                        │
│  Fast GET for deterministic queries (commands, identical filters)           │
│  HIT → immediate response                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │ MISS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. SEMANTIC CACHE (RedisVL)                                                │
│  check(query, num_results=k) + metadata filter (tenant/lang/version)        │
│  HIT (distance < threshold) → response                                      │
│  BORDERLINE → continue to validation                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │ MISS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. EMBEDDINGS CACHE                                                        │
│  Exact-match embedding lookup (avoid Voyage API cost)                       │
│  HIT → use cached vector                                                    │
│  MISS → call Voyage API, cache result                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. RETRIEVAL (Qdrant)                                                      │
│  Hybrid search (dense + sparse + RRF fusion)                                │
│  Cache results with short TTL (retrieval_cache)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6. RERANK (Voyage)                                                         │
│  Rerank top candidates, cache results (rerank_cache, TTL 2h)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  7. LLM GENERATION                                                          │
│  Via LiteLLM → auto-traced to Langfuse (langfuse_otel callback)             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  8. STORE-BACK                                                              │
│  Save response to semantic cache (with metadata/versions)                   │
│  Update "hot" TTLs if needed                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Observability Strategy

**LLM calls:** LiteLLM → Langfuse via OTel callback `langfuse_otel` (auto-instrumentation)
**Everything else:** Manual spans via Langfuse SDK (caches, Qdrant, router, analyzer)

### Metrics to Track (Minimal, Useful)

| Layer | Span Attributes | Purpose |
|-------|-----------------|---------|
| **Cache spans** | `hit` (0/1), `layer` (semantic/emb/retr/rer), `ttl`, `key_prefix`, `distance`, `threshold`, `num_results` | Tune cache thresholds |
| **Redis health** | `keyspace_hits`, `keyspace_misses`, `evicted_keys`, `hit_rate` | Baseline/regression |
| **Qdrant** | `/metrics` (prometheus), search latency as span attribute | Baseline/regression |

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

## Data Masking (CRITICAL - Before Any Tracing)

**Rule 2026:** "Log everything, but only with masking enabled first."

Before sending ANY data to Langfuse, enable SDK-side masking:

```python
# telegram_bot/observability.py
import re
from typing import Any

def mask_pii(data: Any) -> Any:
    """Mask PII before sending to Langfuse.

    Applied to all inputs/outputs/metadata automatically.
    """
    if isinstance(data, str):
        # Mask Telegram user IDs (9-10 digits)
        data = re.sub(r'\b\d{9,10}\b', '[USER_ID]', data)
        # Mask phone numbers
        data = re.sub(r'\+?\d{10,15}', '[PHONE]', data)
        # Mask emails
        data = re.sub(r'[\w.-]+@[\w.-]+\.\w+', '[EMAIL]', data)
        # Truncate long texts (>500 chars)
        if len(data) > 500:
            data = data[:500] + '... [TRUNCATED]'
        return data
    elif isinstance(data, dict):
        return {k: mask_pii(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [mask_pii(item) for item in data]
    return data

# Initialize Langfuse with masking
from langfuse import Langfuse

def get_langfuse_client() -> Langfuse:
    """Get Langfuse client with PII masking enabled."""
    return Langfuse(
        mask=mask_pii,
        flush_at=50,      # Batch size
        flush_interval=5,  # Seconds
    )
```

**Reference:** [Langfuse Masking Docs](https://langfuse.com/docs/observability/features/masking)

## Implementation Phases

### Phase 0: Preflight + Masking Setup (30 min)

| Task | Command | Success Criteria |
|------|---------|------------------|
| Start Docker stack | `docker compose -f docker-compose.dev.yml up -d` | All 15 services healthy |
| Check Langfuse UI | `open http://localhost:3001` | Login works |
| Create API keys | Langfuse UI → Settings → API Keys | `pk-lf-*`, `sk-lf-*` in `.env` |
| **Create masking module** | `telegram_bot/observability.py` | `mask_pii()` function ready |
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

## Concrete TODO List (by file, in order)

### Step 1: Masking Module (NEW FILE)

**File:** `telegram_bot/observability.py` (NEW)

```python
# Create this file with:
# - mask_pii() function
# - get_langfuse_client() with masking enabled
# - configure_observability() initialization function
```

**Test:** `pytest tests/unit/test_observability_masking.py`

---

### Step 2: Root Trace in Bot Handler

**File:** `telegram_bot/bot.py`

```python
# Line ~1: Add imports
from langfuse.decorators import observe, langfuse_context
from .observability import get_langfuse_client

# Line ~167: Add decorator to handle_query
@observe()
async def handle_query(self, message: Message):
    # Line ~170: Add trace metadata (AFTER query = message.text)
    langfuse_context.update_current_trace(
        name="telegram-rag-query",
        user_id=str(message.from_user.id),
        session_id=f"chat:{message.chat.id}",
        metadata={
            "pipeline_version": "2.0",
            "lang": "ru",
        },
        tags=["telegram", "rag", "production"],
    )
```

**Test:** Send message to bot → verify trace in Langfuse UI.

---

### Step 3: Cache Spans Enhancement

**File:** `telegram_bot/services/cache.py`

Existing `@observe` decorators need enhanced metadata:

```python
# Line ~259: check_semantic_cache - add layer info
@observe(name="cache-semantic-check")
async def check_semantic_cache(...):
    # After line ~310 (after results check):
    langfuse_context.update_current_observation(
        output={
            "hit": bool(results),
            "layer": "semantic",
            "distance": results[0].get("vector_distance") if results else None,
            "threshold": effective_threshold,
        }
    )

# Similar for: cache-search-check, cache-rerank-check
# Add: layer, hit, ttl, key_prefix
```

---

### Step 4: LLM Service Instrumentation

**File:** `telegram_bot/services/llm.py`

```python
# Line ~1: Add imports
from langfuse.decorators import observe, langfuse_context

# Line ~38: Add decorator
@observe(name="llm-generate-answer", as_type="generation")
async def generate_answer(self, question: str, context_chunks: list, ...):
    # Line ~55 (after building messages):
    langfuse_context.update_current_observation(
        input={"question_preview": question[:100], "context_count": len(context_chunks)},
        model=self.model,
    )

    # Line ~100 (after response):
    langfuse_context.update_current_observation(
        usage={
            "input": data.get("usage", {}).get("prompt_tokens", 0),
            "output": data.get("usage", {}).get("completion_tokens", 0),
        },
        output={"answer_length": len(answer)},
    )

# Line ~113: Similar for stream_answer
@observe(name="llm-stream-answer", as_type="generation")
async def stream_answer(...):
    # Track at start and end of stream
```

---

### Step 5: QueryAnalyzer Instrumentation

**File:** `telegram_bot/services/query_analyzer.py`

```python
# Add imports at top
from langfuse.decorators import observe, langfuse_context

# Find analyze() method, add decorator:
@observe(name="query-analyzer", as_type="generation")
async def analyze(self, query: str) -> dict:
    langfuse_context.update_current_observation(
        input={"query_preview": query[:100]},
        model=self.model,
    )
    # ... existing code ...
    langfuse_context.update_current_observation(
        output={"filters": result.get("filters", {}), "has_semantic": bool(result.get("semantic_query"))},
    )
    return result
```

---

### Step 6: QueryRouter Instrumentation

**File:** `telegram_bot/services/query_router.py`

```python
# Add imports at top
from langfuse.decorators import observe, langfuse_context

# Find classify_query function, add decorator:
@observe(name="query-router")
def classify_query(query: str) -> QueryType:
    result = _classify(query)
    langfuse_context.update_current_observation(
        input={"query_preview": query[:50]},
        output={"type": result.value},
    )
    return result
```

---

### Step 7: Scores in Bot Handler

**File:** `telegram_bot/bot.py`

```python
# At end of handle_query (before final return), add:
from langfuse import get_client

# After line ~370 (after cache_service.store_semantic_cache):
langfuse = get_client()
trace_id = langfuse_context.get_current_trace_id()

if trace_id:
    langfuse.score(trace_id=trace_id, name="semantic_cache_hit", value=1.0 if cached_answer else 0.0)
    langfuse.score(trace_id=trace_id, name="results_count", value=float(len(results)) if results else 0.0)
    langfuse.score(trace_id=trace_id, name="query_type", value=float({"CHITCHAT": 0, "SIMPLE": 1, "COMPLEX": 2}.get(query_type.value, 1)))
```

---

### Step 8: Infrastructure Metrics Collector

**File:** `tests/baseline/collector.py`

```python
# Add method to LangfuseMetricsCollector class:

async def collect_infrastructure_metrics(self) -> dict:
    """Collect Redis INFO + Qdrant /metrics for baseline."""
    import httpx

    metrics = {}

    # Redis INFO
    if self.redis:
        info = await self.redis.info()
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        metrics["redis"] = {
            "keyspace_hits": hits,
            "keyspace_misses": misses,
            "evicted_keys": info.get("evicted_keys", 0),
            "used_memory_human": info.get("used_memory_human"),
            "hit_rate": round(hits / (hits + misses) * 100, 2) if (hits + misses) > 0 else 0,
        }

    # Qdrant /metrics
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{self.qdrant_url}/metrics", timeout=5)
            metrics["qdrant_raw"] = resp.text[:2000]  # Store raw for baseline
        except Exception as e:
            metrics["qdrant_error"] = str(e)

    return metrics
```

---

### Step 9: E2E Trace Validation Test (NEW FILE)

**File:** `tests/e2e/test_langfuse_traces.py` (NEW)

```python
"""E2E test: verify Langfuse traces are created correctly."""
import asyncio
import pytest
from langfuse import Langfuse

@pytest.mark.e2e
async def test_rag_query_creates_full_trace():
    """Verify e2e query creates complete Langfuse trace."""
    # 1. Send message via Telethon (or direct bot call)
    # 2. Wait for Langfuse processing
    await asyncio.sleep(3)

    # 3. Fetch recent traces
    langfuse = Langfuse()
    traces = langfuse.fetch_traces(tags=["telegram", "rag"], limit=1)

    assert len(traces) > 0, "No traces found"
    trace = traces[0]

    # 4. Verify span structure
    span_names = {obs.name for obs in trace.observations}
    expected_spans = {
        "query-router",
        "cache-semantic-check",
        "voyage-embed-query",
        "qdrant-hybrid-search-rrf",
    }
    assert expected_spans.issubset(span_names), f"Missing spans: {expected_spans - span_names}"

    # 5. Verify scores
    score_names = {s.name for s in trace.scores}
    assert "semantic_cache_hit" in score_names
    assert "results_count" in score_names
```

---

### Step 10: Makefile Targets

**File:** `Makefile`

```makefile
# Add these targets:

test-e2e-traces:
	pytest tests/e2e/test_langfuse_traces.py -v

baseline-create:
	python -m tests.baseline.cli create --tag $(TAG)

baseline-compare:
	python -m tests.baseline.cli compare --baseline $(BASELINE_TAG) --current $(CURRENT_TAG)
```

## Execution Order Summary

| Order | File | Change | Depends On |
|-------|------|--------|------------|
| 1 | `telegram_bot/observability.py` | NEW: masking + client | - |
| 2 | `telegram_bot/bot.py` | Root `@observe` + trace metadata | Step 1 |
| 3 | `telegram_bot/services/cache.py` | Enhance existing spans | Step 2 |
| 4 | `telegram_bot/services/llm.py` | Add `@observe` decorators | Step 2 |
| 5 | `telegram_bot/services/query_analyzer.py` | Add `@observe` | Step 2 |
| 6 | `telegram_bot/services/query_router.py` | Add `@observe` | Step 2 |
| 7 | `telegram_bot/bot.py` | Add scores at end | Steps 2-6 |
| 8 | `tests/baseline/collector.py` | Infrastructure metrics | - |
| 9 | `tests/e2e/test_langfuse_traces.py` | NEW: trace validation | Steps 1-7 |
| 10 | `Makefile` | New targets | Steps 8-9 |

## References

- [Langfuse Python Decorators](https://langfuse.com/docs/sdk/python/decorators)
- [Langfuse Trace IDs & Distributed Tracing](https://langfuse.com/docs/observability/features/trace-ids-and-distributed-tracing)
- [Langfuse Masking](https://langfuse.com/docs/observability/features/masking)
- [LiteLLM Langfuse OTEL Integration](https://docs.litellm.ai/docs/observability/langfuse_otel_integration)
- [Redis Semantic Cache Optimization](https://redis.io/blog/10-techniques-for-semantic-cache-optimization/)
- [Redis INFO Command](https://redis.io/docs/latest/commands/info/)
- [Qdrant Cluster Monitoring](https://qdrant.tech/documentation/cloud/cluster-monitoring/)
- [Best Practices: LLM Evaluation and Observability](https://github.com/Dicklesworthstone/claude_code_agent_farm/blob/main/best_practices_guides/LLM_EVALUATION_AND_OBSERVABILITY_BEST_PRACTICES.md)
