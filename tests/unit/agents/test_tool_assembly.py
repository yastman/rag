"""Tests for telegram_bot/agents/tool_assembly.py build_agent_tools() helper."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from telegram_bot.agents.tool_assembly import build_agent_tools


@pytest.fixture
def mock_config():
    """Minimal config mock for tool assembly tests."""
    return MagicMock()


class TestBuildAgentTools:
    """Test build_agent_tools helper."""

    def test_client_role_returns_base_plus_utility(self, mock_config):
        """Client role returns [rag_search, apartment_search] + utility tools."""
        tools = build_agent_tools(
            role="client",
            config=mock_config,
            history_service=None,
        )

        tool_names = [getattr(t, "name", str(t)) for t in tools]
        assert "rag_search" in tool_names
        assert "apartment_search" in tool_names
        assert len(tools) > 2

    def test_manager_role_includes_history_when_provided(self, mock_config):
        """Manager role adds history_search when history_service is provided."""
        tools = build_agent_tools(
            role="manager",
            config=mock_config,
            history_service=MagicMock(),
        )

        tool_names = [getattr(t, "name", str(t)) for t in tools]
        assert "rag_search" in tool_names
        assert "apartment_search" in tool_names
        assert "history_search" in tool_names

    def test_manager_without_history_service_omits_history_search(self, mock_config):
        """Manager without history_service should not have history_search tool."""
        tools = build_agent_tools(
            role="manager",
            config=mock_config,
            history_service=None,
        )

        tool_names = [getattr(t, "name", str(t)) for t in tools]
        assert "history_search" not in tool_names

    def test_invalid_role_raises_value_error(self, mock_config):
        """Passing an unrecognized role raises ValueError."""
        with pytest.raises(ValueError, match="Unknown role 'managr'"):
            build_agent_tools(
                role="managr",
                config=mock_config,
                history_service=None,
            )
