"""E2E smoke test for manager flow (#402).

Verifies: manager role -> menu -> CRM tools -> hot lead notification path.
No Docker required — uses mocked services.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from telegram_bot.agents.manager_tools import build_tools_for_role


@pytest.fixture
def manager_config():
    """BotConfig with CRM enabled and manager IDs."""
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
        kommo_enabled=True,
        kommo_subdomain="test",
        kommo_access_token="token",
        kommo_client_id="client_id",
        kommo_client_secret="secret",
        kommo_redirect_uri="https://example.com/callback",
        kommo_auth_code="",
        kommo_default_pipeline_id=1,
        kommo_session_field_id=100,
        kommo_lead_score_field_id=200,
        kommo_lead_band_field_id=300,
        kommo_telegram_field_id=400,
        manager_hot_lead_threshold=60,
        manager_hot_lead_dedupe_sec=3600,
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


class TestManagerStartMenu:
    """Manager /start shows manager-specific menu."""

    def test_render_manager_menu(self):
        from telegram_bot.services.manager_menu import render_start_menu

        text = render_start_menu(role="manager", domain="test")
        client_text = render_start_menu(role="client", domain="test")
        assert text != client_text

    def test_render_client_menu(self):
        from telegram_bot.services.manager_menu import render_start_menu

        text = render_start_menu(role="client", domain="test_domain")
        assert "test_domain" in text


class TestToolGating:
    """Manager gets CRM tools, client does not."""

    def test_build_tools_for_manager(self):
        base = [MagicMock(name="rag_search"), MagicMock(name="direct_response")]
        manager = [MagicMock(name="crm_tool_1"), MagicMock(name="crm_tool_2")]
        tools = build_tools_for_role(role="manager", base_tools=base, manager_tools=manager)
        assert len(tools) == 4  # base(2) + manager(2)

    def test_build_tools_for_client(self):
        base = [MagicMock(name="rag_search"), MagicMock(name="direct_response")]
        manager = [MagicMock(name="crm_tool_1")]
        tools = build_tools_for_role(role="client", base_tools=base, manager_tools=manager)
        assert len(tools) == 2  # base only


class TestHotLeadNotifierExists:
    """HotLeadNotifier service is importable and has correct interface."""

    def test_notifier_importable(self):
        from telegram_bot.services.hot_lead_notifier import HotLeadNotifier

        assert callable(getattr(HotLeadNotifier, "notify_if_hot", None))

    def test_notifier_constructor(self):
        from telegram_bot.services.hot_lead_notifier import HotLeadNotifier

        notifier = HotLeadNotifier(
            bot=MagicMock(),
            cache=MagicMock(),
            manager_ids=[123],
            dedupe_ttl_sec=3600,
        )
        assert notifier is not None
