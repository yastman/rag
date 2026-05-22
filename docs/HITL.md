# Human-in-the-Loop (HITL) for CRM Operations

The bot uses LangGraph's `interrupt()` mechanism to pause execution and request user confirmation before executing CRM write operations.

## Overview

HITL enables the bot to:
- Pause before destructive or important CRM operations
- Show users a preview of what will happen
- Let users approve or cancel the operation
- Resume or cancel the graph based on user decision

## How HITL Works

```
User Request --> Agent decides to call CRM tool
                        |
              hitl_guard() called with tool preview
                        |
              interrupt() pauses graph
                        |
              Bot sends confirmation keyboard to user
                        |
         User clicks "Approve" or "Cancel"
                        |
              Command(resume={"action": "approve"|"cancel"})
                        |
              Graph resumes, tool executes or is skipped
```

## CRM Operations Covered by HITL

| Tool | Operation | Preview |
|------|-----------|---------|
| `crm_create_lead` | Create new deal | Deal name, budget |
| `crm_update_lead` | Update existing deal | Deal ID, new values |
| `crm_upsert_contact` | Create/update contact | Contact name, phone |
| `crm_update_contact` | Update contact | Contact ID, new values |

## User Experience

When HITL triggers, the user sees:

1. **Inline keyboard** with two buttons:
   - ✅ "Подтвердить" (Approve)
   - ❌ "Отмена" (Cancel)

2. **Preview text** showing what will happen:
   ```
   Создать сделку:           # "Create deal:"
     name: Test Deal
     budget: 50000
   ```

## Implementation Details

### hitl_guard Function

Located in `telegram_bot/agents/hitl.py`:

```python
def hitl_guard(tool_name: str, preview: str, args: dict) -> dict:
    """Pause graph for HITL confirmation.

    Returns resume value with 'action' key: 'approve' or 'cancel'.
    """
    return interrupt({
        "tool": tool_name,
        "preview": preview,
        "args": args,
    })
```

### HITL Flow in CRM Tools

```python
# In crm_create_lead tool
preview = format_hitl_preview("crm_create_lead", args)
result = hitl_guard("crm_create_lead", preview, args)

if result["action"] == "cancel":
    return "Операция отменена"  # "Operation cancelled"

# Proceed with CRM call
...
```

### Bot Resume Handling

In `telegram_bot/bot.py`:

```python
# When user clicks inline keyboard:
if callback_data == "hitl_approve":
    agent_command = Command(resume={"action": "approve"})
elif callback_data == "hitl_cancel":
    agent_command = Command(resume={"action": "cancel"})

# Resume graph with command
await graph.ainvoke(None, config={"command": agent_command})
```

## Handoff State Management

The handoff state is managed by `telegram_bot/services/handoff_state.py` using a Pydantic model backed by Redis:

```python
class HandoffData(BaseModel):
    """State for an active handoff session."""
    client_id: int
    topic_id: int
    mode: str = "human_waiting"  # bot | human_waiting | human
    lead_id: int | None = None
    created_at: float
    manager_joined_at: float | None = None
    qualification: dict[str, str]
```

### Redis Keys

| Key Pattern | TTL | Content |
|-------------|-----|---------|
| `handoff:{client_id}` | session-scoped | Serialized HandoffData |
| `topic_map:{topic_id}` | session-scoped | Reverse lookup to client_id |

## Code Locations

| File | Purpose |
|------|---------|
| `telegram_bot/agents/hitl.py` | `interrupt()` wrapper and `format_hitl_preview` |
| `telegram_bot/services/handoff_state.py` | Handoff state (Pydantic model + Redis) |
| `telegram_bot/handlers/handoff.py` | Handoff FSM states and callback helpers |
| `telegram_bot/dialogs/handoff.py` | Qualification dialog (aiogram-dialog) |
| `telegram_bot/graph/nodes/` | Graph nodes that may trigger HITL |

## Troubleshooting

### Interrupt State Lost (Bot Restart)

If the bot restarts while awaiting HITL confirmation:
1. The interrupt state is stored in the LangGraph checkpointer
2. On restart, the state is reloaded from the checkpointer store (Redis)
3. The user will see the confirmation message again
4. If the state is truly lost, the user should start a new query

### Recovery Steps

If a user is stuck waiting for confirmation:

1. **For the user:** Start a new query -- the previous operation will be abandoned
2. **For operators:** Check Redis for interrupt state keys:
   ```bash
   redis-cli -p 6379 KEYS "*interrupt*"
   ```

### Debugging HITL

To trace HITL flow in Langfuse:

1. Look for spans named `hitl_guard`
2. Check input fields: `tool`, `preview`, `args`
3. Check for `__interrupt__` in state

## Testing

```bash
# Unit tests for handoff flow
uv run pytest tests/unit/telegram_bot/test_handoff.py -v
```

## Configuration

HITL is enabled by default for all CRM write tools. No configuration required.

## Related Documentation

- [LangGraph Interrupt](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/#interrupt)
- [ADR-0009: LangGraph Send Fan-Out](adr/0009-langgraph-send-fanout-scoping.md) (related LangGraph patterns)
- Bot source: `telegram_bot/agents/hitl.py`
