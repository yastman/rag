# HITL CRM Flow

Human-in-the-loop (HITL) confirmation for CRM **write** operations. Every CRM
write tool pauses the agent and asks the user to confirm before the write hits
Kommo.

> Scope: this document describes the **CRM write-confirmation** flow only. The
> separate *manager handoff* mechanism (`telegram_bot/services/handoff_state.py`
> `HandoffData` / `handoff:{client_id}` Redis hash, `telegram_bot/handlers/handoff.py`)
> is a different feature and is **not** part of this flow.

## Architecture

The flow is SDK-native: LangGraph `interrupt()` pauses the graph, the bot
surfaces an inline keyboard, and `Command(resume=...)` continues the same
checkpointed run.

```
User → Telegram → _handle_query_supervisor → agent.ainvoke(...)
                                                   │
                              CRM write tool (crm_create_lead, ...)
                                                   │
                              hitl_guard(tool, preview, args)
                                                   │
                                   interrupt({tool, preview, args})   ← graph pauses
                                                   │
        result["__interrupt__"] detected → _send_hitl_confirmation(...)
                                                   │
                      inline keyboard: ✅ hitl:approve  /  ❌ hitl:cancel
                                                   │
        handle_hitl_callback → agent.ainvoke(Command(resume={"action": ...}))
                                                   │
                 hitl_guard returns {"action": ...} → tool proceeds or aborts
```

## HITL trigger points

The CRM write tools in `telegram_bot/agents/crm_tools.py` each call
`hitl_guard(...)` before performing the write:

| Tool | hitl_guard label | Effect on approve |
|------|------------------|-------------------|
| `crm_create_lead` | `crm_create_lead` | `kommo.create_lead(...)` |
| `crm_update_lead` | `crm_update_lead` | `kommo.update_lead(...)` |
| `crm_upsert_contact` | `crm_upsert_contact` | `kommo.upsert_contact(...)` |
| `crm_update_contact` | `crm_update_contact` | `kommo.update_contact(...)` |

Read-only CRM tools (`crm_get_deal`, `crm_search_leads`, `crm_get_my_tasks`,
notes/tasks creation, etc.) do **not** trigger HITL.

On `{"action": "cancel"}` (or anything other than `approve`) the tool returns
`"Операция отменена пользователем."` and never calls Kommo.

## How the pause/resume works

1. `hitl_guard(tool_name, preview, args)` (`telegram_bot/agents/hitl.py`) calls
   LangGraph `interrupt({"tool": ..., "preview": ..., "args": ...})`. LangGraph
   persists the graph state via the checkpointer and unwinds with that payload.
2. The supervisor invoke returns a result whose `result["__interrupt__"][0].value`
   carries that payload. `PropertyBot._send_hitl_confirmation` posts an inline
   keyboard with `hitl:approve` / `hitl:cancel` buttons.
3. `PropertyBot.handle_hitl_callback` rebuilds the agent with the **same
   checkpointer** and resumes with `agent.ainvoke(Command(resume={"action":
   "approve"|"cancel"}), config={"configurable": {"thread_id": ...}})`.
4. Inside the resumed run, `interrupt()` returns the resume value, so
   `hitl_guard` returns `{"action": ...}` and the tool continues.

The resume value is the user's decision; there is no custom Redis state for this
flow — pause/resume rides entirely on the LangGraph checkpointer keyed by
`thread_id` (`_supervisor_thread_id(chat_id, forum_thread_id)`).

## State persistence

| Concern | Mechanism |
|---------|-----------|
| Paused graph state | LangGraph checkpointer (`AsyncRedisSaver` in prod, `MemorySaver` in dev), keyed by `thread_id` |
| Interrupt payload | `{"tool", "preview", "args"}` returned in `result["__interrupt__"][0].value` |
| Resume decision | `Command(resume={"action": "approve"|"cancel"})` |

## Tracing

A HITL turn produces a **linear** trace. `telegram-rag-supervisor` stays a
generic parent span because it also covers pre-agent guard, semantic-cache, and
client-direct paths that can return before any SDK agent invocation. The actual
agent execution is typed separately as `as_type="agent"`:
`telegram-rag-agent-stream` for the streaming supervisor path and
`telegram-rag-agent-invoke` for the non-streaming/menu invoke path. The CRM tool
span (e.g. `crm-create-lead`, `as_type="tool"`) is nested under the agent run;
the confirmation keyboard is sent and the run pauses. The resume click is a
**separate** trace (`telegram-hitl-callback`, `as_type="agent"`) that scores
`hitl_action`.

The two traces are linked: at interrupt time the bot stores the parent trace id
and the resume trace records it as `resumes_trace_id` metadata. See
[`docs/BOT_INTERNAL_STRUCTURE.md`](BOT_INTERNAL_STRUCTURE.md) ("Interrupted/resumed
(HITL) trace linkage") and issue #2224.

## Code locations

| File | Purpose |
|------|---------|
| `telegram_bot/agents/hitl.py` | `hitl_guard()` (`interrupt()` wrapper), `format_hitl_preview()`, pending-resume trace store |
| `telegram_bot/agents/crm_tools.py` | CRM write tools that call `hitl_guard()` |
| `telegram_bot/bot.py` | `_send_hitl_confirmation()` (keyboard) and `handle_hitl_callback()` (`Command(resume=...)`) |

## Testing

```bash
# HITL guard, preview formatting, approve/cancel tool behavior, resume-trace store
uv run pytest tests/unit/agents/test_hitl.py -v

# thread_id <-> session_id co-location and interrupt/resume trace linkage
uv run pytest tests/contract/test_thread_session_link_contract.py -v
```
