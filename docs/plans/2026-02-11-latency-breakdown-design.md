# Design: Slow-Thinking Latency Breakdown (#147)

**Issue:** #147 | **Depends on:** #144 (closed) | **Related:** #143
**Goal:** Break down "why is response slow" into granular Langfuse scores — queue, decode, throughput, failure modes.

## Design Principles

1. **No false precision.** Emit a metric only when the measurement is reliable. Otherwise skip the score and write an `*_unavailable` flag.
2. **Honest semantics.** Non-streaming paths produce no decode/TPS scores — not zeros, not sentinels.
3. **Separate severity tiers.** Hard timeout, stream recovery, and general fallback are distinct signals.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Queue measurement | Server-timing headers only | No heuristics; TTFT ≠ queue. Fallback: skip + `queue_unavailable` |
| Non-streaming decode | Skip score + `decode_unavailable` | Can't split non-streaming into TTFT + decode |
| Timeout semantics | Hard fail only (`llm_timeout`) | Recovered streaming failures → `llm_stream_recovery` instead |
| Score absence | Don't write score (no -1/0 sentinels) | Sentinels poison aggregates and alerts |
| Flag data type | Langfuse BOOLEAN | Not NUMERIC 0/1 — cleaner queries, native SDK support |
| TTFT canonical field | `completion_start_time` on generation span | Langfuse's official TTFT representation, plus score for alerts |
| LiteLLM timeout config | Separate `timeout` + `stream_timeout` | Distinguishes "stuck before first token" from "slow decode" |

## Score Inventory

### New Scores (10 new → total 24)

| Score | Langfuse Type | When Written | When Skipped |
|-------|--------------|-------------|-------------|
| `llm_queue_ms` | NUMERIC | Server-timing headers present | No headers |
| `llm_queue_unavailable` | BOOLEAN | No server-timing headers | Headers present |
| `llm_decode_ms` | NUMERIC | Streaming + TTFT > 0 | Non-streaming |
| `llm_decode_unavailable` | BOOLEAN | Non-streaming or TTFT = 0 | Streaming with TTFT |
| `llm_tps` | NUMERIC | Streaming + token usage available | No usage or non-streaming |
| `llm_tps_unavailable` | BOOLEAN | No TPS data available | TPS written |
| `llm_timeout` | BOOLEAN | Always (hard fail = True) | — |
| `llm_stream_recovery` | BOOLEAN | Always when streaming attempted | Non-streaming path |
| `llm_fallback_used` | BOOLEAN | Always | — |
| `streaming_enabled` | BOOLEAN | Always | — |

### Existing Scores (unchanged)

`llm_ttft_ms` (NUMERIC), `llm_response_duration_ms` (NUMERIC), plus 12 others in `_write_langfuse_scores()`.

### Pairing Rule

Every conditional NUMERIC metric has a BOOLEAN `*_unavailable` counterpart. A trace has **either** the metric **or** the flag — never both, never neither.

## Data Flow

### 1. generate_node (measurement point)

```
LLM call start ─┬─ streaming path ────────────────────────────┐
                 │   t_stream_start = monotonic()               │
                 │   first chunk → ttft_ms = (now - start)*1000 │
                 │   last chunk  → decode_ms = dur - ttft       │
                 │   token usage → tps = tokens / (decode/1000) │
                 │   completion_start_time = datetime(first_chunk)│
                 │                                               │
                 ├─ non-streaming path ────────────────────────┐ │
                 │   response_duration_ms = elapsed*1000        │ │
                 │   decode_ms = None                           │ │
                 │   tps = None                                 │ │
                 │                                               │
                 ├─ stream failure → recovery ─────────────────┐ │
                 │   stream_recovery = True                     │ │
                 │   fallback to non-streaming                  │ │
                 │                                               │
                 └─ hard failure ──────────────────────────────┐ │
                    timeout = True                              │
                    no answer delivered                          │
```

### 2. Server-timing header parsing (generate_node)

```python
# После получения response headers от LiteLLM
# Если есть server-timing или x-queue-time:
headers = response_obj._headers  # или response.headers в streaming
queue_ms = parse_server_timing(headers)  # float | None
```

Формат зависит от провайдера. Cerebras может не отдавать. Если нет → `queue_ms = None`.

### 3. RAGState expansion

New fields in `telegram_bot/graph/state.py`:

```python
# Latency breakdown (#147)
llm_decode_ms: float | None        # response_duration - ttft (streaming only)
llm_tps: float | None              # completion_tokens / decode_seconds
llm_queue_ms: float | None         # from server-timing headers
llm_timeout: bool                  # hard fail, no answer
llm_stream_recovery: bool          # streaming failed → non-streaming saved
streaming_enabled: bool            # config at call time
```

### 4. Score writing (bot.py)

```python
def _write_langfuse_scores(state: RAGState, pipeline_wall_ms: float) -> None:
    # ... existing 14 scores ...

    # --- Latency breakdown (#147) ---
    _write_boolean("streaming_enabled", state.get("streaming_enabled", False))
    _write_boolean("llm_timeout", state.get("llm_timeout", False))
    _write_boolean("llm_fallback_used", state.get("llm_fallback_used", False))

    # Stream recovery: only when streaming was attempted
    if state.get("streaming_enabled"):
        _write_boolean("llm_stream_recovery", state.get("llm_stream_recovery", False))

    # Conditional NUMERIC + unavailable flags
    decode_ms = state.get("llm_decode_ms")
    if decode_ms is not None:
        _write_numeric("llm_decode_ms", decode_ms)
    else:
        _write_boolean("llm_decode_unavailable", True)

    tps = state.get("llm_tps")
    if tps is not None:
        _write_numeric("llm_tps", tps)
    else:
        _write_boolean("llm_tps_unavailable", True)

    queue_ms = state.get("llm_queue_ms")
    if queue_ms is not None:
        _write_numeric("llm_queue_ms", queue_ms)
    else:
        _write_boolean("llm_queue_unavailable", True)
```

### 5. Generation span enrichment

```python
# В generate_node, после получения first token:
langfuse_context.update_current_observation(
    completion_start_time=datetime.utcnow(),  # canonical TTFT
)
```

## Failure Matrix

| Scenario | `llm_timeout` | `llm_stream_recovery` | `llm_fallback_used` | decode/tps |
|----------|:---:|:---:|:---:|:---:|
| Streaming OK | F | F | F | Written |
| Streaming fail → non-streaming OK | F | T | T | Unavailable |
| Non-streaming OK | F | — | F | Unavailable |
| Hard fail (no answer) | T | F/T | T | Unavailable |
| Chitchat (no LLM) | F | — | F | Unavailable |

## Validation Integration

`scripts/validate_traces.py` — extend Phase 4 (streaming) and report:

- Aggregate `llm_decode_ms` p50/p95 from streaming runs
- Aggregate `llm_tps` p50/p95 from streaming runs
- Count `llm_timeout` and `llm_stream_recovery` occurrences
- Report `llm_queue_unavailable` rate (expect ~100% until provider adds headers)

No new Go/No-Go criteria yet — collect baseline data first.

## Testing

### Unit tests (test_bot_scores.py)

1. **Streaming path**: all NUMERIC scores written, no `*_unavailable` flags
2. **Non-streaming path**: `decode_unavailable`, `tps_unavailable`, `queue_unavailable` written; no NUMERIC decode/tps/queue
3. **Stream recovery**: `llm_stream_recovery=True`, `llm_fallback_used=True`, `llm_timeout=False`
4. **Hard timeout**: `llm_timeout=True`, no decode/tps scores
5. **Total score count**: 14 existing + up to 10 new (varies by path)

### Unit tests (test_generate_node.py)

1. **decode_ms calculation**: `response_duration_ms - ttft_ms` matches expected
2. **tps calculation**: `completion_tokens / (decode_ms / 1000)` matches expected
3. **completion_start_time**: set on generation span in streaming path
4. **Server-timing parsing**: extract queue_ms from headers (mock)
5. **Stream recovery flags**: set correctly on fallback path

## Out of Scope

- Langfuse dashboard/alert configuration (manual, after baseline data)
- p95 threshold alerts (need 1-2 weeks of data first)
- `rerank_cache_hit` (separate issue)
- `hyde_used` (not implemented yet)

## File Changes

| File | Change |
|------|--------|
| `telegram_bot/graph/state.py` | Add 6 new fields |
| `telegram_bot/graph/nodes/generate.py` | Compute decode_ms, tps, parse headers, set completion_start_time, failure flags |
| `telegram_bot/bot.py` | Write 10 new scores with BOOLEAN/NUMERIC types |
| `scripts/validate_traces.py` | Extend report with new metrics aggregation |
| `tests/unit/test_bot_scores.py` | 5 test scenarios for score paths |
| `tests/unit/test_generate_node.py` | 5 test scenarios for metric computation |
