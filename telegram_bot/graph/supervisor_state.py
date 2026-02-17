"""Supervisor state schema for multi-agent architecture (#240).

Minimal state for LLM-based supervisor that routes to tools:
rag_search, history_search, direct_response.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class SupervisorState(TypedDict):
    """State for the supervisor graph.

    Fields:
        messages: Conversation messages (with add_messages reducer for tool calls).
        user_id: Telegram user ID.
        session_id: Session identifier for grouping interactions.
        agent_used: Which tool/agent was selected by the supervisor.
        latency_stages: Timing breakdown per stage.
    """

    messages: Annotated[list, add_messages]
    user_id: int
    session_id: str
    agent_used: str
    latency_stages: dict[str, float]


def make_supervisor_state(
    user_id: int,
    session_id: str,
    query: str,
) -> dict[str, Any]:
    """Create initial state for a supervisor graph invocation."""
    return {
        "messages": [{"role": "user", "content": query}],
        "user_id": user_id,
        "session_id": session_id,
        "agent_used": "",
        "latency_stages": {},
    }
