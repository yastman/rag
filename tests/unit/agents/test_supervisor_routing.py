"""Tests for supervisor graph routing (#240 Task 5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


def _make_config(user_id: int = 42, session_id: str = "s-1") -> RunnableConfig:
    return RunnableConfig(configurable={"user_id": user_id, "session_id": session_id})


# Real @tool functions for ToolNode (ToolNode needs introspectable callables)
@tool
async def rag_search(query: str) -> str:
    """Search the knowledge base for domain-specific information."""
    return f"RAG result for: {query}"


@tool
async def history_search(query: str) -> str:
    """Search conversation history for past interactions."""
    return f"History result for: {query}"


@tool
async def direct_response(message: str) -> str:
    """Respond directly to the user without searching."""
    return message


ALL_TOOLS = [rag_search, history_search, direct_response]


def _mock_llm_then_final(tool_name: str, tool_args: dict):
    """Create LLM that first returns a tool call, then returns a final message.

    The supervisor loop: supervisor -> tool -> supervisor (final).
    So the LLM must be called twice: first with tool_call, then with final answer.
    """
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"id": "call_test123", "name": tool_name, "args": tool_args}],
    )
    final_msg = AIMessage(content="Final answer based on tool result.")

    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke = AsyncMock(side_effect=[tool_call_msg, final_msg])
    return mock_llm


async def test_supervisor_routes_domain_query_to_rag_search():
    """Domain query (e.g., real estate) is routed to rag_search."""
    from telegram_bot.agents.supervisor import build_supervisor_graph

    mock_llm = _mock_llm_then_final("rag_search", {"query": "цены на квартиры"})

    graph = build_supervisor_graph(supervisor_llm=mock_llm, tools=ALL_TOOLS)
    config = _make_config()
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "цены на квартиры"}]},
        config=config,
    )

    assert result.get("agent_used") == "rag_search"


async def test_supervisor_routes_history_to_history_search():
    """History query is routed to history_search."""
    from telegram_bot.agents.supervisor import build_supervisor_graph

    mock_llm = _mock_llm_then_final("history_search", {"query": "прошлые вопросы"})

    graph = build_supervisor_graph(supervisor_llm=mock_llm, tools=ALL_TOOLS)
    config = _make_config()
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "что я спрашивал раньше?"}]},
        config=config,
    )

    assert result.get("agent_used") == "history_search"


async def test_supervisor_routes_chitchat_to_direct_response():
    """Chitchat is routed to direct_response."""
    from telegram_bot.agents.supervisor import build_supervisor_graph

    mock_llm = _mock_llm_then_final("direct_response", {"message": "Привет! Чем могу помочь?"})

    graph = build_supervisor_graph(supervisor_llm=mock_llm, tools=ALL_TOOLS)
    config = _make_config()
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "привет"}]},
        config=config,
    )

    assert result.get("agent_used") == "direct_response"
