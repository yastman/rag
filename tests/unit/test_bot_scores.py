# tests/unit/test_bot_scores.py
"""Unit tests for bot handler Langfuse scores."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHandleQueryScores:
    """Tests for handle_query Langfuse scores."""

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

        handler = PropertyBot.__new__(PropertyBot)
        handler.config = BotConfig(
            telegram_token="test",
            voyage_api_key="test",
            llm_api_key="test",
            llm_model="test-model",
            cesc_enabled=False,
        )
        handler._cache_initialized = True

        handler.cache_service = MagicMock()
        handler.cache_service.initialize = AsyncMock()
        handler.cache_service.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        handler.cache_service.check_semantic_cache = AsyncMock(return_value="Cached answer")
        handler.cache_service.log_metrics = MagicMock()

        handler._test_query_type = QueryType.COMPLEX
        return handler

    @pytest.mark.asyncio
    async def test_scores_cache_hit(self, bot_handler, mock_message):
        """Should score semantic_cache_hit=1.0 on cache hit."""
        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query", autospec=True) as mock_classify_query,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            # Find the semantic_cache_hit score call
            score_calls = [
                c
                for c in mock_langfuse.score_current_trace.call_args_list
                if c.kwargs.get("name") == "semantic_cache_hit"
            ]
            assert len(score_calls) == 1
            assert score_calls[0].kwargs["value"] == 1.0

    @pytest.mark.asyncio
    async def test_scores_query_type(self, bot_handler, mock_message):
        """Should score query_type based on classification."""
        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query", autospec=True) as mock_classify_query,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            # Find the query_type score call
            score_calls = [
                c
                for c in mock_langfuse.score_current_trace.call_args_list
                if c.kwargs.get("name") == "query_type"
            ]
            assert len(score_calls) == 1
            # COMPLEX = 2.0
            assert score_calls[0].kwargs["value"] == 2.0
