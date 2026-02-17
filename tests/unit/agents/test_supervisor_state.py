"""Tests for SupervisorState contract (#240)."""

from __future__ import annotations

from typing import get_type_hints


def test_supervisor_state_has_required_fields():
    """SupervisorState must have all required fields."""
    from telegram_bot.graph.supervisor_state import SupervisorState

    hints = get_type_hints(SupervisorState, include_extras=True)
    required = {"messages", "user_id", "session_id", "agent_used", "latency_stages"}
    assert required.issubset(hints.keys()), f"Missing fields: {required - hints.keys()}"


def test_supervisor_state_messages_uses_add_messages_reducer():
    """messages field must use add_messages Annotated reducer."""
    from telegram_bot.graph.supervisor_state import SupervisorState

    hints = get_type_hints(SupervisorState, include_extras=True)
    messages_hint = hints["messages"]
    # Annotated types have __metadata__
    assert hasattr(messages_hint, "__metadata__"), "messages must be Annotated with reducer"


def test_make_supervisor_state_factory():
    """make_supervisor_state creates valid initial state."""
    from telegram_bot.graph.supervisor_state import make_supervisor_state

    state = make_supervisor_state(user_id=123, session_id="s-1", query="тест")
    assert state["user_id"] == 123
    assert state["session_id"] == "s-1"
    assert state["agent_used"] == ""
    assert state["latency_stages"] == {}
    assert len(state["messages"]) == 1
    assert state["messages"][0]["content"] == "тест"
