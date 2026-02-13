# Design: Streaming Validation Phase (#144)

**Issue:** #144 (parent: #143, related: #147)
**Scope:** Add streaming phase to `validate_traces.py` for real TTFT measurement
**Out of scope:** #147 latency breakdown scores (queue/decode/tps) — separate PR

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fake message fidelity | TTFT-only recorder | Minimal complexity; no Markdown/content validation |
| Phase order | warmup → cold → cache_hit → streaming | Warm caches isolate LLM TTFT from retrieval noise |
| TTFT threshold | p50 < 1000ms | Aggressive but realistic for Cerebras |
| N/A policy | `skipped=True` when n < 3 | Don't block on insufficient data, don't fake green |
| Query subset | First N (deterministic) | Stable p50 across runs, no shuffle |

## 1. FakeMessage / FakeSentMessage

Two classes in `scripts/validate_traces.py`:

```python
class FakeSentMessage:
    """Records edit_text calls for TTFT measurement."""
    def __init__(self):
        self.t_first_edit: float | None = None
        self.edit_calls_count: int = 0
        self.last_text_len: int = 0

    async def edit_text(self, text: str, **kwargs) -> None:
        self.edit_calls_count += 1
        self.last_text_len = len(text)
        if self.t_first_edit is None:
            self.t_first_edit = time.monotonic()

    async def delete(self) -> None:
        pass


class FakeMessage:
    """Minimal aiogram Message stand-in for streaming validation."""
    def __init__(self):
        self.t_answer_called: float | None = None
        self.sent: FakeSentMessage | None = None

    async def answer(self, text: str, **kwargs) -> FakeSentMessage:
        self.t_answer_called = time.monotonic()
        self.sent = FakeSentMessage()
        return self.sent
```

**TTFT calculation:** `sent.t_first_edit - message.t_answer_called` (ms).
If either timestamp is None or result < 0 → TTFT = None (excluded from aggregates).

## 2. Streaming Phase (Phase 4)

In `run_collection_validation`, after cache_hit:

```python
# Phase 4: Streaming TTFT (first 5 cold queries, deterministic)
streaming_queries = cold_queries[:5]
logger.info("Phase 4: Streaming TTFT (%d queries)", len(streaming_queries))
for q in streaming_queries:
    fake_msg = FakeMessage()
    result = await run_single_query(
        q, services, run_meta, phase="streaming", message=fake_msg,
    )
    # Extract TTFT from fake message timestamps
    if (fake_msg.t_answer_called is not None
            and fake_msg.sent is not None
            and fake_msg.sent.t_first_edit is not None):
        ttft = (fake_msg.sent.t_first_edit - fake_msg.t_answer_called) * 1000
        if ttft >= 0:
            result.state["streaming_ttft_ms"] = ttft
    results.append(result)
```

**`run_single_query` changes:**
- New `message: Any | None = None` param
- Pass to `build_graph(... message=message)`
- Force `config.streaming_enabled = True` when message is not None

## 3. Aggregation

New `"streaming"` phase in `compute_aggregates`:

```python
streaming_results = [r for r in results if r.phase == "streaming"]
ttft_values = [
    r.state["streaming_ttft_ms"]
    for r in streaming_results
    if r.state.get("streaming_ttft_ms") is not None
]
if ttft_values:
    aggregates["streaming"] = {
        "n": len(streaming_results),
        "ttft_sample_count": len(ttft_values),
        "ttft_p50": float(np.percentile(ttft_values, 50)),
        "ttft_p95": float(np.percentile(ttft_values, 95)),
        "ttft_mean": float(np.mean(ttft_values)),
        "ttft_max": float(np.max(ttft_values)),
    }
```

## 4. Go/No-Go Criterion #10

```python
# 10. Streaming TTFT p50 < 1000ms (skipped if sample < 3)
streaming = aggregates.get("streaming", {})
ttft_p50 = streaming.get("ttft_p50", None)
ttft_n = streaming.get("ttft_sample_count", 0)

if ttft_n < 3:
    criteria["ttft_p50_lt_1000ms"] = {
        "target": "< 1000 ms",
        "actual": f"N/A (n={ttft_n}, need >= 3)",
        "passed": True,
        "skipped": True,  # distinct from real PASS
    }
else:
    criteria["ttft_p50_lt_1000ms"] = {
        "target": "< 1000 ms",
        "actual": f"{ttft_p50:.0f} ms (n={ttft_n})",
        "passed": ttft_p50 < 1000,
        "skipped": False,
    }
```

Report renders `skipped` as `[-] SKIP` instead of `[x] PASS`.

## 5. Report Changes

- New "Streaming TTFT" section between Cache-Hit Run and Trace Details
- Shows ttft_p50/p95/mean/max + sample_count
- Go/No-Go table: 10 criteria (was 9), `[-] SKIP` for N/A
- Note updated: mentions streaming phase for real TTFT

## 6. Files Changed

| File | Change |
|------|--------|
| `scripts/validate_traces.py` | FakeMessage, Phase 4, aggregation, criterion, report |
| `tests/unit/test_validate_aggregates.py` | Tests for streaming aggregation, TTFT=None exclusion, skipped criterion |

## 7. Notes for #147

- Use Langfuse `completion_start_time` on generation span for native TTFT tracking
- Write queue/decode/tps as numeric scores on generate observation
- Build on streaming_ttft_ms data from this PR

## 8. Test Plan

| Test | Validates |
|------|-----------|
| `test_fake_message_records_ttft` | FakeMessage timestamps, TTFT calculation |
| `test_fake_message_no_edits_gives_none` | TTFT=None when no edit_text calls |
| `test_streaming_ttft_excluded_from_cold_aggregates` | Phase separation |
| `test_streaming_aggregates_exclude_none_ttft` | None filtering |
| `test_ttft_criterion_skip_on_small_sample` | n<3 → skipped=True |
| `test_ttft_criterion_pass_under_threshold` | p50 < 1000 → passed |
| `test_ttft_criterion_fail_over_threshold` | p50 >= 1000 → failed |
| `test_go_no_go_report_renders_skip_status` | `[-] SKIP` rendering |
