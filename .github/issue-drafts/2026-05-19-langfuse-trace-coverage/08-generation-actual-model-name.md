# observability: generation observations record requested model, not LiteLLM-routed actual model

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

Several LLM-call wrappers correctly mark the span and pass `name=` to `chat.completions.create`, but they do not call `update_current_generation(model=response.model)` after the call. When LiteLLM routes the request to a different backend than what was requested (e.g., requested `gpt-oss-120b`, actually served by `cerebras/gpt-oss-120b`), the generation observation in Langfuse keeps the requested name. This:

- breaks per-provider cost attribution in Langfuse Usage UI;
- hides router fallback events from latency/cost dashboards;
- makes A/B comparison between providers invisible.

`telegram_bot/graph/nodes/rewrite.py` already does this correctly (`update_current_generation(model=rewrite_actual_model)` after the call). This issue propagates the same pattern to other LLM-call wrappers.

## Evidence

- ✅ Already correct: `telegram_bot/graph/nodes/rewrite.py` reads `response.model` and writes it to the generation.
- ❌ Missing: `telegram_bot/services/ai_advisor_service.py:264` (`@observe(name="advisor-llm-call")`) — does not call `update_current_generation(model=...)`.
- ❌ Missing: `telegram_bot/services/handoff_summary.py` — `generate_handoff_summary` LLM call.
- ❌ Missing: `telegram_bot/services/nurturing_service.py:174` (`@observe(name="nurturing-llm-generate")`) — message-generation LLM call.
- ❌ Missing: `telegram_bot/services/session_summary.py` — `generate_summary` LLM call.
- ❌ Missing: `telegram_bot/services/query_analyzer.py:97` — instructor call (after fix in companion draft 03).

## SDK Baseline

- Langfuse Python v3: after the LLM call returns, call `get_client().update_current_generation(model=response.model, usage_details={"input": ..., "output": ...})` to attach the actual served model and usage breakdown.
- Established pattern: `telegram_bot/graph/nodes/rewrite.py` (rewrite node).

## Implementation Plan

1. In each wrapper listed under Evidence, capture `response = await client.chat.completions.create(...)` (do not discard) and immediately call:
   ```python
   from telegram_bot.observability import get_client
   actual_model = getattr(response, "model", None)
   if actual_model:
       get_client().update_current_generation(model=actual_model)
   ```
2. Where `response.usage` is available (non-streaming), also pass `usage_details={"input": response.usage.prompt_tokens, "output": response.usage.completion_tokens, "total": response.usage.total_tokens}` so Usage UI is correct.
3. For streaming paths (`LLMService.stream_answer`), capture `chunk.model` from the first chunk that exposes it (varies by provider) and call `update_current_generation` once. Do not call it per chunk.
4. Keep this fix scoped to instrumentation; no changes to retry, fallback, or routing logic.

## Forbidden

- No new dependency on LiteLLM internals; rely on standard OpenAI response shape (`response.model`, `response.usage.*`).
- No mutation of caller-visible response object.
- No log spam — write `update_current_generation` once per call site.

## Verification

```bash
uv run pytest tests/unit/services -k "advisor or handoff_summary or nurturing or session_summary or query_analyzer" -q
```

Manual: send a Telegram query that hits each path; confirm in Langfuse UI that the generation `model` field equals what LiteLLM actually served (visible in LiteLLM logs as `successful_call_model_name`).

## Related

- #1648 — observability stack consolidation (orthogonal).
- Sibling drafts 02-05 — orphan-generation @observe wrappers; this issue should land **after** those, since it modifies the same call sites.
