# observability: link Langfuse Prompts to generations via update_current_generation(prompt=...)

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

`telegram_bot/services/prompt_manager.get_prompt(name=, fallback=)` is used across nodes and services to fetch managed prompts from Langfuse. However, the fetched `Prompt` object is **never** passed into `update_current_generation(prompt=...)`. As a result:

- Langfuse UI shows generations without a "Prompt" link, breaking the **Prompt → Traces** drill-down used to evaluate prompt versions.
- A/B-experimentation and prompt rollback workflows lose their telemetry hook.
- Cost/latency comparison "by prompt version" is impossible.

## Evidence

- `grep -rn "update_current_generation(prompt=" telegram_bot/ src/` returns **zero matches**.
- All call sites currently look like: `prompt = get_prompt("...")`, build messages, call LLM — but the `prompt` object is discarded after `compile()` / `messages` extraction.
- Hot call sites that should link prompts:
  - `telegram_bot/services/generate_response.py` (`get_prompt("response_generation", ...)`)
  - `telegram_bot/services/query_preprocessor.py` (`get_prompt("hyde", ...)`)
  - `telegram_bot/services/query_analyzer.py` (`get_prompt("query_analysis", ...)`)
  - `telegram_bot/services/nurturing_service.py` (`get_prompt("nurturing", ...)`)
  - `telegram_bot/services/session_summary.py` (`get_prompt("session_summary", ...)`)
  - `telegram_bot/services/ai_advisor_service.py` (`get_prompt("advisor", ...)`)
  - `telegram_bot/services/handoff_summary.py` (`get_prompt("handoff_summary", ...)`)
  - `src/contextualization/{claude,groq,openai}.py` (`get_prompt("contextualize", ...)`)

## SDK Baseline

- Langfuse Python v3 docs: `update_current_generation(prompt=prompt_obj)` accepts the `Prompt` object returned by `langfuse.get_prompt(...)`. This binds the generation observation to a versioned prompt in Langfuse Prompt Management.
- Pattern (from Langfuse cookbook): inside an `@observe`-decorated function, after fetching the prompt and before/after the LLM call, call `get_client().update_current_generation(prompt=prompt_obj)`.

## Implementation Plan

1. Audit `prompt_manager.get_prompt(...)` callers. Where the function does not already return the raw `Prompt` object, **expose it** alongside the compiled messages without changing existing call sites' message-list contract.
2. At each call site listed under Evidence, after the LLM call (inside the same `@observe` span), call:
   ```python
   from telegram_bot.observability import get_client
   if prompt_obj is not None:
       get_client().update_current_generation(prompt=prompt_obj)
   ```
3. For services where multiple prompts may be used in one trace (e.g., `query_analyzer` + `generate_response` chained), each call site links its own prompt — Langfuse handles the per-generation binding.
4. For fallback paths where `prompt_obj` is `None` (Langfuse unavailable, fallback string used), skip the link silently — no errors.
5. Add a unit test that mocks the Langfuse client and asserts `update_current_generation` was called with `prompt=<Prompt>` at least once per LLM-call wrapper.

## Forbidden

- Do not change the public signature of `get_prompt` in a breaking way; expand its return shape only if it stays backwards-compatible (e.g., add an optional `return_prompt_obj=False` flag, or return a tuple in a new `get_prompt_with_obj` function).
- Do not link a fallback string as if it were a managed prompt — only link real `Prompt` objects from Langfuse.
- No prompt-store migration in this PR.
- No changes to prompt template content or variables.

## Verification

```bash
uv run pytest tests/unit/services/test_prompt_manager.py -q
uv run pytest tests/unit/services -k "generate_response or query_preprocessor or query_analyzer or nurturing or session_summary or advisor or handoff" -q
uv run pytest tests/unit/contextualization -q
```

Manual: in Langfuse UI, open any production trace; the generation observation should show a "Prompt" link to a versioned prompt in Prompt Management.

## Related

- This issue depends on draft 02 (HyDE @observe), 03 (QueryAnalyzer @observe), 04 (LLMService @observe), 05 (SessionSummaryWorker @observe), and 08 (actual model name) — all of those should land first so that there is an active span/generation to update.
