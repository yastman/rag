# HITL CRM Flow

Human-in-the-loop (HITL) pattern for CRM operations requiring human approval.

## Architecture

```
User → Telegram Bot → LangGraph Agent
                         ↓
                   CRM Tool Call
                         ↓
                   interrupt() ← HITL trigger
                         ↓
                   Bot waits...
                         ↓
Human approves/rejects in Telegram
                         ↓
                  Command(resume=)
                         ↓
                  Graph resumes
```

## HITL Trigger Points

CRM tools that trigger HITL via `interrupt()`:

| Tool | Trigger Condition |
|------|-------------------|
| `create_lead` | All lead creation |
| `schedule_viewing` | All viewing scheduling |
| `transfer_lead` | Lead ownership transfer |
| `update_lead_status` | Status changes to qualified |

## Flow States

Defined in `telegram_bot/services/handoff_state.py`:

```python
class HandoffState(TypedDict):
    """HITL state persisted in Redis."""
    state: str                    # "waiting", "approved", "rejected"
    lead_id: int | None
    action: str                   # "create_lead", "schedule_viewing", etc.
    payload: dict                 # Action parameters
    supervisor_chat_id: int       # Where to send approval request
    created_at: float
    expires_at: float
```

## HandoffData Schema

```python
class HandoffData(TypedDict):
    """Passed through graph state for HITL decisions."""
    is_handoff: bool
    handoff_reason: str | None
    lead_id: int | None
    action: str | None
    qualification_score: float | None
```

## Supervisor Notification

When `interrupt()` fires:
1. Graph execution pauses
2. Supervisor thread receives notification with action details
3. Supervisor approves/rejects via inline keyboard
4. `Command(resume=...)` fires with decision

## Redis Keys

| Key Pattern | TTL | Content |
|-------------|-----|---------|
| `handoff:{thread_id}` | 300s | Serialized HandoffState |
| `kommo:oauth:tokens` | long-lived | OAuth tokens (shared) |

## Code Locations

| File | Purpose |
|------|---------|
| `telegram_bot/agents/hitl.py` | `interrupt()` wrapper and handlers |
| `telegram_bot/services/handoff_state.py` | State definitions |
| `telegram_bot/handlers/handoff.py` | Handoff FSM states and handlers |
| `telegram_bot/graph/nodes/` | Nodes that may trigger HITL |

## Error Handling

If supervisor times out (300s TTL):
- Action is automatically rejected
- User receives timeout message
- Graph resumes with `rejected` state

## Testing

```bash
# Test HITL flow
uv run pytest tests/unit/telegram_bot/test_handoff.py -v
```
