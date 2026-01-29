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

### Phase 0: Preflight + Masking + Root Trace (1 hour)

**Goal:** All spans connect to single trace, PII masked before Langfuse.

| Task | File | Change |
|------|------|--------|
| Start Docker stack | - | `docker compose -f docker-compose.dev.yml up -d` |
| Create API keys | `.env` | `pk-lf-*`, `sk-lf-*` from Langfuse UI |
| Create masking module | `telegram_bot/observability.py` | `mask_pii()` + `get_langfuse_client()` |
| **Root trace** | `telegram_bot/bot.py:167` | `@observe(name="telegram-message")` on `handle_query()` |
| **Context fingerprint** | `telegram_bot/bot.py:170` | See below |

**Context Fingerprint (critical for cache isolation):**

```python
@observe(name="telegram-message")
async def handle_query(self, message: Message):
    query = message.text
    user_id = message.from_user.id

    # Context fingerprint for cache isolation + trace filtering
    context_fingerprint = {
        "tenant": "default",
        "lang": "ru",
        "prompt_version": "v2.1",
        "retrieval_version": f"{self.config.voyage_model_queries}-bm42-rrf",
        "rerank_version": self.config.voyage_model_rerank,
        "model_id": self.config.llm_model,
        "cache_schema": CACHE_SCHEMA_VERSION,  # "v2"
    }

    langfuse_context.update_current_trace(
        name="telegram-rag-query",
        user_id=str(user_id),
        session_id=f"chat:{message.chat.id}",
        metadata=context_fingerprint,
        tags=["telegram", "rag", context_fingerprint["retrieval_version"]],
    )
```

**Test:** Send message → verify trace in Langfuse UI with all child spans connected.

### Phase 1: Close CacheService Blind Spots (1 hour)

**Goal:** All 12 CacheService methods instrumented with consistent attributes.

| Method | Current | Add | Key Attributes |
|--------|---------|-----|----------------|
| `check_semantic_cache` | ✅ | enhance | `layer`, `hit`, `distance`, `threshold`, `num_results`, `filters_applied` |
| `store_semantic_cache` | ✅ | enhance | `layer`, `ttl`, `key_prefix` |
| `get_cached_embedding` | ❌ | **add** | `layer=embeddings`, `hit`, `model_name`, `dim` |
| `store_embedding` | ❌ | **add** | `layer=embeddings`, `model_name`, `dim` |
| `get_cached_sparse_embedding` | ❌ | **add** | `layer=sparse`, `hit`, `model_name` |
| `store_sparse_embedding` | ❌ | **add** | `layer=sparse`, `ttl` |
| `get_cached_analysis` | ❌ | **add** | `layer=analyzer`, `hit` |
| `store_analysis` | ❌ | **add** | `layer=analyzer`, `ttl` |
| `get_cached_search` | ✅ | enhance | `layer=retrieval`, `hit`, `index_version` |
| `store_search_results` | ❌ | **add** | `layer=retrieval`, `ttl`, `results_count` |
| `get_cached_rerank` | ✅ | enhance | `layer=rerank`, `hit` |
| `store_rerank_results` | ❌ | **add** | `layer=rerank`, `ttl` |

**Span attribute standard (all cache spans):**

```python
langfuse_context.update_current_observation(
    output={
        "layer": "semantic",      # semantic/embeddings/sparse/analyzer/retrieval/rerank
        "hit": True,              # bool
        "ttl": 7200,              # seconds
        "key_prefix": "sem:v2:",  # for debugging
        # Layer-specific:
        "distance": 0.12,         # semantic only
        "threshold": 0.20,        # semantic only
        "filters_applied": ["lang=ru", "tenant=default"],  # semantic only
    }
)
```

### Phase 2: LLM + Router + Analyzer Observability (1 hour)

**Goal:** Complete visibility into LLM costs and query preprocessing.

| File | Method | Decorator | Key Attributes |
|------|--------|-----------|----------------|
| `llm.py` | `generate_answer` | `@observe(name="llm-generate", as_type="generation")` | `model`, `input_tokens`, `output_tokens`, `latency_ms` |
| `llm.py` | `stream_answer` | `@observe(name="llm-stream", as_type="generation")` | `model`, `chunks_count`, `latency_ms` |
| `query_analyzer.py` | `analyze` | `@observe(name="query-analyzer", as_type="generation")` | `model`, `filters_extracted`, `has_semantic` |
| `query_router.py` | `classify_query` | `@observe(name="query-router")` | `query_type`, `confidence` |

**Note:** LLM calls via LiteLLM are auto-traced (`langfuse_otel` callback). These decorators add app-level context.

**Test:** `pytest tests/unit/services/test_llm_observability.py -v`

### Phase 2.5: Cache Calibration (NEW - 1 hour)

**Goal:** Two-threshold logic to reduce false-hits without losing recall.

**Problem:** Single threshold = either too many false-hits (low threshold) or too many cache misses (high threshold).

**Solution:** Two thresholds + borderline validation.

```python
# telegram_bot/services/cache.py

# Thresholds (configurable via env)
STRICT_THRESHOLD = 0.10      # Distance < 0.10 → confident hit, return immediately
BORDERLINE_THRESHOLD = 0.20  # Distance 0.10-0.20 → validate before returning
# Distance > 0.20 → miss, go to retrieval

@observe(name="cache-semantic-check")
async def check_semantic_cache(
    self,
    query: str,
    user_id: Optional[int] = None,
    language: str = "ru",
    context_fingerprint: Optional[dict] = None,  # NEW: for cache isolation
) -> Optional[str]:
    if not self.semantic_cache:
        return None

    # Build metadata filter from context_fingerprint
    filter_expr = Tag("language") == language
    if context_fingerprint:
        if "tenant" in context_fingerprint:
            filter_expr &= Tag("tenant") == context_fingerprint["tenant"]
        if "cache_schema" in context_fingerprint:
            filter_expr &= Tag("cache_schema") == context_fingerprint["cache_schema"]

    # Check with BORDERLINE threshold (wider net)
    results = await self.semantic_cache.acheck(
        prompt=query,
        filter_expression=filter_expr,
        num_results=3,  # Get top-3 for validation
        distance_threshold=BORDERLINE_THRESHOLD,
    )

    if not results:
        langfuse_context.update_current_observation(
            output={"hit": False, "layer": "semantic", "reason": "no_candidates"}
        )
        return None

    distance = results[0].get("vector_distance", 1.0)

    # STRICT HIT: confident, return immediately
    if distance < STRICT_THRESHOLD:
        langfuse_context.update_current_observation(
            output={
                "hit": True,
                "layer": "semantic",
                "hit_type": "strict",
                "distance": distance,
                "threshold": STRICT_THRESHOLD,
            }
        )
        return results[0].get("response")

    # BORDERLINE HIT: validate with light rerank
    if distance < BORDERLINE_THRESHOLD:
        is_valid = await self._validate_borderline_hit(query, results[0])
        if is_valid:
            langfuse_context.update_current_observation(
                output={
                    "hit": True,
                    "layer": "semantic",
                    "hit_type": "borderline_validated",
                    "distance": distance,
                }
            )
            return results[0].get("response")

    # MISS: go to retrieval
    langfuse_context.update_current_observation(
        output={
            "hit": False,
            "layer": "semantic",
            "reason": "borderline_rejected" if distance < BORDERLINE_THRESHOLD else "distance_too_high",
            "distance": distance,
        }
    )
    return None

async def _validate_borderline_hit(self, query: str, cached_result: dict) -> bool:
    """Light validation for borderline cache hits.

    Uses rerank score to verify semantic match.
    Cheaper than full retrieval, catches false positives.
    """
    try:
        # Quick rerank check (single doc)
        rerank_result = await self.voyage_service.rerank(
            query=query,
            documents=[cached_result.get("response", "")[:500]],  # Truncate
            top_k=1,
        )
        # If rerank score > 0.7, consider valid
        if rerank_result and rerank_result[0].get("score", 0) > 0.7:
            return True
    except Exception as e:
        logger.warning(f"Borderline validation failed: {e}")
    return False
```

**Threshold Tuning (RedisVL helper):**

```python
# scripts/tune_cache_threshold.py
from redisvl.extensions.cache.llm import SemanticCache

async def tune_threshold(cache: SemanticCache, test_queries: list[dict]):
    """Find optimal threshold using golden test set."""
    from redisvl.extensions.cache.utils import optimize_threshold

    # test_queries: [{"query": "...", "expected_hit": True/False}, ...]
    optimal = await optimize_threshold(
        cache=cache,
        test_data=test_queries,
        min_threshold=0.05,
        max_threshold=0.30,
        step=0.02,
    )
    print(f"Optimal threshold: {optimal}")
```

**Test:** `pytest tests/unit/services/test_cache_calibration.py -v`

### Phase 3: Baseline with Cold/Warm Paths + Infrastructure Metrics (1.5 hours)

**Goal:** Prove cache works (warm < cold), detect regressions via infra metrics.

#### 3.1 Cold vs Warm Path Tests

**Main contract:** "Second identical query is faster/cheaper than first."

```python
# tests/baseline/test_cache_paths.py

import pytest
from tests.baseline.collector import LangfuseMetricsCollector

GOLDEN_QUERIES = [
    "квартиры до 100000 евро",
    "3-комнатные в Солнечный берег",
    "студии рядом с морем",
]

@pytest.fixture
async def clean_caches(cache_service):
    """Flush all caches before cold-path test."""
    await cache_service.redis_client.flushdb()
    yield
    # Don't clean after - warm path needs data

@pytest.mark.parametrize("query", GOLDEN_QUERIES)
class TestCachePaths:

    @pytest.mark.order(1)
    async def test_cold_path(self, query, pipeline, clean_caches, collector):
        """First query: all cache misses, full pipeline."""
        result = await pipeline.process(query)

        # Verify cold-path behavior
        assert result.cache_hits["semantic"] == 0
        assert result.cache_hits["embeddings"] == 0
        assert result.latency_ms > 800  # Full pipeline is slow

        # Log to Langfuse for baseline
        collector.log_cold_path_metrics(query, result)

    @pytest.mark.order(2)
    async def test_warm_path(self, query, pipeline, collector):
        """Second query: cache hits, fast response."""
        result = await pipeline.process(query)

        # Verify warm-path behavior
        assert result.cache_hits["semantic"] >= 1 or result.cache_hits["embeddings"] >= 1
        assert result.latency_ms < 200  # 4x+ faster

        # Calculate speedup
        cold_latency = collector.get_cold_path_latency(query)
        speedup = cold_latency / result.latency_ms

        # Log to Langfuse for baseline
        collector.log_warm_path_metrics(query, result, speedup)

        # Fail if speedup is too low
        assert speedup > 3.0, f"Cache speedup too low: {speedup:.1f}x (expected >3x)"
```

#### 3.2 Infrastructure Metrics Collection

```python
# tests/baseline/collector.py

class LangfuseMetricsCollector:

    async def collect_infrastructure_metrics(self) -> dict:
        """Collect Redis INFO + Qdrant /metrics for baseline."""
        metrics = {"timestamp": datetime.utcnow().isoformat()}

        # Redis INFO stats
        if self.redis:
            info = await self.redis.info("stats")
            memory = await self.redis.info("memory")

            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses

            metrics["redis"] = {
                "keyspace_hits": hits,
                "keyspace_misses": misses,
                "hit_rate": round(hits / total * 100, 2) if total > 0 else 0,
                "evicted_keys": info.get("evicted_keys", 0),
                "expired_keys": info.get("expired_keys", 0),
                "used_memory_human": memory.get("used_memory_human"),
                "maxmemory_human": memory.get("maxmemory_human"),
                "fragmentation_ratio": memory.get("mem_fragmentation_ratio"),
            }

            # Alert if eviction is eating cache effectiveness
            if metrics["redis"]["evicted_keys"] > 100:
                logger.warning(f"High eviction count: {metrics['redis']['evicted_keys']}")

        # Qdrant /metrics (Prometheus format)
        if self.qdrant_url:
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get(f"{self.qdrant_url}/metrics", timeout=5)
                    raw_metrics = resp.text

                    # Parse key metrics
                    metrics["qdrant"] = {
                        "raw": raw_metrics[:3000],  # Store for baseline diff
                        "search_latency_p95": self._parse_histogram_p95(
                            raw_metrics, "qdrant_search_seconds"
                        ),
                        "points_total": self._parse_gauge(
                            raw_metrics, "qdrant_points_total"
                        ),
                    }
                except Exception as e:
                    metrics["qdrant"] = {"error": str(e)}

        return metrics

    def _parse_histogram_p95(self, raw: str, metric_name: str) -> Optional[float]:
        """Parse p95 from Prometheus histogram."""
        import re
        pattern = rf'{metric_name}_bucket{{le="0.95".*?}}\s+(\d+\.?\d*)'
        match = re.search(pattern, raw)
        return float(match.group(1)) if match else None

    def _parse_gauge(self, raw: str, metric_name: str) -> Optional[int]:
        """Parse gauge value from Prometheus format."""
        import re
        pattern = rf'{metric_name}\s+(\d+)'
        match = re.search(pattern, raw)
        return int(match.group(1)) if match else None
```

#### 3.3 Scores in Bot Handler

```python
# telegram_bot/bot.py (at end of handle_query)

from langfuse import get_client
import time

# At start of handle_query:
start_time = time.time()

# ... pipeline code ...

# At end, before return:
latency_ms = (time.time() - start_time) * 1000
langfuse = get_client()
trace_id = langfuse_context.get_current_trace_id()

if trace_id:
    # Cache effectiveness
    langfuse.score(trace_id=trace_id, name="semantic_cache_hit",
                   value=1.0 if cached_answer else 0.0)
    langfuse.score(trace_id=trace_id, name="embeddings_cache_hit",
                   value=1.0 if embedding_from_cache else 0.0)

    # Quality metrics
    langfuse.score(trace_id=trace_id, name="results_count",
                   value=float(len(results)) if results else 0.0)
    langfuse.score(trace_id=trace_id, name="query_type",
                   value=float({"CHITCHAT": 0, "SIMPLE": 1, "COMPLEX": 2}[query_type.value]))

    # Performance
    langfuse.score(trace_id=trace_id, name="latency_total_ms",
                   value=latency_ms)
    langfuse.score(trace_id=trace_id, name="cache_layers_hit",
                   value=float(sum([
                       1 if cached_answer else 0,
                       1 if embedding_from_cache else 0,
                       1 if search_from_cache else 0,
                   ])))
```

**Scores Summary:**

| Score | Type | Purpose |
|-------|------|---------|
| `semantic_cache_hit` | BOOLEAN | Track semantic cache effectiveness |
| `embeddings_cache_hit` | BOOLEAN | Track embedding cache effectiveness |
| `results_count` | NUMERIC | Monitor retrieval quality |
| `query_type` | NUMERIC | Segment by complexity |
| `latency_total_ms` | NUMERIC | Overall performance |
| `cache_layers_hit` | NUMERIC | How many cache layers contributed |

### Phase 4: E2E Validation + Regression Gate (1 hour)

**Goal:** E2E tests verify trace structure, baseline-compare blocks regressions.

#### 4.1 Trace Structure Validation

```python
# tests/e2e/test_langfuse_traces.py

import pytest
from langfuse import Langfuse

EXPECTED_SPANS = {
    "telegram-message",      # Root
    "query-router",          # Classification
    "cache-semantic-check",  # Semantic cache
    "cache-embeddings-get",  # Embeddings cache
    "voyage-embed-query",    # Embedding generation
    "qdrant-hybrid-search-rrf",  # Retrieval
    "voyage-rerank",         # Reranking
    "llm-generate",          # Answer generation (or via LiteLLM)
}

EXPECTED_SCORES = {
    "semantic_cache_hit",
    "results_count",
    "latency_total_ms",
}

@pytest.mark.e2e
async def test_trace_structure(bot_client, langfuse_client):
    """Verify e2e query creates complete trace with expected structure."""
    # 1. Send test message
    await bot_client.send_message("квартиры до 100000 евро")
    await asyncio.sleep(5)  # Wait for Langfuse processing

    # 2. Fetch recent trace
    traces = langfuse_client.fetch_traces(
        tags=["telegram", "rag"],
        limit=1,
    )
    assert len(traces) > 0, "No traces found in Langfuse"

    trace = traces[0]

    # 3. Verify spans
    span_names = {obs.name for obs in trace.observations}
    missing_spans = EXPECTED_SPANS - span_names
    assert not missing_spans, f"Missing spans: {missing_spans}"

    # 4. Verify scores
    score_names = {s.name for s in trace.scores}
    missing_scores = EXPECTED_SCORES - score_names
    assert not missing_scores, f"Missing scores: {missing_scores}"

    # 5. Verify context_fingerprint in metadata
    assert "retrieval_version" in trace.metadata
    assert "cache_schema" in trace.metadata

@pytest.mark.e2e
async def test_cold_warm_trace_comparison(bot_client, langfuse_client, cache_service):
    """Verify cold and warm paths produce different metrics."""
    query = "тестовый запрос для cold/warm"

    # Cold path
    await cache_service.redis_client.flushdb()
    await bot_client.send_message(query)
    await asyncio.sleep(5)

    cold_trace = langfuse_client.fetch_traces(limit=1)[0]
    cold_latency = next(s.value for s in cold_trace.scores if s.name == "latency_total_ms")
    cold_cache_hit = next(s.value for s in cold_trace.scores if s.name == "semantic_cache_hit")

    # Warm path
    await bot_client.send_message(query)
    await asyncio.sleep(5)

    warm_trace = langfuse_client.fetch_traces(limit=1)[0]
    warm_latency = next(s.value for s in warm_trace.scores if s.name == "latency_total_ms")
    warm_cache_hit = next(s.value for s in warm_trace.scores if s.name == "semantic_cache_hit")

    # Assertions
    assert cold_cache_hit == 0.0, "Cold path should have cache miss"
    assert warm_cache_hit == 1.0, "Warm path should have cache hit"
    assert warm_latency < cold_latency * 0.5, f"Warm should be 2x+ faster: {warm_latency} vs {cold_latency}"
```

#### 4.2 Baseline Comparison as Regression Gate

```python
# tests/baseline/test_regression_gate.py

import pytest
from tests.baseline.manager import BaselineManager

REGRESSION_THRESHOLDS = {
    "latency_p95_increase": 0.20,    # Max 20% latency increase
    "cache_hit_rate_decrease": 0.10, # Max 10% hit rate decrease
    "cost_increase": 0.10,           # Max 10% cost increase
    "error_rate_increase": 0.05,     # Max 5% error rate increase
}

@pytest.mark.baseline
async def test_no_regressions(baseline_manager: BaselineManager):
    """Block release if performance regressed vs baseline."""
    current = await baseline_manager.collect_current_metrics()
    baseline = await baseline_manager.load_baseline("latest")

    regressions = []

    # Check latency
    if current["latency_p95"] > baseline["latency_p95"] * (1 + REGRESSION_THRESHOLDS["latency_p95_increase"]):
        regressions.append(
            f"Latency p95 regressed: {baseline['latency_p95']:.0f}ms → {current['latency_p95']:.0f}ms"
        )

    # Check cache hit rate
    if current["cache_hit_rate"] < baseline["cache_hit_rate"] * (1 - REGRESSION_THRESHOLDS["cache_hit_rate_decrease"]):
        regressions.append(
            f"Cache hit rate dropped: {baseline['cache_hit_rate']:.1f}% → {current['cache_hit_rate']:.1f}%"
        )

    # Check cost
    if current["total_cost"] > baseline["total_cost"] * (1 + REGRESSION_THRESHOLDS["cost_increase"]):
        regressions.append(
            f"Cost increased: ${baseline['total_cost']:.2f} → ${current['total_cost']:.2f}"
        )

    assert not regressions, "Regressions detected:\n" + "\n".join(regressions)
```

#### 4.3 Makefile Targets

```makefile
# Makefile additions

# E2E trace validation
test-e2e-traces:
	pytest tests/e2e/test_langfuse_traces.py -v --tb=short

# Baseline management
baseline-create:
	python -m tests.baseline.cli create --tag $(shell date +%Y%m%d-%H%M%S)

baseline-compare:
	python -m tests.baseline.cli compare \
		--baseline $(BASELINE_TAG) \
		--current $(CURRENT_TAG) \
		--thresholds tests/baseline/thresholds.yaml

baseline-gate:
	pytest tests/baseline/test_regression_gate.py -v

# Pre-release check (blocks on regression)
pre-release: test-unit test-smoke baseline-gate
	@echo "✅ All checks passed, ready for release"
```

### Phase 5: Data Masking (Already in Phase 0)

**Note:** Masking is configured in Phase 0 (`telegram_bot/observability.py`). This phase just verifies it works.

```python
# tests/unit/test_observability_masking.py

import pytest
from telegram_bot.observability import mask_pii

def test_mask_user_id():
    data = {"user_id": "123456789", "text": "Hello"}
    masked = mask_pii(data)
    assert masked["user_id"] == "[USER_ID]"
    assert masked["text"] == "Hello"

def test_mask_phone():
    data = "Позвоните мне +79161234567"
    masked = mask_pii(data)
    assert "+79161234567" not in masked
    assert "[PHONE]" in masked

def test_mask_email():
    data = "Напишите на test@example.com"
    masked = mask_pii(data)
    assert "test@example.com" not in masked
    assert "[EMAIL]" in masked

def test_truncate_long_text():
    data = "x" * 1000
    masked = mask_pii(data)
    assert len(masked) <= 520  # 500 + "... [TRUNCATED]"
    assert "[TRUNCATED]" in masked
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

| Phase | Order | File | Change | Depends On |
|-------|-------|------|--------|------------|
| **0** | 1 | `telegram_bot/observability.py` | NEW: `mask_pii()` + `get_langfuse_client()` | - |
| **0** | 2 | `telegram_bot/bot.py:167` | `@observe(name="telegram-message")` + context_fingerprint | Step 1 |
| **1** | 3 | `telegram_bot/services/cache.py` | Add `@observe` to 8 missing methods | Step 2 |
| **1** | 4 | `telegram_bot/services/cache.py` | Enhance 4 existing spans with layer/hit/ttl | Step 3 |
| **2** | 5 | `telegram_bot/services/llm.py` | `@observe` on generate/stream | Step 2 |
| **2** | 6 | `telegram_bot/services/query_analyzer.py` | `@observe` on analyze | Step 2 |
| **2** | 7 | `telegram_bot/services/query_router.py` | `@observe` on classify_query | Step 2 |
| **2.5** | 8 | `telegram_bot/services/cache.py` | Two-threshold logic + borderline validation | Steps 3-4 |
| **3** | 9 | `telegram_bot/bot.py` | Add 6 scores at end of handle_query | Steps 5-7 |
| **3** | 10 | `tests/baseline/collector.py` | `collect_infrastructure_metrics()` | - |
| **3** | 11 | `tests/baseline/test_cache_paths.py` | NEW: cold/warm path tests | Step 10 |
| **4** | 12 | `tests/e2e/test_langfuse_traces.py` | NEW: trace structure validation | Steps 1-9 |
| **4** | 13 | `tests/baseline/test_regression_gate.py` | NEW: regression blocking | Steps 10-11 |
| **4** | 14 | `Makefile` | `baseline-*`, `pre-release` targets | Steps 11-13 |
| **5** | 15 | `tests/unit/test_observability_masking.py` | NEW: masking unit tests | Step 1 |

## PR Strategy (Suggested)

| PR | Files | Description |
|----|-------|-------------|
| **PR #1** | observability.py, bot.py | Root trace + masking + context_fingerprint |
| **PR #2** | cache.py | All 12 methods instrumented + two-threshold |
| **PR #3** | llm.py, query_analyzer.py, query_router.py | LLM + preprocessing spans |
| **PR #4** | bot.py (scores), collector.py | Scores + infrastructure metrics |
| **PR #5** | tests/baseline/*, tests/e2e/* | Cold/warm tests + trace validation + regression gate |
| **PR #6** | Makefile | `baseline-*`, `pre-release` targets |

## References

- [Langfuse Python Decorators](https://langfuse.com/docs/sdk/python/decorators)
- [Langfuse Trace IDs & Distributed Tracing](https://langfuse.com/docs/observability/features/trace-ids-and-distributed-tracing)
- [Langfuse Masking](https://langfuse.com/docs/observability/features/masking)
- [LiteLLM Langfuse OTEL Integration](https://docs.litellm.ai/docs/observability/langfuse_otel_integration)
- [Redis Semantic Cache Optimization](https://redis.io/blog/10-techniques-for-semantic-cache-optimization/)
- [Redis INFO Command](https://redis.io/docs/latest/commands/info/)
- [Qdrant Cluster Monitoring](https://qdrant.tech/documentation/cloud/cluster-monitoring/)
- [Best Practices: LLM Evaluation and Observability](https://github.com/Dicklesworthstone/claude_code_agent_farm/blob/main/best_practices_guides/LLM_EVALUATION_AND_OBSERVABILITY_BEST_PRACTICES.md)
