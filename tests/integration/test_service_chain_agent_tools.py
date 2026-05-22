"""Service-chain integration tests for agent tool routing (#554)."""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


def _make_config() -> BotConfig:
    return BotConfig(
        _env_file=None,
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
        kommo_enabled=True,
    )


def _create_bot() -> PropertyBot:
    cfg = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(cfg)


def _make_typing_cm():
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock()
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _tool_name(tool: object) -> str:
    if hasattr(tool, "name"):
        return str(tool.name)
    if hasattr(tool, "__name__"):
        return str(tool.__name__)
    return str(tool)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_manager_service_chain_includes_history_and_crm_tools():
    """Manager routing chain should pass manager-only tools into create_bot_agent."""
    bot = _create_bot()
    bot._history_service = AsyncMock()
    bot._kommo_client = AsyncMock()
    bot._resolve_user_role = AsyncMock(return_value="manager")
    bot._ainvoke_supervisor_with_recovery = AsyncMock(
        return_value={"messages": [MagicMock(content="ok")]}
    )

    fake_crm_tool = MagicMock()
    fake_crm_tool.name = "crm_get_my_leads"

    message = MagicMock()
    message.text = "покажи мои сделки"
    message.chat = MagicMock(id=12345)
    message.from_user = MagicMock(id=12345)
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.answer = AsyncMock()

    created_agent = MagicMock()
    created_agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="ok")]})
    with (
        patch("telegram_bot.bot.propagate_attributes", return_value=nullcontext()),
        patch("telegram_bot.bot.get_client", return_value=MagicMock()),
        patch("telegram_bot.bot.classify_query", return_value="OFF_TOPIC"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
        patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        patch("telegram_bot.bot.create_bot_agent", return_value=created_agent) as mock_create_agent,
        patch("telegram_bot.agents.manager_tools.create_manager_nurturing_tools", return_value=[]),
        patch("telegram_bot.agents.manager_tools.create_crm_score_sync_tool", return_value=None),
        patch(
            "telegram_bot.agents.manager_tools.build_tools_for_role",
            side_effect=lambda **kwargs: [*kwargs["base_tools"], *kwargs["manager_tools"]],
        ),
        patch("telegram_bot.agents.crm_tools.get_crm_tools", return_value=[fake_crm_tool]),
        patch("telegram_bot.agents.utility_tools.get_utility_tools", return_value=[]),
    ):
        mock_cas.typing.return_value = _make_typing_cm()
        await bot._handle_query_supervisor(message=message, pipeline_start=0.0)

        tools = mock_create_agent.call_args.kwargs["tools"]
        names = {_tool_name(t) for t in tools}
        assert "rag_search" in names
        assert "history_search" in names
        assert "crm_get_my_leads" in names
