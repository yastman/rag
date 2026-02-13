# Design: CI Baseline Isolation (#167)

> **Issue:** [#167](https://github.com/yastman/rag/issues/167) — CI baseline-compare cross-PR contamination and bootstrap issues
> **Date:** 2026-02-12
> **Status:** Approved

## Problem

`tests/baseline/` comparison system has environment-dependent failure modes causing false regressions in CI:

1. **7-day lookback window** — `--hours=168` catches traces from unrelated PRs
2. **No session_id filtering** — `get_daily_metrics()` and `get_latency_metrics()` in `collector.py` don't filter by session, contaminating baseline comparison with ALL traces in the window
3. **Missing `main-latest` tag** — first PR in a new env always fails (no baseline)
4. **`.current_baseline` file** — file-based state in worktree (dirty-worktree class, same as #165)
5. **Fixed `session_id=baseline`** — no per-run isolation

## Solution: Per-Trace Computation with Session Isolation

### Architecture

**Current (broken):**
```
CI run → --hours=168 → metrics_daily API (ALL traces, no session filter) → compare
```

**New:**
```
CI run → current_session="ci-{sha}-{job}-{attempt}"
       → langfuse.api.trace.list(session_id=current_session)
       → fetch observations per trace (GENERATION type)
       → compute p50/p95/cost/count locally → compare
```

Replace aggregate Langfuse API calls (`metrics_daily`, `metrics_v_2`) with per-trace fetching via `langfuse.api.trace.list()` + `langfuse.api.observations.list()`. Compute metrics from individual observation data (latency, cost, tokens).

### Terminology

| Term | Meaning | Example |
|------|---------|---------|
| `current_session` | session_id for the current CI run | `ci-e947aa1f-baseline-compare-1` |
| `baseline_tag` | Langfuse tag identifying baseline traces | `main-latest` |

These are always separate concepts — never mixed.

### Session ID Format

```
ci-{sha[:8]}-{job_id}-{run_attempt}
```

In CI workflow (shell, not GitHub expression):
```bash
SHORT_SHA="${GITHUB_SHA::8}"
CURRENT_SESSION="ci-${SHORT_SHA}-${GITHUB_JOB}-${GITHUB_RUN_ATTEMPT}"
```

| Component | Source | Example |
|-----------|--------|---------|
| `sha[:8]` | `${GITHUB_SHA::8}` | `e947aa1f` |
| `job_id` | `${GITHUB_JOB}` | `baseline-compare` |
| `run_attempt` | `${GITHUB_RUN_ATTEMPT}` | `1` |

### Collector Rewrite

New `collect_session_metrics()` replaces 3 old aggregate methods:

```python
def collect_session_metrics(
    self, *, session_id: str | None = None, tag: str | None = None
) -> SessionMetrics:
    """Fetch traces + observations for a session/tag, compute metrics locally.

    Args:
        session_id: Filter by Langfuse session_id (for current run)
        tag: Filter by Langfuse tag (for baseline)

    At least one of session_id or tag must be provided.
    """
    # 1. Fetch traces (paginated, cursor-based)
    traces = self._fetch_all_traces(session_id=session_id, tags=[tag] if tag else None)

    # 2. For each trace, fetch observations
    #    langfuse.api.observations.list(trace_id=trace.id, type="GENERATION")

    # 3. Compute from observations (with None guards):
    #    - latency: obs.end_time - obs.start_time (skip if either is None)
    #    - cost: obs.calculated_total_cost (default 0.0 if None)
    #    - tokens: obs.usage.input / obs.usage.output (default 0 if None)
    #    - p50/p95: numpy.percentile() on valid latency values
    #    - cache: trace.metadata.get("cache_hit") (true/false)
    #    - LLM calls: count(observations where type="GENERATION")

    return SessionMetrics(...)
```

**None guards on observations:**
- `end_time` or `start_time` is None → skip this observation for latency computation
- `calculated_total_cost` is None → treat as 0.0
- `usage` is None → treat input/output tokens as 0
- Zero valid latency observations → p50/p95 = 0.0

**Old methods to remove:**
- `get_daily_metrics()` — replaced by trace-level cost/token aggregation
- `get_latency_metrics()` — replaced by observation-level latency computation
- `get_cache_metrics()` — replaced by trace metadata inspection

Keep infrastructure methods (`get_qdrant_metrics`, `get_redis_metrics`, `collect_infrastructure_metrics`) — they don't have the session isolation problem.

### Baseline Storage

**Remove `.current_baseline` file.** Replace with:

1. **Langfuse tag** `main-latest` — applied to traces from successful smoke runs on main
2. **CI artifact** — snapshot JSON uploaded for audit/debugging

`set-baseline` command → tags traces via Langfuse API instead of writing file.

### Bootstrap & Graceful Degradation

When `main-latest` baseline doesn't exist:

```python
baseline_traces = collector.fetch_all_traces(tags=["main-latest"])
if not baseline_traces:
    result = {
        "status": "skipped",
        "reason": "No baseline tagged 'main-latest' found",
        "recommendation": "Run smoke tests on main branch first",
    }
    # Write structured JSON for CI artifact
    Path(output).write_text(json.dumps(result, indent=2))
    click.secho("SKIP — no baseline found", fg="yellow")
    sys.exit(0)  # SKIP, not FAIL
```

Always write structured JSON to output path — even on skip — so CI artifact always has a reason.

### CI Workflow Changes

```yaml
baseline-compare:
  steps:
    - name: Run baseline comparison
      if: env.LANGFUSE_AVAILABLE == 'true'
      env:
        LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
        LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
        LANGFUSE_HOST: ${{ secrets.LANGFUSE_HOST }}
      run: |
        SHORT_SHA="${GITHUB_SHA::8}"
        CURRENT_SESSION="ci-${SHORT_SHA}-${GITHUB_JOB}-${GITHUB_RUN_ATTEMPT}"

        uv run python3 -m tests.baseline.cli compare \
          --baseline-tag="main-latest" \
          --current-session="${CURRENT_SESSION}" \
          --thresholds=tests/baseline/thresholds.yaml \
          --output=reports/baseline-${CURRENT_SESSION}.json

    - name: Upload baseline report
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: baseline-report
        path: reports/baseline-*.json
```

**Removed:** `--hours=168` (no longer needed — session/tag filtering is exact).
**Added:** `--output` for structured JSON artifact.

### File Changes

| File | Change |
|------|--------|
| `tests/baseline/collector.py` | New `collect_session_metrics()`, `_fetch_all_traces()`. Remove `get_daily_metrics`, `get_latency_metrics`, `get_cache_metrics` |
| `tests/baseline/manager.py` | `create_snapshot()` uses new `collect_session_metrics()`. `BaselineSnapshot` unchanged |
| `tests/baseline/cli.py` | New flags `--baseline-tag`, `--current-session`. Bootstrap SKIP with JSON. Remove `.current_baseline` logic |
| `.github/workflows/ci.yml` | New session ID format, remove `--hours`, add artifact upload |
| `tests/baseline/test_collector.py` | Tests for trace-level computation, None guards, pagination |
| `tests/baseline/test_cli.py` | Tests for bootstrap SKIP, new flags, structured JSON output |

**Unchanged:** `thresholds.yaml`, `BaselineSnapshot` dataclass, `BaselineManager.compare()`.

## Implementation Order (TDD)

1. **Tests first:** `test_collector.py` — mock `langfuse.api.trace.list()` and `langfuse.api.observations.list()`, test computation logic + None guards
2. **Tests first:** `test_cli.py` — test bootstrap SKIP, new CLI flags, structured JSON output
3. **Implement:** `collector.py` — new methods
4. **Implement:** `cli.py` — new flags, bootstrap, remove file-based state
5. **Implement:** `manager.py` — wire new collector
6. **Implement:** `ci.yml` — new session ID, artifact upload
7. **Cleanup:** Remove `.current_baseline` file, update `.gitignore`
