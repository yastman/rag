"""Human-in-the-Loop (HITL) support for CRM write tools (#443).

Uses LangGraph interrupt() to pause graph execution and surface a confirmation
payload to the Telegram bot. The bot sends an inline keyboard; when the user
clicks, the agent is resumed via Command(resume={"action": "approve"|"cancel"}).
"""

from __future__ import annotations

import threading
from collections import OrderedDict

from langgraph.types import interrupt


# ---------------------------------------------------------------------------
# Pending resume trace-id store (#2224)
# ---------------------------------------------------------------------------
# A HITL interrupt emits one Langfuse trace; the later ``Command(resume=...)``
# click emits a *separate* trace. To link them, the bot records the interrupt
# trace id here (keyed by the checkpointer ``thread_id``) at confirmation time,
# then reads it back when the resume trace starts and attaches it as
# ``resumes_trace_id`` metadata. This is best-effort, in-memory observability
# glue — a missing entry simply means no back-link is recorded — so the store
# is bounded to avoid unbounded growth and guarded by a lock for thread safety.

_PENDING_RESUME_TRACE_IDS: OrderedDict[str, str] = OrderedDict()
_PENDING_RESUME_LOCK = threading.Lock()
_PENDING_RESUME_MAX = 1024


def set_pending_resume_trace_id(thread_id: str, trace_id: str | None) -> None:
    """Remember the Langfuse trace id that emitted a HITL interrupt for *thread_id*.

    No-op when either argument is empty so callers can pass
    ``lf.get_current_trace_id()`` directly without guarding (#2224).
    """
    if not thread_id or not trace_id:
        return
    with _PENDING_RESUME_LOCK:
        _PENDING_RESUME_TRACE_IDS[thread_id] = trace_id
        _PENDING_RESUME_TRACE_IDS.move_to_end(thread_id)
        while len(_PENDING_RESUME_TRACE_IDS) > _PENDING_RESUME_MAX:
            _PENDING_RESUME_TRACE_IDS.popitem(last=False)


def pop_pending_resume_trace_id(thread_id: str) -> str | None:
    """Retrieve and clear the pending interrupt trace id for *thread_id* (#2224).

    Returns ``None`` when nothing was stored (e.g. tracing disabled at interrupt
    time or the entry was evicted).
    """
    if not thread_id:
        return None
    with _PENDING_RESUME_LOCK:
        return _PENDING_RESUME_TRACE_IDS.pop(thread_id, None)


def hitl_guard(
    tool_name: str,
    preview: str,
    args: dict,
) -> dict:
    """Pause graph execution for HITL confirmation.

    Calls interrupt() with a structured payload. LangGraph saves graph state
    via checkpointer; the caller receives result["__interrupt__"][0].value.

    Args:
        tool_name: Name of the tool requiring confirmation.
        preview: Human-readable description of the pending operation.
        args: Raw tool arguments (for audit / display).

    Returns:
        The resume value dict (with "action" key: "approve" or "cancel").
    """
    return interrupt(  # type: ignore[return-value, no-any-return]
        {
            "tool": tool_name,
            "preview": preview,
            "args": args,
        }
    )


_TOOL_LABELS: dict[str, str] = {
    "crm_create_lead": "Создать сделку",
    "crm_update_lead": "Обновить сделку",
    "crm_upsert_contact": "Создать/обновить контакт",
    "crm_update_contact": "Обновить контакт",
}


def format_hitl_preview(tool_name: str, args: dict) -> str:
    """Format a human-readable preview for HITL confirmation.

    Args:
        tool_name: Tool name (used to look up a Russian label).
        args: Tool arguments to display.

    Returns:
        Multiline string like "Создать сделку:\\n  name: Test\\n  budget: 50000"
    """
    label = _TOOL_LABELS.get(tool_name, tool_name)
    lines = [f"{label}:"]
    for k, v in args.items():
        if v is not None and k != "config":
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)
