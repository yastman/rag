# Langfuse Dashboards Design: LLM Latency Breakdown (#147)

**Date:** 2026-02-12
**Branch:** `chore/parallel-backlog/langfuse-147`
**Status:** Implementation

## Context

Issue #147 tracks slow-thinking latency breakdown. The runtime scores are already written to Langfuse traces:

| Score Name | Type | Source | When Written |
|------------|------|--------|--------------|
| `llm_queue_ms` | NUMERIC | `_extract_queue_ms_from_provider_headers()` | Provider reports queue time |
| `llm_ttft_ms` | NUMERIC | `generate_node` streaming timer | Always (0.0 if non-streaming) |
| `llm_decode_ms` | NUMERIC | `response_duration_ms - ttft_ms` | Streaming only, ttft > 0 |
| `llm_tps` | NUMERIC | `completion_tokens / (decode_ms / 1000)` | Streaming + decode > 0 |
| `llm_timeout` | BOOLEAN | Hard LLM failure flag | Always |
| `streaming_enabled` | BOOLEAN | Config check | Always |
| `llm_stream_recovery` | BOOLEAN | Streaming fallback to non-streaming | Always |
| `llm_queue_unavailable` | BOOLEAN | Paired flag when queue_ms is None | When queue_ms absent |
| `llm_decode_unavailable` | BOOLEAN | Paired flag when decode_ms is None | When decode_ms absent |
| `llm_tps_unavailable` | BOOLEAN | Paired flag when tps is None | When tps absent |

**What remains:** Dashboards, alerts, classification guide, investigation runbook.

## 1. Dashboard Layout

### Dashboard 1: LLM Latency Breakdown (Primary)

**Purpose:** At-a-glance view of where LLM time is spent.

| Panel | Chart Type | View | Metric | Dimensions | Filter |
|-------|-----------|------|--------|------------|--------|
| TTFT p95 Trend | Line (time series) | `scores-numeric` | `value` / `p95` | `timeDimension: day` | `name = llm_ttft_ms` |
| Decode p95 Trend | Line (time series) | `scores-numeric` | `value` / `p95` | `timeDimension: day` | `name = llm_decode_ms` |
| Queue p95 Trend | Line (time series) | `scores-numeric` | `value` / `p95` | `timeDimension: day` | `name = llm_queue_ms` |
| TPS Trend (avg) | Line (time series) | `scores-numeric` | `value` / `avg` | `timeDimension: day` | `name = llm_tps` |
| Timeout Rate | Bar (time series) | `scores-numeric` | `value` / `avg` | `timeDimension: day` | `name = llm_timeout` |
| Stream Recovery Rate | Bar (time series) | `scores-numeric` | `value` / `avg` | `timeDimension: day` | `name = llm_stream_recovery` |

### Dashboard 2: End-to-End Pipeline Latency

**Purpose:** Total latency with node-level breakdown context.

| Panel | Chart Type | View | Metric | Dimensions | Filter |
|-------|-----------|------|--------|------------|--------|
| Total Latency p50/p95 | Line (dual) | `scores-numeric` | `value` / `p50`, `p95` | `timeDimension: day` | `name = latency_total_ms` |
| Generate Node Latency | Line | `observations` | `latency` / `p95` | `timeDimension: day` | `name = node-generate` |
| Retrieve Node Latency | Line | `observations` | `latency` / `p95` | `timeDimension: day` | `name = node-retrieve` |
| Cache Hit Rate | Line | `scores-numeric` | `value` / `avg` | `timeDimension: day` | `name = semantic_cache_hit` |

### Dashboard 3: Availability & Reliability

| Panel | Chart Type | Metric | Filter |
|-------|-----------|--------|--------|
| Timeout % (daily) | Bar | `llm_timeout` avg | `streaming_enabled = 1` |
| Data Availability | Stacked bar | `llm_decode_unavailable` count | — |
| Queue Unavailable % | Bar | `llm_queue_unavailable` avg | — |

## 2. Alert Rules

Langfuse v3 Custom Dashboards do not have built-in alerting. Alerts are implemented via:
1. **Metrics API polling script** (`scripts/setup_langfuse_dashboards.py`) — runs on schedule
2. **Existing Telegram alerting stack** (`make monitoring-up`) — receives threshold violations

### Threshold Definitions

| Alert | Score | Aggregation | Threshold | Window | Severity |
|-------|-------|-------------|-----------|--------|----------|
| TTFT p95 High | `llm_ttft_ms` | p95 | > 2000 ms | 1 hour | WARNING |
| TTFT p95 Critical | `llm_ttft_ms` | p95 | > 5000 ms | 1 hour | CRITICAL |
| Decode p95 High | `llm_decode_ms` | p95 | > 3000 ms | 1 hour | WARNING |
| Queue p95 High | `llm_queue_ms` | p95 | > 1000 ms | 1 hour | WARNING |
| Queue p95 Critical | `llm_queue_ms` | p95 | > 3000 ms | 1 hour | CRITICAL |
| Timeout Rate | `llm_timeout` | avg | > 0.05 (5%) | 1 hour | CRITICAL |
| TPS Degradation | `llm_tps` | p50 | < 20 tps | 1 hour | WARNING |
| Stream Recovery Spike | `llm_stream_recovery` | avg | > 0.10 (10%) | 1 hour | WARNING |

### Rationale

- **TTFT 2s WARNING:** Current gate is `generate_p50_lt_2s` for full generation. TTFT should be well under that.
- **Queue 1s WARNING:** Queue time is provider-side. >1s indicates Cerebras/LiteLLM congestion.
- **Timeout 5%:** Any LLM hard failure rate above 5% is production-critical.
- **TPS 20:** Below 20 tokens/second indicates model slowdown (normal range: 40-80 tps for Cerebras).

## 3. Classification Guide: Queue-Bound vs Model-Bound

### Decision Tree

```
Slow trace detected (latency_total_ms p95 > threshold)
│
├─ llm_timeout = true?
│  └─ YES → Hard failure. Check LiteLLM logs, provider status page.
│
├─ llm_queue_ms available?
│  ├─ YES and queue_ms > 1000ms → QUEUE-BOUND
│  │  └─ Provider queue congestion. Consider:
│  │     - Different time window (off-peak)
│  │     - Fallback model in LiteLLM
│  │     - Rate limiting on bot side
│  │
│  └─ YES and queue_ms < 500ms → Not queue-bound, continue below
│
├─ llm_ttft_ms > 2000ms?
│  └─ YES → MODEL-BOUND (prefill phase)
│     └─ Slow prompt processing. Consider:
│        - Reduce context_docs_count (currently top-5)
│        - Shorten system prompt
│        - Check prompt token count in trace metadata
│
├─ llm_decode_ms > 3000ms AND llm_tps < 20?
│  └─ YES → MODEL-BOUND (decode phase)
│     └─ Slow token generation. Consider:
│        - Model load issues (cold start)
│        - Provider throttling
│        - Switch to faster model variant
│
├─ llm_decode_ms > 3000ms AND llm_tps >= 20?
│  └─ YES → RESPONSE-LENGTH-BOUND
│     └─ Normal speed, just long output. Consider:
│        - Reduce GENERATE_MAX_TOKENS
│        - Tighter response length policy (#129)
│
└─ All LLM metrics normal?
   └─ Check non-LLM nodes: retrieve, rerank, embeddings
      - node-retrieve p95 > 500ms → Qdrant/embedding bottleneck
      - node-rerank p95 > 500ms → ColBERT reranker bottleneck
      - cache miss → Expected for cold queries
```

### Summary Table

| Classification | Key Indicator | Root Cause | Action |
|---------------|---------------|------------|--------|
| Queue-Bound | `llm_queue_ms` > 1000ms | Provider queue congestion | Fallback model, rate limit, off-peak |
| TTFT-Bound (Prefill) | `llm_ttft_ms` > 2000ms, queue low | Slow prompt processing | Reduce context, shorter prompts |
| Decode-Bound (Slow) | `llm_decode_ms` high, `llm_tps` < 20 | Model generation slow | Provider issue, model switch |
| Response-Length-Bound | `llm_decode_ms` high, `llm_tps` >= 20 | Long output at normal speed | Reduce max_tokens, style policy |
| Retrieval-Bound | LLM metrics normal, node-retrieve slow | Qdrant/embedding latency | Check Qdrant, BGE-M3 service |
| Timeout | `llm_timeout` = true | Hard LLM failure | Check LiteLLM, provider status |

## 4. Langfuse Metrics API Queries

### Query: TTFT p95 (last 24 hours)

```json
{
  "view": "scores-numeric",
  "metrics": [{"measure": "value", "aggregation": "p95"}],
  "dimensions": [],
  "filters": [
    {"column": "name", "operator": "=", "value": "llm_ttft_ms", "type": "string"}
  ],
  "fromTimestamp": "2026-02-11T00:00:00Z",
  "toTimestamp": "2026-02-12T00:00:00Z"
}
```

### Query: All Latency Breakdown p95 (grouped by score name)

```json
{
  "view": "scores-numeric",
  "metrics": [
    {"measure": "value", "aggregation": "p95"},
    {"measure": "value", "aggregation": "p50"},
    {"measure": "count", "aggregation": "count"}
  ],
  "dimensions": [{"field": "name"}],
  "filters": [
    {"column": "name", "operator": "anyOf", "value": ["llm_ttft_ms", "llm_decode_ms", "llm_queue_ms", "llm_tps"], "type": "stringList"}
  ],
  "fromTimestamp": "2026-02-11T00:00:00Z",
  "toTimestamp": "2026-02-12T00:00:00Z"
}
```

### Query: Timeout Rate (daily trend)

```json
{
  "view": "scores-numeric",
  "metrics": [
    {"measure": "value", "aggregation": "avg"},
    {"measure": "count", "aggregation": "count"}
  ],
  "dimensions": [],
  "timeDimension": {"granularity": "day"},
  "filters": [
    {"column": "name", "operator": "=", "value": "llm_timeout", "type": "string"}
  ],
  "fromTimestamp": "2026-02-05T00:00:00Z",
  "toTimestamp": "2026-02-12T00:00:00Z"
}
```

## 5. UI Steps for Custom Dashboard Creation

### Step-by-Step (Langfuse UI)

1. Navigate to **Dashboards** in left sidebar
2. Click **+ New Dashboard**, name it "LLM Latency Breakdown"
3. Click **+ Add Widget**
4. Configure first widget (TTFT p95 Trend):
   - **Chart type:** Line
   - **View:** scores-numeric
   - **Metric:** value / p95
   - **Filter:** name = llm_ttft_ms
   - **Time dimension:** day
   - **Time range:** Last 7 days
5. Save widget, repeat for each panel from Dashboard 1 layout above
6. Arrange widgets using drag-and-drop layout
7. Repeat for Dashboard 2 (Pipeline Latency) and Dashboard 3 (Availability)

### Curated Dashboard Baseline

Langfuse provides curated dashboards for Latency and Cost. Start with the curated "Latency" dashboard, then customize by adding score-based widgets for the breakdown metrics.

## 6. Integration with Existing Infrastructure

### Existing Gates (from `validate_traces.py`)

| Gate | Current | Enhancement |
|------|---------|-------------|
| `generate_p50_lt_2s` | Full generation p50 < 2000ms | Add TTFT-specific gate when streaming validation available (#144) |
| `ttft_p50_lt_1000ms` | Streaming TTFT p50 < 1000ms | Already implemented, skipped when sample < 3 |

### Baseline Module Integration

The `tests/baseline/` module computes per-trace metrics. The latency breakdown scores (`llm_ttft_ms`, `llm_decode_ms`, `llm_queue_ms`) are already included in traces via `_write_langfuse_scores()` and picked up by `enrich_results_from_langfuse()`.

### Monitoring Stack

- `make monitoring-up` starts alerting stack
- `make monitoring-test-alert` validates Telegram alerting
- The metrics query script can be integrated as a periodic check

## 7. Data Availability Notes

- **`llm_queue_ms`:** Currently always `None` — `_extract_queue_ms_from_provider_headers()` returns `None` (stub). Will become available when Cerebras/LiteLLM exposes queue time headers.
- **`llm_decode_ms`:** Available only when streaming is enabled AND `ttft_ms > 0`.
- **`llm_tps`:** Available only when `decode_ms > 0` AND `completion_tokens` is reported.
- **`llm_ttft_ms`:** Written as 0.0 for non-streaming; meaningful values only from streaming runs.

Dashboard widgets should handle missing data gracefully (empty charts rather than errors).
