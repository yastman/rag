# tests/unit/test_bot_observability.py
"""Unit tests for bot handler observability."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHandleQueryObservability:
    """Tests for handle_query Langfuse instrumentation."""

    @pytest.fixture
    def mock_message(self):
        """Create mock Telegram message."""
        message = MagicMock()
        message.text = "квартиры до 100000 евро"
        message.from_user.id = 123456789
        message.chat.id = 987654321
        message.message_id = 42
        message.answer = AsyncMock()
        message.bot.send_chat_action = AsyncMock()
        return message

    @pytest.fixture
    def bot_handler(self):
        """Create PropertyBot handler with mocked services."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig
        from telegram_bot.services import QueryType

        # Avoid running PropertyBot.__init__ in unit tests (aiogram + real services)
        handler = PropertyBot.__new__(PropertyBot)

        handler.config = BotConfig(
            telegram_token="test",
            voyage_api_key="test",
            llm_api_key="test",
            llm_model="test-model",
            cesc_enabled=False,  # keep handle_query on the simplest path
        )
        handler._cache_initialized = True

        # Mock services used by handle_query
        handler.cache_service = MagicMock()
        handler.cache_service.initialize = AsyncMock()
        handler.cache_service.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        handler.cache_service.check_semantic_cache = AsyncMock(return_value="Cached answer")
        handler.cache_service.log_metrics = MagicMock()

        # Query preprocessor and HyDE (required by handle_query pipeline)
        handler.query_preprocessor = MagicMock()
        handler.query_preprocessor.analyze = MagicMock(
            return_value={
                "use_hyde": False,
                "normalized_query": "test",
                "rrf_weights": {"dense": 0.6, "sparse": 0.4},
            }
        )
        handler.hyde_generator = None
        handler.dense_service = MagicMock()
        handler.dense_service.embed_query = AsyncMock(return_value=[0.1] * 1024)

        # Router decision is external; make it deterministic
        handler._test_query_type = QueryType.COMPLEX

        return handler

    @pytest.mark.asyncio
    async def test_handle_query_updates_trace(self, bot_handler, mock_message):
        """handle_query should call langfuse.update_current_trace."""
        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query", autospec=True) as mock_classify_query,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            mock_langfuse.update_current_trace.assert_called_once()
            call_kwargs = mock_langfuse.update_current_trace.call_args.kwargs
            assert call_kwargs["user_id"] == "123456789"
            # Session ID format: chat-{hash}-{YYYYMMDD}
            assert call_kwargs["session_id"].startswith("chat-")
            assert "telegram" in call_kwargs["tags"]

    @pytest.mark.asyncio
    async def test_handle_query_includes_context_fingerprint(self, bot_handler, mock_message):
        """handle_query should include context_fingerprint in metadata."""
        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query", autospec=True) as mock_classify_query,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            call_kwargs = mock_langfuse.update_current_trace.call_args.kwargs
            metadata = call_kwargs["metadata"]
            assert "tenant" in metadata
            assert "cache_schema" in metadata
            assert "retrieval_version" in metadata
