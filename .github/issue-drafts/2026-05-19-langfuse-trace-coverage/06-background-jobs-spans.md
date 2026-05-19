# observability: lead-scoring / hot-lead / nurturing-scheduler background jobs missing @observe

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

Several periodic / on-demand background jobs run with **no Langfuse span**, so a hung or failing job is visible only via logs. Without a span, you cannot:

- aggregate per-job latency in Langfuse Sessions UI;
- attach a `tags=["job", "<name>"]` filter for ops dashboards;
- record `level=ERROR` with a structured `status_message` for failure attribution.

`NurturingScheduler.run_nurturing_batch` already has `@observe(name="nurturing-scheduler-tick")`, so the pattern is established and accepted. This issue extends the same pattern to the remaining jobs.

## Evidence

- `telegram_bot/services/lead_score_sync.py:14` — `async def sync_pending_lead_scores(...)`; no `@observe`.
- `telegram_bot/services/hot_lead_notifier.py:27` — `async def notify_if_hot(self, payload)`; no `@observe`.
- `telegram_bot/services/nurturing_scheduler.py:99` — `async def run_nurturing_dispatch(self)`; no `@observe`.
- `telegram_bot/services/nurturing_scheduler.py:108` — `async def run_funnel_rollup(self)`; no `@observe`.
- Companion (already done): `telegram_bot/services/nurturing_scheduler.py:90` — `@observe(name="nurturing-scheduler-tick")` on `run_nurturing_batch`.

## SDK Baseline

- Langfuse Python v3: `@observe(name="job-<name>", capture_input=False, capture_output=False)` paired with `propagate_attributes(tags=["job", "<area>"])` inside the body so every nested generation gets the job tag.
- Established pattern: `telegram_bot/services/nurturing_scheduler.py:90`.

## Implementation Plan

1. Add `@observe(name="job-lead-score-sync", capture_input=False, capture_output=False)` on `sync_pending_lead_scores`. Inside, `propagate_attributes(tags=["job", "lead-scoring"])`. Set `update_current_span(output={"processed": n, "failed": k, "skipped": s})` after the batch.
2. Add `@observe(name="job-hot-lead-notify", capture_input=False, capture_output=False)` on `HotLeadNotifier.notify_if_hot`. Set `update_current_span(input={"lead_id": lead_id, "score": score, "threshold": threshold})` and `output={"notified": bool_value}`.
3. Add `@observe(name="job-nurturing-dispatch", capture_input=False, capture_output=False)` on `run_nurturing_dispatch` with `propagate_attributes(tags=["job", "nurturing"])`.
4. Add `@observe(name="job-funnel-rollup", capture_input=False, capture_output=False)` on `run_funnel_rollup` with `propagate_attributes(tags=["job", "analytics"])`.
5. On exception in any: `update_current_span(level="ERROR", status_message=str(exc)[:200])` then re-raise so APScheduler can record the failure.

## Forbidden

- No new metrics or alerting in this PR; just spans (alerts are tracked in #1416).
- No coalesce/concurrency changes; only instrumentation.
- Do not capture full `payload` dicts in `update_current_span(input=...)` — keep curated keys only (lead_id, score, threshold). PII (phone/email) must not appear in span input.

## Verification

```bash
uv run pytest tests/unit/services/test_lead_score_sync.py tests/unit/services/test_hot_lead_notifier.py tests/unit/services/test_nurturing_scheduler.py -q
```

## Related

- #1654 — APScheduler migration (orthogonal). This PR can land before or after #1654; the `@observe` decorators work the same with both task-based and scheduler-based execution.
