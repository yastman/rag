# tests/unit/test_bot_scores.py
"""Unit tests for bot handler Langfuse scores."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


EXPECTED_SCORE_NAMES = {
    "query_type",
    "latency_total_ms",
    "semantic_cache_hit",
    "embeddings_cache_hit",
    "search_cache_hit",
    "rerank_applied",
    "rerank_cache_hit",
    "results_count",
    "no_results",
    "llm_used",
}


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


class TestHandleQueryScoresAllPaths:
    """Tests for scores on all exit paths."""

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
    def bot_handler_full(self):
        """Create PropertyBot handler with all services mocked."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig

        handler = PropertyBot.__new__(PropertyBot)
        handler.config = BotConfig(
            telegram_token="test",
            voyage_api_key="test",
            llm_api_key="test",
            llm_model="test-model",
            cesc_enabled=False,
        )
        handler._cache_initialized = True

        # Mock all services
        handler.cache_service = MagicMock()
        handler.cache_service.initialize = AsyncMock()
        handler.cache_service.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        handler.cache_service.check_semantic_cache = AsyncMock(return_value="Cached answer")
        handler.cache_service.log_metrics = MagicMock()

        return handler

    @pytest.mark.asyncio
    async def test_all_10_scores_on_cache_hit(self, bot_handler_full, mock_message):
        """Cache hit path should write all 10 scores."""
        from telegram_bot.services import QueryType

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.COMPLEX

            await bot_handler_full.handle_query(mock_message)

            score_names = {
                c.kwargs["name"] for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert score_names == EXPECTED_SCORE_NAMES, (
                f"Missing: {EXPECTED_SCORE_NAMES - score_names}"
            )

    @pytest.mark.asyncio
    async def test_all_10_scores_on_llm_path(self, bot_handler_full, mock_message):
        """LLM generation path should write all 10 scores with correct values."""
        from telegram_bot.services import QueryType

        # Configure for cache miss + LLM path
        bot_handler_full.cache_service.check_semantic_cache = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_analysis = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_search = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_sparse_embedding = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_rerank = AsyncMock(return_value=None)
        bot_handler_full.cache_service.store_analysis = AsyncMock()
        bot_handler_full.cache_service.store_search_results = AsyncMock()
        bot_handler_full.cache_service.store_sparse_embedding = AsyncMock()
        bot_handler_full.cache_service.store_rerank_results = AsyncMock()
        bot_handler_full.cache_service.get_conversation_history = AsyncMock(return_value=[])
        bot_handler_full.cache_service.store_conversation_message = AsyncMock()
        bot_handler_full.cache_service.store_semantic_cache = AsyncMock()

        # Mock query analyzer
        bot_handler_full.query_analyzer = MagicMock()
        bot_handler_full.query_analyzer.analyze = AsyncMock(
            return_value={"filters": {}, "semantic_query": "test"}
        )

        # Mock Qdrant service
        bot_handler_full.qdrant_service = MagicMock()
        bot_handler_full.qdrant_service.hybrid_search_rrf = AsyncMock(
            return_value=[{"text": "Result 1", "id": "1"}, {"text": "Result 2", "id": "2"}]
        )

        # Mock Voyage service
        bot_handler_full.voyage_service = MagicMock()
        bot_handler_full.voyage_service.embed_query = AsyncMock(return_value=[0.1] * 1024)
        bot_handler_full.voyage_service.rerank = AsyncMock(
            return_value=[{"index": 0, "score": 0.9}, {"index": 1, "score": 0.8}]
        )

        # Mock LLM service - stream_answer must return async iterator directly
        bot_handler_full.llm_service = MagicMock()
        bot_handler_full.llm_service.stream_answer = MagicMock(
            return_value=AsyncIteratorMock(["Test ", "answer"])
        )
        bot_handler_full.llm_service.generate_answer = AsyncMock(return_value="Fallback answer")

        # Mock BM42 sparse vector
        bot_handler_full._http_client = MagicMock()
        bot_handler_full.bm42_url = "http://test"
        bot_handler_full._get_sparse_vector = AsyncMock(
            return_value={"indices": [1, 2], "values": [0.5, 0.3]}
        )

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
            patch("telegram_bot.bot.needs_rerank") as mock_needs_rerank,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.COMPLEX
            mock_needs_rerank.return_value = True

            # Mock message.answer to return a message for editing
            mock_temp_message = MagicMock()
            mock_temp_message.edit_text = AsyncMock()
            mock_message.answer = AsyncMock(return_value=mock_temp_message)

            await bot_handler_full.handle_query(mock_message)

            score_names = {
                c.kwargs["name"] for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert score_names == EXPECTED_SCORE_NAMES

            # Verify LLM-specific scores
            scores_dict = {
                c.kwargs["name"]: c.kwargs["value"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert scores_dict["llm_used"] == 1.0
            assert scores_dict["semantic_cache_hit"] == 0.0
            assert scores_dict["results_count"] == 2.0

    @pytest.mark.asyncio
    async def test_all_10_scores_on_no_results_path(self, bot_handler_full, mock_message):
        """No results path should write all 10 scores with no_results=1.0."""
        from telegram_bot.services import QueryType

        # Configure for no results path
        bot_handler_full.cache_service.check_semantic_cache = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_analysis = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_search = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_sparse_embedding = AsyncMock(return_value=None)
        bot_handler_full.cache_service.store_analysis = AsyncMock()
        bot_handler_full.cache_service.store_search_results = AsyncMock()
        bot_handler_full.cache_service.store_sparse_embedding = AsyncMock()

        bot_handler_full.query_analyzer = MagicMock()
        bot_handler_full.query_analyzer.analyze = AsyncMock(
            return_value={"filters": {}, "semantic_query": "test"}
        )

        bot_handler_full.qdrant_service = MagicMock()
        bot_handler_full.qdrant_service.hybrid_search_rrf = AsyncMock(return_value=[])

        bot_handler_full.voyage_service = MagicMock()
        bot_handler_full.voyage_service.embed_query = AsyncMock(return_value=[0.1] * 1024)

        bot_handler_full._get_sparse_vector = AsyncMock(return_value={"indices": [], "values": []})

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.SIMPLE

            await bot_handler_full.handle_query(mock_message)

            score_names = {
                c.kwargs["name"] for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert score_names == EXPECTED_SCORE_NAMES

            scores_dict = {
                c.kwargs["name"]: c.kwargs["value"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert scores_dict["no_results"] == 1.0
            assert scores_dict["llm_used"] == 0.0
            assert scores_dict["results_count"] == 0.0

    @pytest.mark.asyncio
    async def test_all_10_scores_on_chitchat_path(self, bot_handler_full, mock_message):
        """CHITCHAT path should write all 10 scores with query_type=0."""
        from telegram_bot.services import QueryType

        mock_message.text = "Привет!"

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
            patch("telegram_bot.bot.get_chitchat_response") as mock_chitchat,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.CHITCHAT
            mock_chitchat.return_value = "Привет! Чем могу помочь?"

            await bot_handler_full.handle_query(mock_message)

            score_names = {
                c.kwargs["name"] for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert score_names == EXPECTED_SCORE_NAMES

            scores_dict = {
                c.kwargs["name"]: c.kwargs["value"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert scores_dict["query_type"] == 0.0  # CHITCHAT
            assert scores_dict["semantic_cache_hit"] == 0.0
            assert scores_dict["llm_used"] == 0.0

    @pytest.mark.asyncio
    async def test_latency_recorded_positive(self, bot_handler_full, mock_message):
        """latency_total_ms should be > 0."""
        from telegram_bot.services import QueryType

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.COMPLEX

            await bot_handler_full.handle_query(mock_message)

            latency_calls = [
                c
                for c in mock_langfuse.score_current_trace.call_args_list
                if c.kwargs["name"] == "latency_total_ms"
            ]
            assert len(latency_calls) == 1
            assert latency_calls[0].kwargs["value"] > 0


class AsyncIteratorMock:
    """Mock for async iterator (streaming)."""

    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration:
            raise StopAsyncIteration
