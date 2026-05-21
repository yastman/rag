"""Tests for telegram_bot/agents/tool_assembly.py build_agent_tools() helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from telegram_bot.agents.tool_assembly import build_agent_tools


@pytest.fixture
def mock_config():
    """Minimal config mock for tool assembly tests."""
    config = MagicMock()
    config.kommo_enabled = False
    config.kommo_lead_score_field_id = 0
    config.kommo_lead_band_field_id = 0
    return config


class TestBuildAgentTools:
    """Test build_agent_tools helper."""

    def test_client_role_returns_base_plus_utility(self, mock_config):
        """Client role returns [rag_search, apartment_search] + utility tools."""
        tools = build_agent_tools(
            role="client",
            config=mock_config,
            history_service=None,
            funnel_analytics_service=None,
            nurturing_service=None,
            lead_scoring_store=None,
            kommo_client=None,
        )

        # Should contain at least base tools + utility tools
        tool_names = [getattr(t, "name", str(t)) for t in tools]
        assert "rag_search" in tool_names
        assert "apartment_search" in tool_names
        # Utility tools are appended
        assert len(tools) > 2

    def test_manager_role_returns_extended_tools(self, mock_config):
        """Manager role returns base + manager tools + utility."""
        mock_config.kommo_enabled = True
        kommo_client = MagicMock()

        tools = build_agent_tools(
            role="manager",
            config=mock_config,
            history_service=MagicMock(),
            funnel_analytics_service=MagicMock(),
            nurturing_service=MagicMock(),
            lead_scoring_store=MagicMock(),
            kommo_client=kommo_client,
        )

        tool_names = [getattr(t, "name", str(t)) for t in tools]
        assert "rag_search" in tool_names
        assert "apartment_search" in tool_names
        assert "history_search" in tool_names
        # Manager tools include nurturing + CRM
        assert len(tools) > 5

    def test_manager_without_history_service_omits_history_search(self, mock_config):
        """Manager without history_service should not have history_search tool."""
        tools = build_agent_tools(
            role="manager",
            config=mock_config,
            history_service=None,
            funnel_analytics_service=MagicMock(),
            nurturing_service=MagicMock(),
            lead_scoring_store=None,
            kommo_client=None,
        )

        tool_names = [getattr(t, "name", str(t)) for t in tools]
        assert "history_search" not in tool_names

    def test_manager_without_kommo_enabled_omits_crm_tools(self, mock_config):
        """Manager without kommo_enabled should not include CRM tools."""
        mock_config.kommo_enabled = False

        tools = build_agent_tools(
            role="manager",
            config=mock_config,
            history_service=MagicMock(),
            funnel_analytics_service=MagicMock(),
            nurturing_service=MagicMock(),
            lead_scoring_store=None,
            kommo_client=MagicMock(),
        )

        tool_names = [getattr(t, "name", str(t)) for t in tools]
        # CRM tools should not be present when kommo_enabled=False
        crm_tools = [n for n in tool_names if "crm" in n.lower() or "kommo" in n.lower()]
        # The only possible CRM-related is the score sync (which needs lead_scoring_store)
        # With lead_scoring_store=None, no CRM tools at all
        assert not crm_tools

    def test_manager_without_kommo_client_omits_crm_tools(self, mock_config):
        """Manager without kommo_client should not include CRM tools even if enabled."""
        mock_config.kommo_enabled = True

        tools = build_agent_tools(
            role="manager",
            config=mock_config,
            history_service=None,
            funnel_analytics_service=MagicMock(),
            nurturing_service=MagicMock(),
            lead_scoring_store=None,
            kommo_client=None,
        )

        tool_names = [getattr(t, "name", str(t)) for t in tools]
        # get_crm_tools not appended when kommo_client is None
        from telegram_bot.agents.crm_tools import get_crm_tools

        crm_tool_names = [getattr(t, "name", str(t)) for t in get_crm_tools()]
        for crm_name in crm_tool_names:
            assert crm_name not in tool_names
