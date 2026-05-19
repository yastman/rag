# observability: LLMService public methods produce orphan generations

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

`telegram_bot/services/llm.py:LLMService` uses `langfuse.openai.AsyncOpenAI` as its underlying client. Each `chat.completions.create` call is auto-traced as a generation. But all three public async methods — `generate_answer`, `stream_answer`, `generate` — are **not** wrapped in `@observe`. When `LLMService` is used outside a request-scoped trace (background tasks, fallback paths, scripts), generations show up as top-level orphans without `session_id`/`user_id`/pipeline-step grouping.

This is a single-file fix; three method-level decorators.

## Evidence

- `telegram_bot/services/llm.py:61` — `class LLMService`.
- `telegram_bot/services/llm.py:97` — `async def generate_answer(...)`; no `@observe`.
- `telegram_bot/services/llm.py:213` — `async def stream_answer(...)`; no `@observe`.
- `telegram_bot/services/llm.py:366` — `async def generate(...)`; no `@observe`.
- `telegram_bot/services/llm.py:14` — `from langfuse.openai import AsyncOpenAI` (auto-trace path is correct, just not parented).

## SDK Baseline

- Langfuse Python v3: per-method `@observe(name="llm-service-<method>", capture_input=False, capture_output=False)`.
- For `stream_answer`, mark as a coroutine that yields chunks; capture only summary metadata in `update_current_span(output=...)` after the stream is fully drained, not chunk-by-chunk.
- Established pattern: `telegram_bot/services/ai_advisor_service.py:264` (`@observe(name="advisor-llm-call", capture_input=False, capture_output=False)`).

## Implementation Plan

1. Decorate `generate_answer` with `@observe(name="llm-service-generate-answer", capture_input=False, capture_output=False)`. Inside, set `update_current_span(input={"prompt_preview": prompt[:120], "model": self.model, "with_confidence": with_confidence})` and `update_current_span(output={"response_len": len(response_text)})` after the call.
2. Decorate `stream_answer` with `@observe(name="llm-service-stream-answer", capture_input=False, capture_output=False)`. Track chunks count and final length in a local accumulator, then `update_current_span(output={"chunks": n, "total_len": len(full)})` after the generator finishes.
3. Decorate `generate` with `@observe(name="llm-service-generate", capture_input=False, capture_output=False)`. Same shape as `generate_answer` but simpler: prompt preview in, response length out.
4. On exception in any of the three: `update_current_span(level="ERROR", status_message=str(exc)[:200])` then re-raise.

## Forbidden

- Do not capture full prompt or full response in span input/output (truncated previews only).
- Do not switch off `langfuse.openai` auto-trace; nested generation under our @observe span is the intended structure.
- Do not change `ConfidenceResponse` schema or `instructor` integration.
- Do not introduce a new metrics path; this PR is observability-only.

## Verification

```bash
uv run pytest tests/unit/services/test_llm.py tests/unit/test_llm_service.py -q
```

## Related

- Sibling drafts: 02 (HyDE), 03 (QueryAnalyzer), 05 (SessionSummaryWorker._generate_summary) — same orphan-generation pattern.
