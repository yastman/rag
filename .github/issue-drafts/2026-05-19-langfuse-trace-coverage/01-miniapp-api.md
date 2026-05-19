# observability: Mini App FastAPI has zero Langfuse trace coverage

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

`mini_app/` is a **separate FastAPI service** that handles conversion-funnel traffic from Telegram Mini App: `/api/start-expert`, `/api/phone`, `/api/log`, `/api/config`. It has **no** `@observe`, no `propagate_attributes`, no `get_client()` calls. Leads created via Mini App and the Kommo write inside `submit_phone()` are **invisible in Langfuse**, and there is no `session_id` linking the Mini App entry to the subsequent `/start q_<expert>` Telegram dialog.

This breaks two things:

1. The full funnel `Mini App → /start q_… → Telegram dialog → CRM` cannot be reconstructed in Langfuse Sessions UI.
2. Failures of the Kommo upsert+create-lead pair inside `mini_app/phone.py:submit_phone` are visible only as logs, not as a span with `level=ERROR`.

## Evidence

- `mini_app/api.py:43-110` — endpoints `get_config`, `start_expert`, `remote_log`, `phone` — no Langfuse instrumentation.
- `mini_app/phone.py:39` — `async def submit_phone(...)` performs Kommo `upsert_contact` + `create_lead` with no parent span.
- `mini_app/expert_start.py` — payload assembly for deeplink, no `propagate_attributes(session_id=..., user_id=...)`.
- `telegram_bot/observability.py` already exports `observe`, `get_client`, `propagate_attributes` for reuse.

## SDK Baseline

- Langfuse Python v3: `@observe(name=..., capture_input=False, capture_output=False)` for endpoints + `update_current_span(input={...})` for curated payloads (avoid leaking phone numbers / payloads).
- `propagate_attributes(session_id=f"miniapp-{user_id}", user_id=str(user_id), tags=["miniapp", ...])` to attach session/user context.
- Established pattern in repo: `src/api/main.py:156` (`@observe(name="rag-api-query", capture_input=False, capture_output=False)`).

## Implementation Plan

1. Add `@observe(name="miniapp-start-expert", capture_input=False, capture_output=False)` on `mini_app/api.py:start_expert` with `propagate_attributes(session_id=f"miniapp-{user_id}", user_id=str(user_id), tags=["miniapp", "start-expert", expert_id])`.
2. Add `@observe(name="miniapp-submit-phone", capture_input=False, capture_output=False)` on `mini_app/api.py:phone` with the same propagate scope.
3. Add `@observe(name="miniapp-kommo-create-lead", capture_input=False, capture_output=False)` on `mini_app/phone.py:submit_phone`; on Kommo failure call `get_client().update_current_span(level="ERROR", status_message=...)`.
4. Use the same `session_id` format (`miniapp-{tg_user_id}`) when the Telegram bot subsequently handles `/start q_<expert>` so the funnel groups in Langfuse Sessions UI.
5. Ensure PII (`phone`, `name`) is excluded from span input/output via curated dicts; rely on the SDK-level `mask` from `telegram_bot/observability.py`.

## Forbidden

- No raw `request` payloads in span input/output.
- No `langfuse_trace_id` plumbing on the Mini App API surface yet (separate concern; see #1253).
- No new prometheus metrics in this PR.
- No changes to the Mini App frontend SDK.

## Verification

```bash
uv run pytest tests/unit/mini_app -q
uv run pytest tests/unit/test_langfuse_context_middleware.py -q
```

Manual: run `make local-up`, hit `/api/start-expert` and `/api/phone` from the dev Mini App, confirm a single Langfuse session contains both endpoints + the subsequent Telegram `/start q_…` trace.

## Related

- #1253 — trace context propagation between graphs (broader, separate).
- #1543 — contextualize batch + ColBERT span gaps (orthogonal).
