"""Human-in-the-Loop (HITL) support for CRM write tools (#443).

Uses LangGraph interrupt() to pause graph execution and surface a confirmation
payload to the Telegram bot. The bot sends an inline keyboard; when the user
clicks, the agent is resumed via Command(resume={"action": "approve"|"cancel"}).
"""

from __future__ import annotations

from langgraph.types import interrupt


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
    return interrupt(  # type: ignore[return-value]
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
