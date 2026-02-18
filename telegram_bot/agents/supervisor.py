"""Supervisor graph — routes queries to tools (#240 Task 5).

LangGraph StateGraph with a supervisor LLM that selects the right tool
(rag_search, history_search, direct_response) based on user intent.

The supervisor loop:
1. Supervisor LLM decides which tool to call (via bind_tools)
2. ToolNode executes the selected tool
3. If the LLM returns a final message (no tool call), the loop ends
4. Tool call limit (#374): stops loop when tool_call_count >= max_tool_calls
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from telegram_bot.graph.supervisor_state import SupervisorState
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


def route_supervisor(state: dict[str, Any]) -> Literal["tools", "__end__"]:
    """Route after supervisor node: check tool call limit, then tool calls.

    Returns "__end__" when:
    - tool_call_count >= max_tool_calls (limit reached)
    - LLM returned final answer (no tool calls)

    Returns "tools" when LLM requested a tool call and limit not reached.
    """
    max_tool_calls = state.get("max_tool_calls", 5)
    tool_count = state.get("tool_call_count", 0)
    if tool_count >= max_tool_calls:
        logger.warning(
            "Tool call limit reached (%d/%d), ending supervisor loop", tool_count, max_tool_calls
        )
        return "__end__"

    messages = state.get("messages", [])
    if messages:
        last = messages[-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"

    return "__end__"


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

    @observe(name="supervisor-routing", capture_input=False, capture_output=False)
    async def supervisor_node(state: SupervisorState) -> dict[str, Any]:
        """Supervisor LLM decides which tool to call."""
        lf = get_client()
        lf.update_current_span(
            input={"message_count": len(state.get("messages", []))},
        )

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
        tool_name = ""
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_name = response.tool_calls[0]["name"]
            update["agent_used"] = tool_name
            # Increment tool call count (#374)
            update["tool_call_count"] = state.get("tool_call_count", 0) + 1

        lf.update_current_span(
            output={
                "tool_selected": tool_name or "final_answer",
                "latency_ms": round(elapsed * 1000, 1),
            },
        )

        return update

    workflow = StateGraph(SupervisorState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {"tools": "tools", "__end__": END},
    )
    workflow.add_edge("tools", "supervisor")

    return workflow.compile()
