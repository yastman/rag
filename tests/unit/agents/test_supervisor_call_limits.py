"""Tests for supervisor tool call limits (#374).

Verifies tool_call_count tracking and routing in supervisor graph.
"""

from __future__ import annotations

from typing import get_type_hints
from unittest.mock import MagicMock, patch

import pytest

from telegram_bot.graph.supervisor_state import SupervisorState, make_supervisor_state


class TestSupervisorStateToolCallCount:
    """SupervisorState must have tool_call_count field."""

    def test_has_tool_call_count_annotation(self):
        hints = get_type_hints(SupervisorState)
        assert "tool_call_count" in hints, "SupervisorState must have tool_call_count"

    def test_initial_state_has_tool_call_count_zero(self):
        state = make_supervisor_state(user_id=1, session_id="s", query="test")
        assert state["tool_call_count"] == 0

    def test_has_max_tool_calls_annotation(self):
        hints = get_type_hints(SupervisorState)
        assert "max_tool_calls" in hints, "SupervisorState must have max_tool_calls"

    def test_initial_state_has_max_tool_calls_default(self):
        state = make_supervisor_state(user_id=1, session_id="s", query="test")
        assert state["max_tool_calls"] == 5


class TestSupervisorToolCallRouting:
    """Supervisor must route to END when tool_call_count >= max_tool_calls."""

    def test_route_supervisor_tools_when_under_limit(self):
        """When tool_call_count < max, route to tools if LLM requested tool call."""
        from telegram_bot.agents.supervisor import route_supervisor

        mock_msg = MagicMock()
        mock_msg.tool_calls = [{"name": "rag_search", "args": {}}]

        state = {
            "messages": [mock_msg],
            "tool_call_count": 2,
            "max_tool_calls": 5,
        }
        assert route_supervisor(state) == "tools"

    def test_route_supervisor_end_when_limit_reached(self):
        """When tool_call_count >= max, route to __end__ regardless of tool calls."""
        from telegram_bot.agents.supervisor import route_supervisor

        mock_msg = MagicMock()
        mock_msg.tool_calls = [{"name": "rag_search", "args": {}}]

        state = {
            "messages": [mock_msg],
            "tool_call_count": 5,
            "max_tool_calls": 5,
        }
        assert route_supervisor(state) == "__end__"

    def test_route_supervisor_end_when_no_tool_calls(self):
        """When LLM returns final answer (no tool calls), route to __end__."""
        from telegram_bot.agents.supervisor import route_supervisor

        mock_msg = MagicMock()
        mock_msg.tool_calls = []

        state = {
            "messages": [mock_msg],
            "tool_call_count": 1,
            "max_tool_calls": 5,
        }
        assert route_supervisor(state) == "__end__"

    def test_route_supervisor_end_when_no_tool_calls_attr(self):
        """When LLM message has no tool_calls attribute, route to __end__."""
        from telegram_bot.agents.supervisor import route_supervisor

        mock_msg = MagicMock(spec=[])  # no tool_calls attribute

        state = {
            "messages": [mock_msg],
            "tool_call_count": 0,
            "max_tool_calls": 5,
        }
        assert route_supervisor(state) == "__end__"


class TestSupervisorNodeToolCallIncrement:
    """supervisor_node must increment tool_call_count when tool calls are made."""

    @pytest.mark.asyncio
    async def test_supervisor_node_increments_tool_call_count(self):
        """When supervisor LLM selects a tool, tool_call_count increments.

        Tested indirectly via route_supervisor: tool_call_count in state
        must increment for the routing to eventually stop.
        """
        from telegram_bot.agents.supervisor import route_supervisor

        # Simulate state after supervisor_node incremented tool_call_count
        mock_msg = MagicMock()
        mock_msg.tool_calls = [{"name": "rag_search", "args": {}}]
        state = {"messages": [mock_msg], "tool_call_count": 4, "max_tool_calls": 5}
        assert route_supervisor(state) == "tools"

        # After one more increment, limit reached
        state["tool_call_count"] = 5
        assert route_supervisor(state) == "__end__"

    @pytest.mark.asyncio
    async def test_supervisor_node_no_increment_on_final_answer(self):
        """When supervisor returns final answer (no tools), tool_call_count unchanged."""
        from telegram_bot.agents.supervisor import route_supervisor

        mock_msg = MagicMock()
        mock_msg.tool_calls = []
        state = {"messages": [mock_msg], "tool_call_count": 0, "max_tool_calls": 5}
        assert route_supervisor(state) == "__end__"


class TestSupervisorGraphCompilation:
    """Supervisor graph must use custom routing with tool call limits."""

    def test_supervisor_graph_uses_route_supervisor(self):
        """build_supervisor_graph must use route_supervisor for conditional edges."""
        from telegram_bot.agents.supervisor import route_supervisor

        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        with (
            patch("telegram_bot.agents.supervisor.StateGraph") as mock_sg_cls,
            patch("telegram_bot.agents.supervisor.ToolNode"),
            patch("telegram_bot.agents.supervisor.get_client"),
            patch("telegram_bot.agents.supervisor.observe", lambda **_kw: lambda f: f),
        ):
            mock_workflow = MagicMock()
            mock_sg_cls.return_value = mock_workflow

            from telegram_bot.agents.supervisor import build_supervisor_graph

            build_supervisor_graph(supervisor_llm=mock_llm, tools=[])

            # Verify add_conditional_edges was called with route_supervisor
            mock_workflow.add_conditional_edges.assert_called_once()
            call_args = mock_workflow.add_conditional_edges.call_args
            assert call_args[0][1] is route_supervisor
