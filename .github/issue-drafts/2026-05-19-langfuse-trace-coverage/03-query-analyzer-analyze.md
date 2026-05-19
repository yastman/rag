# observability: QueryAnalyzer.analyze produces orphan generations

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

`QueryAnalyzer` wraps an `instructor.from_openai(langfuse.openai.AsyncOpenAI)` client. The structured-output completion call **is** auto-traced as a generation, but the public `analyze()` method is **not** wrapped in `@observe`. When invoked from a code path without an active span (eval runner, batch script, test), the generation becomes orphan and loses the `session_id` / `user_id` / pipeline-step context.

This is a single-file fix, ~8 lines.

## Evidence

- `telegram_bot/services/query_analyzer.py:65` — `class QueryAnalyzer`.
- `telegram_bot/services/query_analyzer.py:86` — `async def analyze(self, query: str) -> dict[str, Any]`; no `@observe`.
- `telegram_bot/services/query_analyzer.py:97` — `await self._instructor_client.chat.completions.create(...)` — auto-traced generation.

## SDK Baseline

- Langfuse Python v3: `@observe(name="query-analyzer", capture_input=False, capture_output=False)` + `update_current_span(input={...}, output={...})` with curated payloads.
- Established pattern: `telegram_bot/services/apartment_filter_extractor.py:53` (`@observe(name="apartment-filter-parse", ...)`).

## Implementation Plan

1. Add `@observe(name="query-analyzer", capture_input=False, capture_output=False)` on `QueryAnalyzer.analyze`.
2. Before the LLM call: `get_client().update_current_span(input={"query_preview": query[:120], "model": self._model})`.
3. After parsing the structured output: `update_current_span(output={"intent": result.intent, "language": result.language, "confidence": result.confidence})` (use the actual fields from `QueryAnalysisResult`).
4. On exception: `update_current_span(level="ERROR", status_message=str(exc)[:200])`.

## Forbidden

- Do not log the full LLM response payload to span output.
- Do not introduce a new wrapper layer; keep `instructor` + `langfuse.openai` as is.
- No changes to `QueryAnalysisResult` schema in this PR.

## Verification

```bash
uv run pytest tests/unit/services/test_query_analyzer.py -q
```

## Related

- Sibling: HyDEGenerator instrumentation (draft 02).
- Sibling: `apartment_filter_extractor` already follows this pattern; reuse the shape.
