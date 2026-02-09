"""In-memory checkpointer for LangGraph conversation persistence.

Uses MemorySaver for development/single-process deployments.
For multi-process production, switch to PostgresSaver.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver


# Singleton checkpointer — shared across graph invocations
checkpointer = MemorySaver()
