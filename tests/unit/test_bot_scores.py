# tests/unit/test_bot_scores.py
"""Unit tests for bot Langfuse integration (LangGraph pipeline).

With the LangGraph migration, Langfuse is integrated via create_langfuse_handler
which returns a callback passed to graph.ainvoke(config={"callbacks": [handler]}).
Individual scoring happens inside graph nodes, not bot.py.
"""

import pytest


# Skip entire module if aiogram not installed
pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


@pytest.fixture
def mock_config():
    """Create mock bot config."""
    return BotConfig(
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
    )


def _create_bot(mock_config):
    """Create PropertyBot with all deps mocked."""
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3Embeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
    ):
        bot = PropertyBot(mock_config)
    return bot  # noqa: RET504 - need `with` block to exit before returning


def _make_message(text="квартиры до 100000 евро", user_id=123456789, chat_id=987654321):
    """Create mock Telegram message."""
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.chat = MagicMock()
    message.chat.id = chat_id
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.answer = AsyncMock()
    return message


class TestLangfuseHandlerCreation:
    """Test that Langfuse handler is created with correct parameters."""

    @pytest.mark.asyncio
    async def test_handler_created_with_session_id(self, mock_config):
        """Langfuse handler should receive session_id from make_initial_state."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok"})
        mock_handler = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch(
                "telegram_bot.bot.create_langfuse_handler", return_value=mock_handler
            ) as mock_create,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(_make_message())

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert "session_id" in call_kwargs
        assert call_kwargs["session_id"].startswith("chat-")

    @pytest.mark.asyncio
    async def test_handler_created_with_user_id(self, mock_config):
        """Langfuse handler should receive user_id as string."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok"})
        mock_handler = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch(
                "telegram_bot.bot.create_langfuse_handler", return_value=mock_handler
            ) as mock_create,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(_make_message(user_id=42))

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["user_id"] == "42"

    @pytest.mark.asyncio
    async def test_handler_created_with_tags(self, mock_config):
        """Langfuse handler should receive standard tags."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok"})
        mock_handler = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch(
                "telegram_bot.bot.create_langfuse_handler", return_value=mock_handler
            ) as mock_create,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(_make_message())

        call_kwargs = mock_create.call_args[1]
        assert "tags" in call_kwargs
        tags = call_kwargs["tags"]
        assert "telegram" in tags
        assert "langgraph" in tags


class TestLangfuseCallbackPassing:
    """Test that Langfuse callback is correctly passed to graph.ainvoke."""

    @pytest.mark.asyncio
    async def test_handler_passed_in_config_callbacks(self, mock_config):
        """When handler exists, it should be in config.callbacks."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok"})
        mock_handler = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.create_langfuse_handler", return_value=mock_handler),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(_make_message())

        call_config = mock_graph.ainvoke.call_args[1].get("config", {})
        assert "callbacks" in call_config
        assert mock_handler in call_config["callbacks"]

    @pytest.mark.asyncio
    async def test_no_handler_means_empty_config(self, mock_config):
        """When create_langfuse_handler returns None, config should be empty."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok"})

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.create_langfuse_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(_make_message())

        call_config = mock_graph.ainvoke.call_args[1].get("config", {})
        assert call_config == {}

    @pytest.mark.asyncio
    async def test_graph_receives_correct_state(self, mock_config):
        """Graph should receive state with user_id, session_id, query."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok"})

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.create_langfuse_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm

            await bot.handle_query(_make_message(text="студии в Несебр", user_id=42))

        state = mock_graph.ainvoke.call_args[0][0]
        assert state["messages"][0]["content"] == "студии в Несебр"
        assert state["user_id"] == 42
        assert "session_id" in state
