# Streaming Validation Phase (#144) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add streaming validation phase with FakeMessage to measure real TTFT in `validate_traces.py`.

**Architecture:** FakeMessage mimics aiogram Message interface (answer/edit_text/delete) to capture TTFT timestamps. New Phase 4 (streaming) runs after cache_hit with first 5 cold queries, forced streaming. New Go/No-Go criterion `ttft_p50_lt_1000ms` with skipped flag for n<3.

**Tech Stack:** Python 3.12, numpy, pytest, scripts/validate_traces.py

**Design doc:** `docs/plans/2026-02-11-streaming-validation-design.md`

---

### Task 1: FakeMessage — failing tests

**Files:**
- Create tests in: `tests/unit/test_validate_aggregates.py` (append to existing)

**Step 1: Write failing tests for FakeMessage / FakeSentMessage**

Add to `tests/unit/test_validate_aggregates.py`:

```python
import time

import pytest


class TestFakeMessage:
    """FakeMessage / FakeSentMessage for streaming TTFT measurement."""

    async def test_answer_records_timestamp_and_returns_sent(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        assert msg.t_answer_called is None
        assert msg.sent is None

        sent = await msg.answer("placeholder")
        assert msg.t_answer_called is not None
        assert msg.sent is sent

    async def test_edit_text_records_first_edit_timestamp(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        sent = await msg.answer("placeholder")
        assert sent.t_first_edit is None

        await sent.edit_text("chunk 1")
        t1 = sent.t_first_edit
        assert t1 is not None
        assert sent.edit_calls_count == 1
        assert sent.last_text_len == 7  # len("chunk 1")

        await sent.edit_text("chunk 1 more")
        assert sent.t_first_edit == t1  # first edit unchanged
        assert sent.edit_calls_count == 2
        assert sent.last_text_len == 12

    async def test_ttft_calculation_positive(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        sent = await msg.answer("placeholder")
        # Simulate small delay
        await sent.edit_text("first chunk")

        ttft = (sent.t_first_edit - msg.t_answer_called) * 1000
        assert ttft >= 0

    async def test_no_edits_gives_none_ttft(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        sent = await msg.answer("placeholder")
        # No edit_text calls
        assert sent.t_first_edit is None
        # TTFT should be None — caller must check

    async def test_delete_is_noop(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        sent = await msg.answer("placeholder")
        await sent.delete()  # should not raise
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestFakeMessage -v`
Expected: FAIL — `ImportError: cannot import name 'FakeMessage'`

---

### Task 2: FakeMessage — implementation

**Files:**
- Modify: `scripts/validate_traces.py` (add classes after `COLLECTIONS_TO_CHECK`, around line 51)

**Step 1: Implement FakeMessage and FakeSentMessage**

Add after line 50 (`COLLECTIONS_TO_CHECK = [...]`):

```python
class FakeSentMessage:
    """Records edit_text calls for TTFT measurement.

    Minimal aiogram sent-message stand-in: tracks first edit timestamp
    and call count without Telegram I/O.
    """

    def __init__(self) -> None:
        self.t_first_edit: float | None = None
        self.edit_calls_count: int = 0
        self.last_text_len: int = 0

    async def edit_text(self, text: str, **kwargs: Any) -> None:
        self.edit_calls_count += 1
        self.last_text_len = len(text)
        if self.t_first_edit is None:
            self.t_first_edit = time.monotonic()

    async def delete(self) -> None:
        pass


class FakeMessage:
    """Minimal aiogram Message stand-in for streaming validation.

    Provides answer() → FakeSentMessage with timestamp recording.
    TTFT = sent.t_first_edit - self.t_answer_called (seconds).
    """

    def __init__(self) -> None:
        self.t_answer_called: float | None = None
        self.sent: FakeSentMessage | None = None

    async def answer(self, text: str, **kwargs: Any) -> FakeSentMessage:
        self.t_answer_called = time.monotonic()
        self.sent = FakeSentMessage()
        return self.sent
```

Note: `time` and `Any` are already imported in the file.

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestFakeMessage -v`
Expected: 5 PASSED

**Step 3: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "feat(validation): add FakeMessage for streaming TTFT measurement #144"
```

---

### Task 3: Streaming aggregation — failing tests

**Files:**
- Modify: `tests/unit/test_validate_aggregates.py` (append)

**Step 1: Write failing tests for streaming TTFT aggregation**

```python
class TestStreamingAggregation:
    """Streaming TTFT aggregation in compute_aggregates."""

    def test_streaming_phase_produces_ttft_aggregates(self):
        """Streaming results with valid TTFT produce ttft_p50/p95/mean/max."""
        results = [
            _make_result(phase="streaming", latency=2000),
            _make_result(phase="streaming", latency=2100),
            _make_result(phase="streaming", latency=1900),
        ]
        # Inject streaming_ttft_ms into state
        results[0].state["streaming_ttft_ms"] = 400.0
        results[1].state["streaming_ttft_ms"] = 600.0
        results[2].state["streaming_ttft_ms"] = 500.0

        agg = compute_aggregates(results)

        assert "streaming" in agg
        s = agg["streaming"]
        assert s["n"] == 3
        assert s["ttft_sample_count"] == 3
        assert s["ttft_p50"] == pytest.approx(500.0, abs=1)
        assert s["ttft_mean"] == pytest.approx(500.0, abs=1)
        assert s["ttft_max"] == pytest.approx(600.0, abs=1)

    def test_streaming_excludes_none_ttft_from_aggregates(self):
        """Results with streaming_ttft_ms=None are excluded from TTFT stats."""
        results = [
            _make_result(phase="streaming", latency=2000),
            _make_result(phase="streaming", latency=2100),
            _make_result(phase="streaming", latency=1900),
        ]
        results[0].state["streaming_ttft_ms"] = 400.0
        results[1].state["streaming_ttft_ms"] = None  # no edit_text
        results[2].state["streaming_ttft_ms"] = 600.0

        agg = compute_aggregates(results)

        s = agg["streaming"]
        assert s["n"] == 3
        assert s["ttft_sample_count"] == 2  # only 2 valid
        assert s["ttft_p50"] == pytest.approx(500.0, abs=1)

    def test_streaming_not_mixed_into_cold(self):
        """Streaming results must not appear in cold aggregates."""
        results = [
            _make_result(phase="cold", latency=3000),
            _make_result(phase="streaming", latency=2000),
        ]
        results[1].state["streaming_ttft_ms"] = 500.0

        agg = compute_aggregates(results)

        assert agg["cold"]["n"] == 1
        assert agg["streaming"]["n"] == 1

    def test_no_streaming_results_no_streaming_key(self):
        """No streaming results → no 'streaming' key in aggregates."""
        results = [_make_result(phase="cold", latency=3000)]
        agg = compute_aggregates(results)
        assert "streaming" not in agg

    def test_all_none_ttft_no_streaming_key(self):
        """All streaming results with None TTFT → no 'streaming' key."""
        results = [
            _make_result(phase="streaming", latency=2000),
        ]
        # No streaming_ttft_ms set (defaults to missing from state)
        agg = compute_aggregates(results)
        assert "streaming" not in agg
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestStreamingAggregation -v`
Expected: FAIL — streaming results currently excluded by `for phase in ["cold", "cache_hit"]` loop

---

### Task 4: Streaming aggregation — implementation

**Files:**
- Modify: `scripts/validate_traces.py` — `compute_aggregates()` function (line 663-746)

**Step 1: Add streaming TTFT aggregation to compute_aggregates**

After line 744 (`aggregates[phase] = agg`) and before `return aggregates` (line 746), add:

```python
    # Streaming TTFT aggregation (separate from cold/cache_hit latency stats)
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

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestStreamingAggregation -v`
Expected: 5 PASSED

**Step 3: Run all existing tests to check no regressions**

Run: `uv run pytest tests/unit/test_validate_aggregates.py -v`
Expected: All PASSED (existing + new)

**Step 4: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "feat(validation): add streaming TTFT aggregation in compute_aggregates #144"
```

---

### Task 5: Go/No-Go criterion — failing tests

**Files:**
- Modify: `tests/unit/test_validate_aggregates.py` (append to `TestEvaluateGoNoGo`)

**Step 1: Write failing tests for ttft_p50_lt_1000ms criterion**

Add to existing `TestEvaluateGoNoGo` class:

```python
    def test_ttft_criterion_skip_on_small_sample(self):
        """n < 3 streaming samples → skipped=True, passed=True."""
        aggregates = {
            "cold": {"latency_p50": 3000, "latency_p90": 5000, "latency_p95": 6000, "node_p50": {"generate": 1500}},
            "cache_hit": {"latency_p50": 500},
            "streaming": {"n": 2, "ttft_sample_count": 2, "ttft_p50": 800.0},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        assert "ttft_p50_lt_1000ms" in criteria
        assert criteria["ttft_p50_lt_1000ms"]["skipped"] is True
        assert criteria["ttft_p50_lt_1000ms"]["passed"] is True

    def test_ttft_criterion_pass_under_threshold(self):
        """TTFT p50 < 1000ms with sufficient samples → passed."""
        aggregates = {
            "cold": {"latency_p50": 3000, "latency_p90": 5000, "latency_p95": 6000, "node_p50": {"generate": 1500}},
            "cache_hit": {"latency_p50": 500},
            "streaming": {"n": 5, "ttft_sample_count": 5, "ttft_p50": 700.0},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        c = criteria["ttft_p50_lt_1000ms"]
        assert c["passed"] is True
        assert c["skipped"] is False
        assert "700" in c["actual"]

    def test_ttft_criterion_fail_over_threshold(self):
        """TTFT p50 >= 1000ms → failed."""
        aggregates = {
            "cold": {"latency_p50": 3000, "latency_p90": 5000, "latency_p95": 6000, "node_p50": {"generate": 1500}},
            "cache_hit": {"latency_p50": 500},
            "streaming": {"n": 5, "ttft_sample_count": 5, "ttft_p50": 1200.0},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        c = criteria["ttft_p50_lt_1000ms"]
        assert c["passed"] is False
        assert c["skipped"] is False

    def test_ttft_criterion_no_streaming_data(self):
        """No streaming aggregates → skipped (n=0)."""
        aggregates = {
            "cold": {"latency_p50": 3000, "latency_p90": 5000, "latency_p95": 6000, "node_p50": {"generate": 1500}},
            "cache_hit": {"latency_p50": 500},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        assert criteria["ttft_p50_lt_1000ms"]["skipped"] is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo::test_ttft_criterion_skip_on_small_sample tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo::test_ttft_criterion_pass_under_threshold tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo::test_ttft_criterion_fail_over_threshold tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo::test_ttft_criterion_no_streaming_data -v`
Expected: FAIL — `KeyError: 'ttft_p50_lt_1000ms'`

---

### Task 6: Go/No-Go criterion — implementation

**Files:**
- Modify: `scripts/validate_traces.py` — `evaluate_go_no_go()` function (line 513-631)

**Step 1: Add ttft_p50_lt_1000ms criterion**

After the orphan_traces_zero criterion (line 629), before `return criteria` (line 631), add:

```python
    # 10. Streaming TTFT p50 < 1000ms (skipped if sample < 3)
    streaming = aggregates.get("streaming", {})
    ttft_p50 = streaming.get("ttft_p50")
    ttft_n = streaming.get("ttft_sample_count", 0)

    if ttft_n < 3:
        criteria["ttft_p50_lt_1000ms"] = {
            "target": "< 1000 ms",
            "actual": f"N/A (n={ttft_n}, need >= 3)",
            "passed": True,
            "skipped": True,
        }
    else:
        criteria["ttft_p50_lt_1000ms"] = {
            "target": "< 1000 ms",
            "actual": f"{ttft_p50:.0f} ms (n={ttft_n})",
            "passed": ttft_p50 < 1000,
            "skipped": False,
        }
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo -v`
Expected: All PASSED (existing 4 + new 4)

**Step 3: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "feat(validation): add ttft_p50_lt_1000ms Go/No-Go criterion with skipped flag #144"
```

---

### Task 7: Report — SKIP rendering and streaming section — failing tests

**Files:**
- Modify: `tests/unit/test_validate_aggregates.py` (append to `TestReportAndSummary`)

**Step 1: Write failing tests for report rendering**

Add to existing `TestReportAndSummary` class:

```python
    def test_go_no_go_renders_skip_status(self, tmp_path):
        """Skipped criteria render as '[-] SKIP', not '[x] PASS'."""
        run = ValidationRun(
            run_id="run-1",
            git_sha="abc123",
            started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            collections=["c1"],
            skip_rerank_threshold=0.012,
            relevance_threshold_rrf=0.005,
            results=[],
        )
        aggregates = {
            "cold": {
                "n": 1, "latency_p50": 100.0, "latency_p90": 130.0,
                "latency_p95": 150.0, "latency_mean": 110.0, "latency_max": 160.0,
                "semantic_cache_hit_rate": 0.0, "search_cache_hit_rate": 0.0,
                "rerank_applied_rate": 0.0, "rewrite_rate": 0.0,
                "results_count_mean": 20.0, "node_p50": {}, "node_p95": {},
            }
        }
        go_no_go = {
            "cold_p50_lt_5s": {"target": "< 5000 ms", "actual": "100 ms", "passed": True, "skipped": False},
            "ttft_p50_lt_1000ms": {"target": "< 1000 ms", "actual": "N/A (n=0, need >= 3)", "passed": True, "skipped": True},
        }
        out = tmp_path / "report.md"
        generate_report(run, aggregates, out, go_no_go=go_no_go)
        text = out.read_text(encoding="utf-8")

        assert "[-] SKIP" in text
        assert "[x] PASS" in text  # non-skipped criterion

    def test_report_includes_streaming_ttft_section(self, tmp_path):
        """Report includes Streaming TTFT section when streaming aggregates exist."""
        run = ValidationRun(
            run_id="run-1",
            git_sha="abc123",
            started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            collections=["c1"],
            skip_rerank_threshold=0.012,
            relevance_threshold_rrf=0.005,
            results=[],
        )
        aggregates = {
            "cold": {
                "n": 1, "latency_p50": 100.0, "latency_p90": 130.0,
                "latency_p95": 150.0, "latency_mean": 110.0, "latency_max": 160.0,
                "semantic_cache_hit_rate": 0.0, "search_cache_hit_rate": 0.0,
                "rerank_applied_rate": 0.0, "rewrite_rate": 0.0,
                "results_count_mean": 20.0, "node_p50": {}, "node_p95": {},
            },
            "streaming": {
                "n": 5, "ttft_sample_count": 5,
                "ttft_p50": 450.0, "ttft_p95": 800.0,
                "ttft_mean": 500.0, "ttft_max": 900.0,
            },
        }
        out = tmp_path / "report.md"
        generate_report(run, aggregates, out)
        text = out.read_text(encoding="utf-8")

        assert "## Streaming TTFT" in text
        assert "| ttft p50 | 450 ms |" in text
        assert "| sample count | 5 |" in text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestReportAndSummary::test_go_no_go_renders_skip_status tests/unit/test_validate_aggregates.py::TestReportAndSummary::test_report_includes_streaming_ttft_section -v`
Expected: FAIL — `[-] SKIP` not in report output, `## Streaming TTFT` not in report output

---

### Task 8: Report — SKIP rendering and streaming section — implementation

**Files:**
- Modify: `scripts/validate_traces.py` — `generate_report()` function (line 808-944)

**Step 1: Update Go/No-Go table rendering to handle `skipped` flag**

In `generate_report()`, find the Go/No-Go section (around line 909-911). Replace:

```python
            status = "[x] PASS" if c["passed"] else "[ ] **FAIL**"
```

with:

```python
            if c.get("skipped"):
                status = "[-] SKIP"
            elif c["passed"]:
                status = "[x] PASS"
            else:
                status = "[ ] **FAIL**"
```

**Step 2: Update the note at the bottom of Go/No-Go**

Replace the existing note (line 916-919):

```python
        lines.append(
            "_Note: `generate_p50_lt_2s` measures full generation latency in "
            "non-streaming validation mode; true TTFT requires a streaming phase._"
        )
```

with:

```python
        lines.append(
            "_Note: `generate_p50_lt_2s` measures full generation latency in "
            "non-streaming mode. `ttft_p50_lt_1000ms` measures real first-token "
            "latency from the streaming phase._"
        )
```

**Step 3: Add Streaming TTFT section**

After the cold/cache_hit phase loop (around line 880, before `# All trace details`), add:

```python
    # Streaming TTFT section
    streaming_agg = aggregates.get("streaming")
    if streaming_agg:
        lines.append(f"## Streaming TTFT (n={streaming_agg['n']})")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| ttft p50 | {streaming_agg['ttft_p50']:.0f} ms |")
        lines.append(f"| ttft p95 | {streaming_agg['ttft_p95']:.0f} ms |")
        lines.append(f"| ttft mean | {streaming_agg['ttft_mean']:.0f} ms |")
        lines.append(f"| ttft max | {streaming_agg['ttft_max']:.0f} ms |")
        lines.append(f"| sample count | {streaming_agg['ttft_sample_count']} |")
        lines.append("")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestReportAndSummary -v`
Expected: All PASSED (existing 2 + new 2)

**Step 5: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "feat(validation): render streaming TTFT section and [-] SKIP in report #144"
```

---

### Task 9: run_single_query — add message param

**Files:**
- Modify: `scripts/validate_traces.py` — `run_single_query()` function (line 219-320)

**Step 1: Add `message` parameter and wire to `build_graph`**

Change function signature (line 219-224) from:

```python
async def run_single_query(
    query: ValidationQuery,
    services: dict[str, Any],
    run_meta: dict[str, str],
    phase: str,
) -> TraceResult:
```

to:

```python
async def run_single_query(
    query: ValidationQuery,
    services: dict[str, Any],
    run_meta: dict[str, str],
    phase: str,
    *,
    message: Any | None = None,
) -> TraceResult:
```

**Step 2: Force streaming_enabled when message provided**

Inside `_run()`, before `build_graph()` call (around line 252), add:

```python
            # Force streaming when fake message provided
            if message is not None:
                config.streaming_enabled = True
```

**Step 3: Wire message to build_graph**

Change line 259 from:

```python
                message=None,  # no Telegram message — headless mode
```

to:

```python
                message=message,
```

**Step 4: Run all existing tests to ensure no regression**

Run: `uv run pytest tests/unit/test_validate_aggregates.py -v`
Expected: All PASSED (signature change is backward-compatible with `message=None` default)

**Step 5: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "feat(validation): add message param to run_single_query for streaming #144"
```

---

### Task 10: Streaming phase (Phase 4) in run_collection_validation

**Files:**
- Modify: `scripts/validate_traces.py` — `run_collection_validation()` function (line 354-411)

**Step 1: Add Phase 4 after cache_hit, before cleanup**

After the Phase 3 cache-hit loop (line 400-401) and before `# Cleanup` (line 403), add:

```python
    # Phase 4: Streaming TTFT (first 5 cold queries, deterministic)
    streaming_queries = cold_queries[:5]
    logger.info("Phase 4: Streaming TTFT (%d queries)", len(streaming_queries))
    for q in streaming_queries:
        fake_msg = FakeMessage()
        result = await run_single_query(
            q, services, run_meta, phase="streaming", message=fake_msg,
        )
        if (
            fake_msg.t_answer_called is not None
            and fake_msg.sent is not None
            and fake_msg.sent.t_first_edit is not None
        ):
            ttft = (fake_msg.sent.t_first_edit - fake_msg.t_answer_called) * 1000
            if ttft >= 0:
                result.state["streaming_ttft_ms"] = ttft
        results.append(result)
```

**Step 2: Run linter to verify**

Run: `uv run ruff check scripts/validate_traces.py`
Expected: No errors

**Step 3: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "feat(validation): add streaming Phase 4 with FakeMessage TTFT extraction #144"
```

---

### Task 11: Console logging for streaming phase

**Files:**
- Modify: `scripts/validate_traces.py` — `run_validation()` (line 952-1112)

**Step 1: Add streaming summary to console log output**

Find the console summary loop (line 1054-1055):

```python
    for phase, agg in aggregates.items():
        logger.info("%s", format_phase_summary(phase, agg))
```

Add after it:

```python
    # Streaming TTFT summary
    streaming_agg = aggregates.get("streaming")
    if streaming_agg:
        logger.info(
            "streaming TTFT (n=%d, samples=%d): p50=%.0fms p95=%.0fms mean=%.0fms",
            streaming_agg["n"],
            streaming_agg["ttft_sample_count"],
            streaming_agg["ttft_p50"],
            streaming_agg["ttft_p95"],
            streaming_agg["ttft_mean"],
        )
```

**Step 2: Include streaming phase in raw JSON output**

No changes needed — streaming results are already included in `all_results` which gets serialized.

**Step 3: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "feat(validation): add streaming TTFT console summary #144"
```

---

### Task 12: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/test_validate_aggregates.py tests/unit/test_validate_queries.py -v`
Expected: All PASSED

**Step 2: Run linter + types**

Run: `make check`
Expected: No errors

**Step 3: Verify streaming phase in format_phase_summary doesn't break**

The `format_phase_summary()` function expects `latency_p50`/`latency_p90`/`latency_p95`/`latency_mean` keys.
The streaming phase only has `ttft_*` keys. Verify that the existing `for phase, agg in aggregates.items()` loop won't crash on streaming — it will try to access `latency_p50` which doesn't exist.

Fix if needed: skip streaming phase in the general `format_phase_summary` loop:

```python
    for phase, agg in aggregates.items():
        if phase == "streaming":
            continue  # handled separately above
        logger.info("%s", format_phase_summary(phase, agg))
```

**Step 4: Final commit if any fixes needed**

```bash
git add scripts/validate_traces.py
git commit -m "fix(validation): skip streaming phase in format_phase_summary loop #144"
```
