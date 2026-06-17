"""Smoke tests for manager flow (#2629: pruned CRM/hot-lead, kept role resolution).

Verifies: manager role resolution from config.manager_ids, tool gating.
No Docker required — uses mocked services.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from telegram_bot.agents.tool_assembly import build_tools_for_role


pytestmark = pytest.mark.no_services


@pytest.fixture
def manager_config():
    """BotConfig with manager IDs."""
    from telegram_bot.config import BotConfig

    return BotConfig(
        telegram_token="test-token",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
        manager_ids=[12345],
        realestate_database_url="postgresql://localhost/test",
    )


def _create_bot(config):
    """Create PropertyBot with all deps mocked."""
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        from telegram_bot.bot import PropertyBot

        return PropertyBot(config)


class TestManagerRoleResolution:
    """Manager role is correctly resolved from config.manager_ids."""

    @pytest.mark.asyncio
    async def test_resolve_manager_from_config(self, manager_config):
        bot = _create_bot(manager_config)
        role = await bot._resolve_user_role(12345)
        assert role == "manager"

    @pytest.mark.asyncio
    async def test_resolve_client_for_unknown_user(self, manager_config):
        bot = _create_bot(manager_config)
        role = await bot._resolve_user_role(99999)
        assert role == "client"


class TestToolGating:
    """Manager gets extra tools, client does not."""

    def test_build_tools_for_manager(self):
        base = [MagicMock(name="rag_search"), MagicMock(name="direct_response")]
        manager = [MagicMock(name="history_search")]
        tools = build_tools_for_role(role="manager", base_tools=base, manager_tools=manager)
        assert len(tools) == 3  # base(2) + manager(1)

    def test_build_tools_for_client(self):
        base = [MagicMock(name="rag_search"), MagicMock(name="direct_response")]
        manager = [MagicMock(name="history_search")]
        tools = build_tools_for_role(role="client", base_tools=base, manager_tools=manager)
        assert len(tools) == 2  # base only
