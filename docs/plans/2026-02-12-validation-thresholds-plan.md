# fix(validation): Relax Brittle Thresholds and Improve Go/No-Go Reporting

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate false-positive Go/No-Go failures caused by normal variance, remove dead reference trace, and make thresholds config-driven.

**Architecture:** Extract all 10 hardcoded Go/No-Go thresholds from Python into a new `go_no_go` section in `tests/baseline/thresholds.yaml`. Remove the hardcoded reference trace comparison (superseded by #167 session-based baseline). Add stddev column to the report and explicit SKIP explanations.

**Tech Stack:** Python 3.12, pytest, PyYAML, numpy

**Issue:** #168

**Evidence Base (verified 2026-02-12):**
- Langfuse SDK docs (sampling, flush/shutdown, trace/session correlation, scores):
  - https://langfuse.com/docs/observability/sdk/advanced-features
  - https://langfuse.com/docs/observability/sdk/troubleshooting-and-faq
  - https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk
- Reliability alerting/SLO guidance (reduce false positives from noisy windows):
  - https://grafana.com/docs/grafana/latest/alerting/guides/best-practices/
  - https://grafana.com/docs/grafana-cloud/alerting-and-irm/slo/best-practices/
  - https://aws-observability.github.io/observability-best-practices/guides/operational/business/sla-percentile/
- Statistical framing for non-deterministic eval variance:
  - https://www.anthropic.com/research/statistical-approach-to-model-evals

---

## Summary of Changes

| Change | File(s) | Impact |
|--------|---------|--------|
| Config-driven Go/No-Go thresholds | `thresholds.yaml`, `validate_traces.py` | All 10 criteria become tunable |
| Widen LLM call factor 1.05 → 1.15 | `thresholds.yaml` | Reduces false positives |
| Remove reference trace `c2b95d86` | `validate_traces.py` | Removes dead comparison |
| Explicit SKIP explanation | `validate_traces.py` | Clearer reports |
| Stddev in report | `validate_traces.py` | Variance visibility |
| Rewrite tokens from config | `thresholds.yaml` | Model-aware threshold |

---

### Task 1: Add `go_no_go` Section to thresholds.yaml

**Files:**
- Modify: `tests/baseline/thresholds.yaml`
- Test: `tests/baseline/test_thresholds_schema.py` (create)

**Step 1: Write the failing test**

Create `tests/baseline/test_thresholds_schema.py`:

```python
"""Tests for thresholds.yaml schema completeness."""

from pathlib import Path

import pytest
import yaml

THRESHOLDS_PATH = Path(__file__).parent / "thresholds.yaml"


@pytest.fixture
def thresholds():
    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)


class TestThresholdsSchema:
    """Verify go_no_go section exists and has required keys."""

    REQUIRED_GO_NO_GO_KEYS = {
        "cold_p50_ms",
        "cold_p90_ms",
        "cold_over_10s_pct",
        "cache_hit_p50_ms",
        "generate_p50_ms",
        "multi_rewrite_pct",
        "rewrite_tokens_p50",
        "ttft_p50_ms",
        "ttft_min_sample",
    }

    def test_go_no_go_section_exists(self, thresholds):
        assert "go_no_go" in thresholds, "thresholds.yaml missing 'go_no_go' section"

    def test_go_no_go_has_all_keys(self, thresholds):
        go_no_go = thresholds["go_no_go"]
        missing = self.REQUIRED_GO_NO_GO_KEYS - set(go_no_go.keys())
        assert not missing, f"Missing go_no_go keys: {missing}"

    def test_go_no_go_values_are_positive(self, thresholds):
        go_no_go = thresholds["go_no_go"]
        for key in self.REQUIRED_GO_NO_GO_KEYS:
            assert go_no_go[key] > 0, f"go_no_go.{key} must be positive"

    def test_llm_factor_at_least_1_10(self, thresholds):
        """Issue #168: factor must be >= 1.10 to avoid false positives."""
        factor = thresholds["calls"]["llm_factor"]
        assert factor >= 1.10, f"llm_factor {factor} too tight, need >= 1.10"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/baseline/test_thresholds_schema.py -v`
Expected: FAIL — `go_no_go` section missing, `llm_factor` is 1.05

**Step 3: Update thresholds.yaml**

Add `go_no_go` section and widen `llm_factor`:

```yaml
# tests/baseline/thresholds.yaml
# Regression = current > baseline * factor
# Based on official observability/eval guidance (Langfuse docs, Grafana/AWS SLO, Anthropic stats)

latency:
  llm_p95_factor: 1.20        # 20% tolerance
  full_rag_p95_factor: 1.20
  qdrant_p95_factor: 1.30     # Vector DB has more variance
  ttft_p95_factor: 1.25       # Time to first token

cost:
  total_factor: 1.10          # 10% tolerance on total cost
  tokens_input_factor: 1.15   # 15% on input tokens
  tokens_output_factor: 1.15

cache:
  hit_rate_min_drop: 0.10     # Alert if drops >10% absolute
  semantic_hit_rate_min: 0.30 # Minimum semantic cache effectiveness

calls:
  llm_factor: 1.15            # 15% — was 1.05, widened per #168
  voyage_embed_factor: 1.10
  voyage_rerank_factor: 1.10

infrastructure:
  redis_memory_factor: 1.50   # 50% tolerance
  qdrant_vectors_factor: 1.20

# Go/No-Go criteria thresholds (validate_traces.py)
# Previously hardcoded, now config-driven per #168
go_no_go:
  cold_p50_ms: 5000           # Cold run p50 latency
  cold_p90_ms: 8000           # Cold run p90 latency
  cold_over_10s_pct: 0.15     # Max % of queries exceeding 10s
  cache_hit_p50_ms: 1500      # Cache-hit p50 latency
  generate_p50_ms: 2000       # Generate node p50 (non-streaming)
  multi_rewrite_pct: 0.10     # Max % of multi-rewrite queries
  rewrite_tokens_p50: 96      # Rewrite completion tokens p50
  ttft_p50_ms: 1000           # Streaming TTFT p50
  ttft_min_sample: 3          # Min samples for TTFT criterion
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/baseline/test_thresholds_schema.py -v`
Expected: PASS (4/4)

**Step 5: Commit**

```bash
git add tests/baseline/test_thresholds_schema.py tests/baseline/thresholds.yaml
git commit -m "feat(validation): add go_no_go config section and widen llm_factor to 1.15 #168"
```

---

### Task 2: Load Go/No-Go Thresholds from Config in evaluate_go_no_go

**Files:**
- Modify: `scripts/validate_traces.py:613-751` (evaluate_go_no_go function)
- Test: `tests/unit/test_validate_aggregates.py` (add/modify tests)

**Step 1: Write failing tests for config-driven thresholds**

Add to `tests/unit/test_validate_aggregates.py` in the `TestEvaluateGoNoGo` class:

```python
def test_custom_cold_p50_threshold(self):
    """Go/No-Go uses config threshold, not hardcoded 5000."""
    agg = {"cold": {"latency_p50": 6000}, "cache_hit": {}}
    # Default config: 5000 → FAIL
    result = evaluate_go_no_go(agg, [], thresholds={"cold_p50_ms": 5000})
    assert result["cold_p50_lt_5s"]["passed"] is False

    # Custom config: 7000 → PASS
    result = evaluate_go_no_go(agg, [], thresholds={"cold_p50_ms": 7000})
    assert result["cold_p50_lt_5s"]["passed"] is True

def test_custom_rewrite_tokens_threshold(self):
    """Rewrite tokens threshold loaded from config, not hardcoded 96."""
    r = _make_result(phase="cold", scores={"rewrite_completion_tokens": 110.0})
    agg = {"cold": {}, "cache_hit": {}}
    # Default: 96 → FAIL
    result = evaluate_go_no_go(agg, [r], thresholds={"rewrite_tokens_p50": 96})
    assert result["rewrite_tokens_p50_le_96"]["passed"] is False

    # Custom: 120 → PASS
    result = evaluate_go_no_go(agg, [r], thresholds={"rewrite_tokens_p50": 120})
    assert result["rewrite_tokens_p50_le_96"]["passed"] is True

def test_default_thresholds_from_yaml(self):
    """When no thresholds passed, loads from thresholds.yaml."""
    agg = {"cold": {"latency_p50": 4000}, "cache_hit": {}}
    result = evaluate_go_no_go(agg, [])
    # Should use yaml default (5000), so 4000 passes
    assert result["cold_p50_lt_5s"]["passed"] is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo::test_custom_cold_p50_threshold -v`
Expected: FAIL — `evaluate_go_no_go` doesn't accept `thresholds` param

**Step 3: Modify evaluate_go_no_go to accept thresholds**

In `scripts/validate_traces.py`, update the function signature and body.

Add at top of file (near other imports, around line 30):

```python
from pathlib import Path
import yaml

THRESHOLDS_PATH = Path(__file__).parent / "../tests/baseline/thresholds.yaml"


def _load_go_no_go_thresholds(
    custom: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load Go/No-Go thresholds from YAML, with optional overrides."""
    with open(THRESHOLDS_PATH) as f:
        defaults = yaml.safe_load(f).get("go_no_go", {})
    if custom:
        defaults.update(custom)
    return defaults
```

Update `evaluate_go_no_go` signature (line 613):

```python
def evaluate_go_no_go(
    aggregates: dict[str, Any],
    results: list[TraceResult],
    orphan_rate: float = 0.0,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
```

Add at start of function body (after docstring):

```python
    t = _load_go_no_go_thresholds(thresholds)
```

Replace all hardcoded values in criteria:

| Line | Old | New |
|------|-----|-----|
| 643 | `cold_p50 < 5000` | `cold_p50 < t.get("cold_p50_ms", 5000)` |
| 649 | `"< 8000 ms"` | `f"< {t.get('cold_p90_ms', 8000)} ms"` |
| 651 | `cold_p90 < 8000` | `cold_p90 < t.get("cold_p90_ms", 8000)` |
| 664 | `pct_over_10s < 0.15` | `pct_over_10s < t.get("cold_over_10s_pct", 0.15)` |
| 672 | `cache_p50 < 1500` | `cache_p50 < t.get("cache_hit_p50_ms", 1500)` |
| 680 | `generate_p50 < 2000` | `generate_p50 < t.get("generate_p50_ms", 2000)` |
| 692 | `multi_rewrite_pct <= 0.10` | `multi_rewrite_pct <= t.get("multi_rewrite_pct", 0.10)` |
| 704 | `tokens_p50 <= 96` | `tokens_p50 <= t.get("rewrite_tokens_p50", 96)` |
| 736 | `ttft_n < 3` | `ttft_n < t.get("ttft_min_sample", 3)` |
| 747 | `ttft_p50 < 1000` | `ttft_p50 < t.get("ttft_p50_ms", 1000)` |

Also update `target` strings to use `t` values so report reflects actual config.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo -v`
Expected: ALL PASS (existing + 3 new)

**Step 5: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "feat(validation): load Go/No-Go thresholds from config #168"
```

---

### Task 3: Remove Hardcoded Reference Trace

**Files:**
- Modify: `scripts/validate_traces.py` (lines 47-48, 754-790, 950-984, ~1186)

**Step 1: Write failing test**

Add to `tests/unit/test_validate_aggregates.py`:

```python
def test_report_has_no_reference_trace_header():
    """Issue #168: reference trace c2b95d86 removed from report."""
    # generate_report should not mention REFERENCE_TRACE_ID
    from scripts.validate_traces import REFERENCE_TRACE_ID
    # This import should fail after removal
    with pytest.raises(ImportError):
        pass  # placeholder — actual test below

# Alternative: test that generate_report output doesn't contain c2b95d86
def test_report_no_reference_trace_section(tmp_path):
    """Report should not contain Reference Trace Comparison section."""
    from scripts.validate_traces import generate_report, ValidationRun
    from datetime import datetime

    run = ValidationRun(
        run_id="test-123",
        git_sha="abc",
        started_at=datetime.now(),
        collections=["test"],
        skip_rerank_threshold=0.012,
    )
    output = tmp_path / "report.md"
    generate_report(
        run=run,
        results=[],
        aggregates={},
        output_path=output,
        reference_metrics=None,
        go_no_go=None,
    )
    content = output.read_text()
    assert "c2b95d86" not in content
    assert "Reference Trace Comparison" not in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::test_report_no_reference_trace_section -v`
Expected: FAIL — report still references `REFERENCE_TRACE_ID`

**Step 3: Remove reference trace code**

In `scripts/validate_traces.py`:

1. **Delete line 48:** `REFERENCE_TRACE_ID = "c2b95d86aa1f643b79016dd611c4691f"`

2. **Delete `fetch_reference_trace_metrics` function** (lines 754-790 approx) entirely.

3. **In `generate_report`** (line 963): Remove `Reference trace` from header:
   - Delete: `lines.append(f"**Reference trace:** \`{REFERENCE_TRACE_ID}\`")`

4. **In `generate_report`**: Remove "Reference Trace Comparison" section (lines 966-984):
   - Delete the entire `if reference_metrics:` block

5. **In `generate_report` signature**: Remove `reference_metrics` parameter. Update all callers.

6. **In `run_validation`** (~line 1186): Remove the call to `fetch_reference_trace_metrics()` and passing `reference_metrics` to `generate_report`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py -v`
Expected: ALL PASS

Also verify no broken imports:

Run: `uv run python -c "from scripts.validate_traces import evaluate_go_no_go, generate_report"`
Expected: No errors

**Step 5: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "fix(validation): remove dead reference trace c2b95d86 #168"
```

---

### Task 4: Improve SKIP Explanation in Report

**Files:**
- Modify: `scripts/validate_traces.py:1062-1063` (report formatting)
- Test: `tests/unit/test_validate_aggregates.py`

**Step 1: Write failing test**

Add to `tests/unit/test_validate_aggregates.py`:

```python
class TestGoNoGoReportFormat:
    """Test Go/No-Go report formatting in markdown."""

    def test_skipped_criterion_shows_reason(self):
        """Issue #168: SKIP must include explicit reason."""
        go_no_go = {
            "ttft_p50_lt_1000ms": {
                "target": "< 1000 ms",
                "actual": "N/A (n=2, need >= 3)",
                "passed": True,
                "skipped": True,
            }
        }
        # Format the criterion line
        from scripts.validate_traces import _format_go_no_go_status
        status = _format_go_no_go_status(go_no_go["ttft_p50_lt_1000ms"])
        assert "SKIPPED" in status
        assert "insufficient samples" in status.lower() or "n=" in status

    def test_pass_criterion_format(self):
        go_no_go_entry = {"target": "< 5000 ms", "actual": "3200 ms", "passed": True}
        from scripts.validate_traces import _format_go_no_go_status
        status = _format_go_no_go_status(go_no_go_entry)
        assert "PASS" in status

    def test_fail_criterion_format(self):
        go_no_go_entry = {"target": "< 5000 ms", "actual": "6100 ms", "passed": False}
        from scripts.validate_traces import _format_go_no_go_status
        status = _format_go_no_go_status(go_no_go_entry)
        assert "FAIL" in status
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestGoNoGoReportFormat -v`
Expected: FAIL — `_format_go_no_go_status` doesn't exist

**Step 3: Extract formatting helper and improve SKIP**

In `scripts/validate_traces.py`, add helper before `generate_report`:

```python
def _format_go_no_go_status(criterion: dict[str, Any]) -> str:
    """Format a single Go/No-Go criterion status for the report."""
    if criterion.get("skipped"):
        return f"[-] SKIPPED ({criterion['actual']})"
    elif criterion["passed"]:
        return "[x] PASS"
    else:
        return "[ ] **FAIL**"
```

Update `generate_report` (lines 1061-1068) to use the helper:

```python
        for i, (name, c) in enumerate(go_no_go.items(), 1):
            status = _format_go_no_go_status(c)
            lines.append(f"| {i} | {name} | {c['target']} | {c['actual']} | {status} |")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestGoNoGoReportFormat -v`
Expected: PASS (3/3)

**Step 5: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "fix(validation): explicit SKIPPED reason in Go/No-Go report #168"
```

---

### Task 5: Add Variance (stddev) Column to Go/No-Go Report

**Files:**
- Modify: `scripts/validate_traces.py` (aggregate computation + report)
- Test: `tests/unit/test_validate_aggregates.py`

**Step 1: Write failing test**

Add to `tests/unit/test_validate_aggregates.py`:

```python
def test_aggregates_include_stddev():
    """Issue #168: aggregates must include latency_stddev."""
    from scripts.validate_traces import compute_phase_aggregates

    results = [
        _make_result(phase="cold", latency_wall_ms=2000),
        _make_result(phase="cold", latency_wall_ms=3000),
        _make_result(phase="cold", latency_wall_ms=4000),
    ]
    agg = compute_phase_aggregates(results)
    cold = agg["cold"]
    assert "latency_stddev" in cold
    # stddev of [2000, 3000, 4000] ≈ 816.5
    assert 800 < cold["latency_stddev"] < 850
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::test_aggregates_include_stddev -v`
Expected: FAIL — `latency_stddev` not in aggregates

**Step 3: Add stddev to compute_phase_aggregates**

Locate `compute_phase_aggregates` in `scripts/validate_traces.py` (search for the function). Add after existing percentile computations:

```python
    phase_agg["latency_stddev"] = float(np.std(latencies)) if len(latencies) > 1 else 0.0
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::test_aggregates_include_stddev -v`
Expected: PASS

**Step 5: Add stddev to report output**

In `generate_report`, in the phase summary table (around line 999), add after latency p95:

```python
        if "latency_stddev" in agg:
            lines.append(f"| latency stddev | {agg['latency_stddev']:.0f} ms |")
```

In the Go/No-Go table header (line 1059), add stddev column. Update to:

```python
        lines.append("| # | Criterion | Target | Actual | Stddev | Status |")
        lines.append("|---|-----------|--------|--------|--------|--------|")
```

For each criterion row, pull stddev from aggregates if available:

```python
        for i, (name, c) in enumerate(go_no_go.items(), 1):
            status = _format_go_no_go_status(c)
            stddev = c.get("stddev", "—")
            lines.append(
                f"| {i} | {name} | {c['target']} | {c['actual']} | {stddev} | {status} |"
            )
```

**Step 6: Pass stddev into Go/No-Go criteria**

In `evaluate_go_no_go`, add stddev to relevant criteria dicts. Example for cold_p50:

```python
    cold_stddev = cold.get("latency_stddev", 0)
    criteria["cold_p50_lt_5s"] = {
        "target": f"< {t.get('cold_p50_ms', 5000)} ms",
        "actual": f"{cold_p50:.0f} ms",
        "passed": cold_p50 < t.get("cold_p50_ms", 5000),
        "stddev": f"±{cold_stddev:.0f} ms" if cold_stddev else "—",
    }
```

Apply same pattern to cold_p90, cache_hit_p50, generate_p50, ttft_p50.

**Step 7: Run all tests**

Run: `uv run pytest tests/unit/test_validate_aggregates.py -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "feat(validation): add stddev column to Go/No-Go report #168"
```

---

### Task 6: Final Verification and Docs

**Files:**
- Modify: `.claude/rules/observability.md` (update thresholds table)
- Run: full test suite

**Step 1: Run unit tests**

Run: `uv run pytest tests/unit/test_validate_aggregates.py tests/unit/test_validate_queries.py tests/baseline/ -v`
Expected: ALL PASS

**Step 2: Run lint and type checks**

Run: `make check`
Expected: PASS (ruff + mypy clean)

**Step 3: Update observability docs**

In `.claude/rules/observability.md`, update the Thresholds table to mention config-driven Go/No-Go:

```markdown
## Thresholds (regression detection)

| Metric | Threshold | Description |
|--------|-----------|-------------|
| LLM p95 latency | +20% | Alert if latency increases |
| Total cost | +10% | Alert if cost increases |
| Cache hit rate | -10% | Alert if cache effectiveness drops |
| LLM calls | +15% | Alert if call count increases (widened from 5% per #168) |

Config: `tests/baseline/thresholds.yaml` (includes `go_no_go` section for validate_traces.py)
```

Remove reference trace mention from the Trace Validation section:

```markdown
## Trace Validation (#110, #143)

`scripts/validate_traces.py` uses `@observe`, `propagate_attributes`, `update_current_trace`
for headless LangGraph runs. After flush, `enrich_results_from_langfuse()` fetches scores +
node spans by trace_id via Langfuse API.

Go/No-Go thresholds are config-driven via `tests/baseline/thresholds.yaml` `go_no_go` section (#168).
```

**Step 4: Commit**

```bash
git add .claude/rules/observability.md
git commit -m "docs(observability): update thresholds docs for #168"
```

---

## Checklist

- [ ] Task 1: `go_no_go` section in `thresholds.yaml` + `llm_factor: 1.15`
- [ ] Task 2: `evaluate_go_no_go` reads thresholds from config
- [ ] Task 3: Remove `REFERENCE_TRACE_ID` and `fetch_reference_trace_metrics`
- [ ] Task 4: Explicit SKIPPED reason in Go/No-Go report
- [ ] Task 5: Stddev column in Go/No-Go report table
- [ ] Task 6: Tests pass, lint clean, docs updated

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Existing tests break from signature change | `thresholds` param is optional with default |
| YAML path not found in CI | Use `Path(__file__).parent` relative resolution |
| Report format change breaks downstream | Report is markdown for humans, not parsed |
| Widening llm_factor hides real regressions | 15% is still tight; stddev gives context |

## Not In Scope

- Statistical significance test (Welch's t-test) — overkill for n < 30 traces per run. Factor + stddev is sufficient.
- Dynamic baseline from `main-latest` tag — already done in #167 session isolation.
- Per-collection thresholds — YAGNI, can add later if needed.
