# observability: complete @observe coverage on CRM aiogram callback handlers

## Source

2026-05-19 Langfuse trace-coverage audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/`).

## Problem

`LangfuseContextMiddleware` creates a root span per Telegram callback, and the highest-traffic CRM callbacks (`on_task_complete`, `on_note_text_received`) have nested `@observe` decorators. But several **write-side** callback handlers run inside the root span as a flat collection of statements — calling Kommo, mutating FSM state, posting messages — with no nested span. As a result the trace timeline shows one span and a fan of un-named `kommo-*` children, making it hard to read flow at a glance.

This is the standard symptom of partial @observe rollout; this issue closes the gap on the remaining callbacks.

## Evidence

- `telegram_bot/handlers/crm_callbacks.py:37` — `async def on_lead_note(...)`; no `@observe`.
- `telegram_bot/handlers/crm_callbacks.py:57` — `async def on_lead_task(...)`; no `@observe`.
- `telegram_bot/handlers/crm_callbacks.py:100` — `async def on_task_postpone(...)`; no `@observe`.
- `telegram_bot/handlers/crm_callbacks.py:125` — `async def on_contact_note(...)`; no `@observe`.
- `telegram_bot/handlers/crm_callbacks.py:175` — `async def on_task_text_received(...)`; no `@observe`.
- `telegram_bot/handlers/crm_callbacks.py:212` — `async def on_task_edit(...)`; no `@observe`.
- `telegram_bot/handlers/crm_callbacks.py:230` — `async def on_edit_field_chosen(...)`; no `@observe`.
- `telegram_bot/handlers/crm_callbacks.py:247` — `async def on_edit_task_text_received(...)`; no `@observe`.
- `telegram_bot/handlers/crm_callbacks.py:275` — `async def on_edit_task_date_received(...)`; no `@observe`.
- Companions already done: `crm_callbacks.py:77` (`crm-quick-complete`), `crm_callbacks.py:145` (`crm-quick-note`).

## SDK Baseline

- Langfuse Python v3: `@observe(name="crm-<action>", capture_input=False, capture_output=False)` per write-handler.
- Curated `update_current_span(input={"deal_id": ..., "action": ...})`; **never** raw `callback.data` or full FSM state.
- Established pattern: `crm_callbacks.py:77` and `crm_callbacks.py:145`.

## Implementation Plan

For each handler listed under Evidence, apply:

1. Decorator: `@observe(name="crm-<short-action-name>", capture_input=False, capture_output=False)`. Suggested names:
   - `on_lead_note` → `crm-lead-note-prompt`
   - `on_lead_task` → `crm-lead-task-prompt`
   - `on_task_postpone` → `crm-task-postpone`
   - `on_contact_note` → `crm-contact-note-prompt`
   - `on_task_text_received` → `crm-task-create`
   - `on_task_edit` → `crm-task-edit-prompt`
   - `on_edit_field_chosen` → `crm-task-edit-field`
   - `on_edit_task_text_received` → `crm-task-edit-text`
   - `on_edit_task_date_received` → `crm-task-edit-date`
2. Curated `update_current_span(input={...})` with stable keys (e.g., `deal_id`, `task_id`, `field`, `action`).
3. On user-facing failure (Kommo error caught and shown to user): `update_current_span(level="ERROR", status_message=str(exc)[:200])`.
4. On no-op / cancelled paths: `update_current_span(output={"action": "cancelled"})` so the span carries the decision.

## Forbidden

- No raw `callback.data` or `state.get_data()` content in span input/output.
- No PII (phone/email/full name) in span fields.
- No changes to FSM state semantics.
- No move of these callbacks to a different module.

## Verification

```bash
uv run pytest tests/unit/handlers/test_crm_callbacks.py -q
```

## Related

- #1655 — Kommo Pydantic custom-field models (orthogonal).
- Sibling draft 09 — link Langfuse Prompts to generations (does not touch callbacks).
