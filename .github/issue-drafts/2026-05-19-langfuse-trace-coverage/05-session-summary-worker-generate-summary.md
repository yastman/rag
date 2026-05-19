# observability: SessionSummaryWorker._generate_summary not wrapped in @observe

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

`SessionSummaryWorker._check_idle_sessions` is decorated with `@observe(name="session-summary-check")`, but the LLM call site `_generate_summary` is **not** wrapped. The actual completion call at line 156 is auto-traced via `langfuse.openai`, but it sits as a flat child of `session-summary-check` without:

- a dedicated span name to filter/aggregate on;
- per-summary input/output metadata (history length, summary length, model);
- an explicit `level=ERROR` path on LLM failure.

Today an LLM failure during summary generation appears as a generic `litellm-acompletion` error; you cannot distinguish it from a generation failure in the request-scoped path.

## Evidence

- `telegram_bot/services/session_summary_worker.py:90` — `@observe(name="session-summary-check")` on `_check_idle_sessions`.
- `telegram_bot/services/session_summary_worker.py:152` — `async def _generate_summary(self, history: list[dict[str, str]]) -> str`; no `@observe`.
- `telegram_bot/services/session_summary_worker.py:156` — `await self._llm.chat.completions.create(...)`.

## SDK Baseline

- Langfuse Python v3: `@observe(name="session-summary-llm", capture_input=False, capture_output=False)` for the LLM-call wrapper.
- Established pattern: `telegram_bot/services/nurturing_service.py:174` — `@observe(name="nurturing-llm-generate", capture_input=False, capture_output=False)` on the LLM-call wrapper inside an outer scheduler span.

## Implementation Plan

1. Decorate `_generate_summary` with `@observe(name="session-summary-llm", capture_input=False, capture_output=False)`.
2. Set `update_current_span(input={"history_turns": len(history), "model": self._model})` before the call.
3. Set `update_current_span(output={"summary_len": len(summary), "summary_preview": summary[:120]})` after the call.
4. On LLM failure: `update_current_span(level="ERROR", status_message=str(exc)[:200])`, then re-raise.

## Forbidden

- Do not capture full conversation history in span input.
- Do not capture full summary text in span output.
- Do not change the placeholder fallback behavior tracked separately in #1599 / #1608.
- No retry or job-scheduling changes in this PR.

## Verification

```bash
uv run pytest tests/unit/services/test_session_summary_worker.py -q
```

## Related

- #1599, #1608 — placeholder source / cap/perf for session summary worker (orthogonal, do not change in this PR).
- #1654 — APScheduler migration for periodic loops (orthogonal, separate PR).
