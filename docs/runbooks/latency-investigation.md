# Runbook: LLM Latency Investigation

**Issue:** #147 — Slow-thinking latency breakdown
**Last Updated:** 2026-02-12

## Quick Commands

```bash
# Check latency metrics (last 24h)
uv run python scripts/setup_langfuse_dashboards.py

# Check with alert thresholds
uv run python scripts/setup_langfuse_dashboards.py --check-alerts

# JSON output for automation
uv run python scripts/setup_langfuse_dashboards.py --json --hours 6

# Run trace validation (full pipeline)
uv run python scripts/validate_traces.py --report
```

## Step 1: Detect — Is There a Latency Problem?

### Automated Detection

The metrics script checks these thresholds:

| Metric | WARNING | CRITICAL |
|--------|---------|----------|
| `llm_ttft_ms` p95 | > 2000 ms | > 5000 ms |
| `llm_decode_ms` p95 | > 3000 ms | — |
| `llm_queue_ms` p95 | > 1000 ms | > 3000 ms |
| `llm_tps` p50 | < 20 tps | — |
| `llm_timeout` avg | — | > 5% |
| `llm_stream_recovery` avg | > 10% | — |

### Manual Detection (Langfuse UI)

1. Open Langfuse: http://localhost:3001 (local) or cloud URL
2. Go to **Dashboards** → "LLM Latency Breakdown"
3. Look for spikes in TTFT, Decode, or Queue p95 trend lines
4. Check Timeout Rate bar chart for red bars

## Step 2: Find the Slow Trace

### Via Langfuse UI

1. **Traces** → Filter by time range of the spike
2. Sort by **Duration** (descending)
3. Look for traces with `latency_total_ms` score > 5000
4. Click on the trace to see timeline

### Via Langfuse API

```python
from langfuse import Langfuse
lf = Langfuse()
# List recent traces sorted by latency
traces = lf.api.trace.list(order_by="latency", order="DESC", limit=10)
for t in traces.data:
    print(f"{t.id}: {t.latency}ms - {t.input}")
```

### Via Scores Filter

1. **Scores** → Filter: `name = llm_ttft_ms`, sort by value DESC
2. Click trace_id to navigate to the slow trace

## Step 3: Determine the Bottleneck

Open the slow trace and check these scores:

```
Trace scores:
├── llm_timeout        → true = hard failure (go to Step 4a)
├── llm_queue_ms       → value present? Check magnitude
├── llm_ttft_ms        → time to first token
├── llm_decode_ms      → token generation time
├── llm_tps            → tokens per second
├── streaming_enabled  → was streaming active?
└── llm_stream_recovery → did streaming fall back?
```

### Decision Matrix

| llm_queue_ms | llm_ttft_ms | llm_decode_ms | llm_tps | Classification |
|-------------|-------------|---------------|---------|----------------|
| > 1000ms | any | any | any | **Queue-Bound** |
| < 500ms | > 2000ms | any | any | **TTFT-Bound (Prefill)** |
| < 500ms | < 2000ms | > 3000ms | < 20 | **Decode-Bound (Slow Model)** |
| < 500ms | < 2000ms | > 3000ms | >= 20 | **Response-Length-Bound** |
| < 500ms | < 2000ms | < 3000ms | >= 20 | **Not LLM — Check Retrieval** |
| N/A | 0.0 | N/A | N/A | **Non-streaming — Check node-generate span** |

### Non-LLM Bottlenecks

If LLM metrics are all normal, expand the trace timeline and check:

| Span | Normal p95 | If Slow |
|------|-----------|---------|
| `node-retrieve` | < 500ms | Qdrant timeout, BGE-M3 cold start |
| `node-rerank` | < 300ms | ColBERT service overloaded |
| `bge-m3-hybrid-embed` | < 200ms | BGE-M3 API timeout, cold start |
| `cache-semantic-check` | < 50ms | Redis connection issue |

## Step 4: Root Cause & Action

### 4a. Hard Timeout (`llm_timeout = true`)

**Symptoms:** `llm_timeout` = 1, no response generated, fallback answer used.

**Actions:**
1. Check LiteLLM proxy logs: `docker logs dev-litellm --tail 100`
2. Check provider status page (Cerebras)
3. Check `QDRANT_TIMEOUT` setting (default 30s)
4. If persistent: increase `GENERATE_MAX_TOKENS` timeout or switch model in LiteLLM config

### 4b. Queue-Bound (`llm_queue_ms > 1000ms`)

**Symptoms:** High queue time, normal TTFT and decode.

**Actions:**
1. Check LiteLLM rate limits: `curl http://localhost:4000/health`
2. Check if Cerebras is experiencing high demand (status page)
3. Consider off-peak scheduling for batch operations
4. Fallback: configure secondary model in LiteLLM routing

### 4c. TTFT-Bound (`llm_ttft_ms > 2000ms`, queue low)

**Symptoms:** Slow first token, but decode speed normal once started.

**Actions:**
1. Check input token count in trace metadata (`prompt_tokens`)
2. Review `context_docs_count` — are too many documents in context?
3. Check system prompt length via Langfuse Prompt Management
4. If context is bloated: lower `TOP_K` or tighten relevance thresholds

### 4d. Decode-Bound (`llm_tps < 20`)

**Symptoms:** Low tokens-per-second, high decode time.

**Actions:**
1. Check if model is under load (LiteLLM `/health` endpoint)
2. Compare with historical TPS trend in dashboard
3. Cold start? Check if first request after idle period
4. If persistent: escalate to provider or switch model

### 4e. Response-Length-Bound (`llm_tps >= 20`, decode > 3s)

**Symptoms:** Good speed but very long response.

**Actions:**
1. Check `answer_words` and `answer_chars` scores
2. Check `answer_to_question_ratio` — is response disproportionately long?
3. Review response length policy settings (#129)
4. Consider reducing `GENERATE_MAX_TOKENS` (default: 2048)

### 4f. Stream Recovery (`llm_stream_recovery = true`)

**Symptoms:** Streaming started but failed, fell back to non-streaming.

**Actions:**
1. Check trace for ERROR span on `node-generate`
2. Common cause: Telegram API rate limit on `edit_text` (300ms throttle)
3. Network interruption between bot and LiteLLM
4. If frequent: check Telegram bot error logs

## Step 5: Verify Fix

After applying fix:

1. Run validation: `uv run python scripts/validate_traces.py --report`
2. Check latency report: `uv run python scripts/setup_langfuse_dashboards.py`
3. Compare with baseline: `make baseline-compare`
4. Monitor dashboard for 24h to confirm regression resolved

## Escalation Criteria

| Condition | Action |
|-----------|--------|
| Timeout rate > 10% for > 1 hour | Page on-call, check provider |
| TTFT p95 > 5s for > 30 min | Investigate immediately |
| Queue p95 > 3s sustained | Contact provider support |
| TPS dropped to 0 | LiteLLM/provider outage, enable fallback model |
| All metrics normal but users report slow | Check Telegram delivery (`respond_node` span), network |

## Related Resources

- Design doc: `docs/plans/2026-02-12-langfuse-dashboards-design.md`
- Observability rules: `.claude/rules/observability.md`
- Trace validation: `scripts/validate_traces.py`
- Baseline module: `tests/baseline/`
- Alerting: `docs/ALERTING.md`
