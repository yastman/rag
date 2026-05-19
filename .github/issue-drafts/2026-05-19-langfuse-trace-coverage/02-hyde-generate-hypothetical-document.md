# observability: HyDEGenerator.generate_hypothetical_document produces orphan generations

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

`HyDEGenerator` uses `langfuse.openai.AsyncOpenAI`, so each completion call **is** auto-traced as a generation. But the public method `generate_hypothetical_document` is **not** wrapped in `@observe`. When this is invoked outside an active span (e.g., from a code path that has not yet entered the Telegram middleware root span — direct evaluation runners, tests, future API surfaces), the generation becomes an orphan trace with no parent and no `session_id`/`user_id`.

The Langfuse v3 docs explicitly recommend grouping related generations under an `@observe`-decorated parent (see *Group Multiple OpenAI Calls into a Single Trace*). This is a single-file fix, ~5 lines.

## Evidence

- `telegram_bot/services/query_preprocessor.py:37-119` — `class HyDEGenerator` and `async def generate_hypothetical_document(self, query: str) -> str` at line 80; no `@observe`.
- The class is constructed via `langfuse.openai.AsyncOpenAI` (auto-trace ON), so `chat.completions.create` becomes `litellm-acompletion` generation — orphan when no parent.

## SDK Baseline

- Langfuse Python v3: `@observe(name="hyde-generate-document", capture_input=False, capture_output=False)` + curated `update_current_span(input={"query_preview": query[:120]})`.
- Established pattern: `telegram_bot/services/query_analyzer.py` — same shape (instructor over Langfuse-wrapped client). See companion issue 03 for parallel fix there.

## Implementation Plan

1. Add `@observe(name="hyde-generate-document", capture_input=False, capture_output=False)` on `HyDEGenerator.generate_hypothetical_document`.
2. Inside the method, before the LLM call, set curated input via `get_client().update_current_span(input={"query_preview": query[:120], "model": self._model})`.
3. After the call, set curated output: `update_current_span(output={"document_preview": doc[:200], "tokens_estimated": len(doc.split())})`.
4. On exception path, set `level="ERROR"`, `status_message=str(exc)[:200]`.

## Forbidden

- Do not strip the `langfuse.openai` wrapping; keep auto-trace on.
- Do not log full generated document to span output (truncated only).
- Do not change the prompt-fetching path (`get_prompt("hyde", ...)`); this issue is purely instrumentation.
- No prompt-to-generation linking in this PR (separate issue, see draft 09).

## Verification

```bash
uv run pytest tests/unit/services/test_query_preprocessor.py -q
uv run pytest tests/unit -k "hyde" -q
```

## Related

- #1652 — research issue on whether HyDE should be replaced with a LangChain-native primitive (orthogonal; this issue improves observability without touching the implementation).
