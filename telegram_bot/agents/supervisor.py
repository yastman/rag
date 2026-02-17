"""Supervisor graph — routes queries to tools (#240 Task 5).

LangGraph StateGraph with a supervisor LLM that selects the right tool
(rag_search, history_search, direct_response) based on user intent.

The supervisor loop:
1. Supervisor LLM decides which tool to call (via bind_tools)
2. ToolNode executes the selected tool
3. If the LLM returns a final message (no tool call), the loop ends
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from telegram_bot.graph.supervisor_state import SupervisorState


logger = logging.getLogger(__name__)


def build_supervisor_graph(
    *,
    supervisor_llm: Any,
    tools: list[Any],
) -> Any:
    """Build and compile the supervisor StateGraph.

    Args:
        supervisor_llm: LLM instance (must support bind_tools).
        tools: List of LangChain tools to bind.

    Returns:
        Compiled StateGraph ready for .ainvoke().
    """
    llm_with_tools = supervisor_llm.bind_tools(tools)

    async def supervisor_node(state: SupervisorState) -> dict[str, Any]:
        """Supervisor LLM decides which tool to call."""
        t0 = time.perf_counter()
        response = await llm_with_tools.ainvoke(state["messages"])
        elapsed = time.perf_counter() - t0

        update: dict[str, Any] = {
            "messages": [response],
            "latency_stages": {
                **state.get("latency_stages", {}),
                "supervisor": elapsed,
            },
        }

        # Only update agent_used when a tool is actually selected
        if hasattr(response, "tool_calls") and response.tool_calls:
            update["agent_used"] = response.tool_calls[0]["name"]

        return update

    workflow = StateGraph(SupervisorState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges("supervisor", tools_condition)
    workflow.add_edge("tools", "supervisor")

    return workflow.compile()
