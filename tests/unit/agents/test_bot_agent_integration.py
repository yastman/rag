"""Tests for bot.py integration with create_agent (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_message():
    """Mock aiogram Message."""
    msg = MagicMock()
    msg.text = "Цены на квартиры в Софии?"
    msg.chat.id = 12345
    msg.from_user.id = 67890
    msg.bot = AsyncMock()
    msg.bot.send_chat_action = AsyncMock()
    msg.answer = AsyncMock()
    return msg


async def test_handle_query_supervisor_imports_available():
    """Verify new imports are available in bot module."""
    from telegram_bot.agents.agent import create_bot_agent
    from telegram_bot.agents.context import BotContext
    from telegram_bot.agents.crm_tools import get_crm_tools
    from telegram_bot.agents.history_tool import history_search
    from telegram_bot.agents.rag_tool import rag_search
    from telegram_bot.observability import create_callback_handler

    assert callable(create_bot_agent)
    assert hasattr(rag_search, "ainvoke")
    assert hasattr(history_search, "ainvoke")
    assert callable(get_crm_tools)
    assert callable(create_callback_handler)
    assert BotContext is not None


async def test_bot_context_has_required_fields():
    """BotContext has all fields needed by _handle_query_supervisor."""
    from telegram_bot.agents.context import BotContext

    ctx = BotContext(
        telegram_user_id=42,
        session_id="test",
        language="ru",
        kommo_client=None,
        history_service=None,
        embeddings=MagicMock(),
        sparse_embeddings=MagicMock(),
        qdrant=MagicMock(),
        cache=MagicMock(),
        reranker=None,
        llm=MagicMock(),
        content_filter_enabled=True,
        guard_mode="hard",
    )
    assert ctx.telegram_user_id == 42
    assert ctx.language == "ru"


async def test_get_crm_tools_returns_list():
    """get_crm_tools returns list of tool objects."""
    from telegram_bot.agents.crm_tools import get_crm_tools

    tools = get_crm_tools()
    assert isinstance(tools, list)
    assert len(tools) == 12
    names = {t.name for t in tools}
    assert "crm_get_deal" in names
    assert "crm_create_lead" in names
