"""Unit tests for telegram_bot/bot.py handlers."""

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
    )


class TestPropertyBotInit:
    """Test PropertyBot initialization."""

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_init_creates_services(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test that initialization creates all services."""
        bot = PropertyBot(mock_config)

        assert bot.config == mock_config
        mock_cache.assert_called_once()
        mock_analyzer.assert_called_once()
        mock_voyage.assert_called_once()
        mock_qdrant.assert_called_once()
        mock_llm.assert_called_once()


class TestCommandHandlers:
    """Test command handlers."""

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_cmd_start(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test /start command handler."""
        bot = PropertyBot(mock_config)

        message = MagicMock()
        message.answer = AsyncMock()

        await bot.cmd_start(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Привет" in call_args
        assert "бот по недвижимости" in call_args

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_cmd_help(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test /help command handler."""
        bot = PropertyBot(mock_config)

        message = MagicMock()
        message.answer = AsyncMock()

        await bot.cmd_help(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Примеры запросов" in call_args
        assert "/clear" in call_args
        assert "/stats" in call_args

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_cmd_clear(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test /clear command handler."""
        mock_cache_instance = MagicMock()
        mock_cache_instance.clear_conversation_history = AsyncMock()
        mock_cache.return_value = mock_cache_instance

        bot = PropertyBot(mock_config)

        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = 12345
        message.answer = AsyncMock()

        await bot.cmd_clear(message)

        mock_cache_instance.clear_conversation_history.assert_called_once_with(12345)
        message.answer.assert_called_once()
        assert "очищена" in message.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_cmd_stats(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test /stats command handler."""
        mock_cache_instance = MagicMock()
        mock_cache_instance.get_metrics.return_value = {
            "overall_hit_rate": 75.0,
            "total_requests": 100,
            "by_type": {
                "semantic": {"hit_rate": 80.0, "hits": 40, "requests": 50},
                "embeddings": {"hit_rate": 70.0, "hits": 35, "requests": 50},
            },
        }
        mock_cache.return_value = mock_cache_instance

        bot = PropertyBot(mock_config)

        message = MagicMock()
        message.answer = AsyncMock()

        await bot.cmd_stats(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Статистика" in call_args
        assert "75" in call_args  # Overall hit rate


class TestFormatResults:
    """Test _format_results method."""

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_format_results_basic(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test formatting search results."""
        bot = PropertyBot(mock_config)

        results = [
            {
                "metadata": {
                    "title": "Квартира 1",
                    "price": 50000,
                    "city": "Несебр",
                    "rooms": 2,
                },
                "score": 0.95,
            },
            {
                "metadata": {
                    "title": "Квартира 2",
                    "price": 75000,
                    "city": "Бургас",
                    "area": 65,
                },
                "score": 0.85,
            },
        ]

        formatted = bot._format_results(results)

        assert "Квартира 1" in formatted
        assert "50,000€" in formatted
        assert "Несебр" in formatted
        assert "2 комн" in formatted
        assert "0.95" in formatted

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_format_results_limits_to_three(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test that formatting limits to 3 results."""
        bot = PropertyBot(mock_config)

        results = [
            {"metadata": {"title": f"Квартира {i}"}, "score": 0.9 - i * 0.1} for i in range(5)
        ]

        formatted = bot._format_results(results)

        assert "Квартира 0" in formatted
        assert "Квартира 1" in formatted
        assert "Квартира 2" in formatted
        assert "Квартира 3" not in formatted
        assert "Квартира 4" not in formatted


class TestGetSparseVector:
    """Test _get_sparse_vector method."""

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_get_sparse_vector_success(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test successful sparse vector retrieval."""
        bot = PropertyBot(mock_config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"indices": [1, 2, 3], "values": [0.5, 0.3, 0.2]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            bot._http_client = mock_client_instance

            result = await bot._get_sparse_vector("test query")

            assert result == {"indices": [1, 2, 3], "values": [0.5, 0.3, 0.2]}

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_get_sparse_vector_error_fallback(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test sparse vector fallback on error."""
        bot = PropertyBot(mock_config)

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Network error")
        bot._http_client = mock_client

        result = await bot._get_sparse_vector("test query")

        # Should return empty sparse vector
        assert result == {"indices": [], "values": []}


class TestBotLifecycle:
    """Test bot start/stop lifecycle."""

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_stop_closes_all_services(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test that stop() closes all services."""
        mock_cache_instance = MagicMock()
        mock_cache_instance.close = AsyncMock()
        mock_cache.return_value = mock_cache_instance

        mock_analyzer_instance = MagicMock()
        mock_analyzer_instance.close = AsyncMock()
        mock_analyzer.return_value = mock_analyzer_instance

        mock_llm_instance = MagicMock()
        mock_llm_instance.close = AsyncMock()
        mock_llm.return_value = mock_llm_instance

        mock_qdrant_instance = MagicMock()
        mock_qdrant_instance.close = AsyncMock()
        mock_qdrant.return_value = mock_qdrant_instance

        mock_bot_instance = MagicMock()
        mock_bot_instance.session = MagicMock()
        mock_bot_instance.session.close = AsyncMock()
        mock_bot.return_value = mock_bot_instance

        bot = PropertyBot(mock_config)
        bot._http_client = AsyncMock()

        await bot.stop()

        mock_cache_instance.close.assert_called_once()
        mock_analyzer_instance.close.assert_called_once()
        mock_llm_instance.close.assert_called_once()
        mock_qdrant_instance.close.assert_called_once()


class TestHandleQuery:
    """Test handle_query method - main RAG pipeline."""

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    @patch("telegram_bot.bot.classify_query")
    @patch("telegram_bot.bot.get_chitchat_response")
    async def test_handle_query_chitchat_routing(
        self,
        mock_chitchat_response,
        mock_classify,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test chitchat queries skip RAG pipeline."""
        from telegram_bot.services import QueryType

        mock_classify.return_value = QueryType.CHITCHAT
        mock_chitchat_response.return_value = "Привет! Чем могу помочь?"

        bot = PropertyBot(mock_config)

        message = MagicMock()
        message.text = "Привет!"
        message.from_user = MagicMock()
        message.from_user.id = 12345
        message.answer = AsyncMock()

        await bot.handle_query(message)

        message.answer.assert_called_once()
        # RAG pipeline should not be called (voyage.embed_query)
        bot.voyage_service.embed_query.assert_not_called()

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    @patch("telegram_bot.bot.classify_query")
    @patch("telegram_bot.bot.is_personalized_query")
    async def test_handle_query_semantic_cache_hit(
        self,
        mock_is_personalized,
        mock_classify,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test semantic cache hit returns cached answer."""
        from telegram_bot.services import QueryType

        mock_classify.return_value = QueryType.SIMPLE
        mock_is_personalized.return_value = False

        cache_instance = MagicMock()
        cache_instance.initialize = AsyncMock()
        cache_instance.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        cache_instance.check_semantic_cache = AsyncMock(
            return_value="Cached answer from semantic cache"
        )
        cache_instance.log_metrics = MagicMock()
        mock_cache.return_value = cache_instance

        user_ctx_instance = MagicMock()
        user_ctx_instance.get_context = AsyncMock(return_value={})
        mock_user_ctx.return_value = user_ctx_instance

        bot = PropertyBot(mock_config)

        message = MagicMock()
        message.text = "Квартиры в Несебр"
        message.from_user = MagicMock()
        message.from_user.id = 12345
        message.answer = AsyncMock()
        message.bot = MagicMock()
        message.bot.send_chat_action = AsyncMock()

        await bot.handle_query(message)

        # Cached answer should be returned
        call_args = message.answer.call_args[0][0]
        assert "Cached answer" in call_args

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    @patch("telegram_bot.bot.classify_query")
    @patch("telegram_bot.bot.is_personalized_query")
    async def test_handle_query_no_results(
        self,
        mock_is_personalized,
        mock_classify,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test handling when search returns no results."""
        from telegram_bot.services import QueryType

        mock_classify.return_value = QueryType.SIMPLE
        mock_is_personalized.return_value = False

        # Setup cache service
        cache_instance = MagicMock()
        cache_instance.initialize = AsyncMock()
        cache_instance.get_cached_embedding = AsyncMock(return_value=None)
        cache_instance.store_embedding = AsyncMock()
        cache_instance.check_semantic_cache = AsyncMock(return_value=None)
        cache_instance.get_cached_analysis = AsyncMock(return_value=None)
        cache_instance.store_analysis = AsyncMock()
        cache_instance.get_cached_search = AsyncMock(return_value=None)
        cache_instance.get_cached_sparse_embedding = AsyncMock(return_value=None)
        cache_instance.store_sparse_embedding = AsyncMock()
        cache_instance.store_search_results = AsyncMock()
        mock_cache.return_value = cache_instance

        # Setup voyage
        voyage_instance = MagicMock()
        voyage_instance.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock_voyage.return_value = voyage_instance

        # Setup analyzer
        analyzer_instance = MagicMock()
        analyzer_instance.analyze = AsyncMock(return_value={"filters": {}})
        mock_analyzer.return_value = analyzer_instance

        # Setup qdrant to return empty results
        qdrant_instance = MagicMock()
        qdrant_instance.hybrid_search_rrf = AsyncMock(return_value=[])
        mock_qdrant.return_value = qdrant_instance

        # Setup user context
        user_ctx_instance = MagicMock()
        user_ctx_instance.get_context = AsyncMock(return_value={})
        mock_user_ctx.return_value = user_ctx_instance

        bot = PropertyBot(mock_config)

        # Mock _get_sparse_vector
        async def mock_sparse(text):
            return {"indices": [1, 2], "values": [0.5, 0.5]}

        bot._get_sparse_vector = mock_sparse

        message = MagicMock()
        message.text = "Несуществующий запрос"
        message.from_user = MagicMock()
        message.from_user.id = 12345
        message.answer = AsyncMock()
        message.bot = MagicMock()
        message.bot.send_chat_action = AsyncMock()
        message.chat = MagicMock()
        message.chat.id = 12345

        await bot.handle_query(message)

        # Should show "nothing found" message
        call_args = message.answer.call_args[0][0]
        assert "Ничего не нашел" in call_args


class TestBotStart:
    """Test bot start method."""

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_start_initializes_cache(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test that start() initializes cache."""
        mock_cache_instance = MagicMock()
        mock_cache_instance.initialize = AsyncMock()
        mock_cache.return_value = mock_cache_instance

        bot = PropertyBot(mock_config)
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()

        await bot.start()

        mock_cache_instance.initialize.assert_called_once()
        bot.dp.start_polling.assert_called_once()

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    async def test_start_skips_reinit_if_already_initialized(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test that start() skips cache init if already done."""
        mock_cache_instance = MagicMock()
        mock_cache_instance.initialize = AsyncMock()
        mock_cache.return_value = mock_cache_instance

        bot = PropertyBot(mock_config)
        bot._cache_initialized = True  # Already initialized
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()

        await bot.start()

        # Should not reinitialize
        mock_cache_instance.initialize.assert_not_called()


class TestSetupMiddlewares:
    """Test middleware setup."""

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    @patch("telegram_bot.bot.setup_throttling_middleware")
    @patch("telegram_bot.bot.setup_error_middleware")
    def test_middlewares_configured(
        self,
        mock_error_mw,
        mock_throttle_mw,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test that middlewares are configured on init."""
        PropertyBot(mock_config)

        mock_throttle_mw.assert_called_once()
        mock_error_mw.assert_called_once()


class TestRegisterHandlers:
    """Test handler registration."""

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_handlers_registered(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test that handlers are registered on init."""
        bot = PropertyBot(mock_config)

        # Dispatcher should have message handlers registered
        # We can't easily check the exact handlers without more complex mocking,
        # but we can verify the bot has the expected methods
        assert hasattr(bot, "cmd_start")
        assert hasattr(bot, "cmd_help")
        assert hasattr(bot, "cmd_clear")
        assert hasattr(bot, "cmd_stats")
        assert hasattr(bot, "handle_query")


class TestFormatResultsEdgeCases:
    """Additional edge case tests for _format_results."""

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_format_results_empty(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test formatting empty results."""
        bot = PropertyBot(mock_config)

        formatted = bot._format_results([])
        assert formatted == ""

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_format_results_with_distance_to_sea(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test formatting with distance_to_sea field."""
        bot = PropertyBot(mock_config)

        results = [
            {
                "metadata": {
                    "title": "Beach apartment",
                    "distance_to_sea": 150,
                },
                "score": 0.9,
            }
        ]

        formatted = bot._format_results(results)
        assert "150 м до моря" in formatted

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_format_results_with_area(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test formatting with area field."""
        bot = PropertyBot(mock_config)

        results = [
            {
                "metadata": {
                    "title": "Spacious apartment",
                    "area": 85,
                },
                "score": 0.85,
            }
        ]

        formatted = bot._format_results(results)
        assert "85 м²" in formatted

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_format_results_string_price(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test formatting with string price (non-numeric)."""
        bot = PropertyBot(mock_config)

        results = [
            {
                "metadata": {
                    "title": "Apartment",
                    "price": "По запросу",
                },
                "score": 0.9,
            }
        ]

        formatted = bot._format_results(results)
        assert "По запросу€" in formatted

    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    def test_format_results_missing_title(
        self,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test formatting with missing title."""
        bot = PropertyBot(mock_config)

        results = [
            {
                "metadata": {"price": 50000},
                "score": 0.9,
            }
        ]

        formatted = bot._format_results(results)
        assert "N/A" in formatted


class TestCESCIntegration:
    """Test CESC personalization integration."""

    @pytest.mark.asyncio
    @patch("telegram_bot.bot.Bot")
    @patch("telegram_bot.bot.CacheService")
    @patch("telegram_bot.bot.QueryAnalyzer")
    @patch("telegram_bot.bot.VoyageService")
    @patch("telegram_bot.bot.QdrantService")
    @patch("telegram_bot.bot.LLMService")
    @patch("telegram_bot.bot.UserContextService")
    @patch("telegram_bot.bot.CESCPersonalizer")
    @patch("telegram_bot.bot.classify_query")
    @patch("telegram_bot.bot.is_personalized_query")
    async def test_personalization_applied_to_cached_answer(
        self,
        mock_is_personalized,
        mock_classify,
        mock_cesc,
        mock_user_ctx,
        mock_llm,
        mock_qdrant,
        mock_voyage,
        mock_analyzer,
        mock_cache,
        mock_bot,
        mock_config,
    ):
        """Test CESC personalizes cached answers."""
        from telegram_bot.services import QueryType

        mock_classify.return_value = QueryType.SIMPLE
        mock_is_personalized.return_value = True

        # Enable CESC in config
        mock_config.cesc_enabled = True

        # Setup cache service
        cache_instance = MagicMock()
        cache_instance.initialize = AsyncMock()
        cache_instance.check_semantic_cache = AsyncMock(return_value="Cached answer")
        cache_instance.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        cache_instance.log_metrics = MagicMock()
        mock_cache.return_value = cache_instance

        # Setup user context
        user_ctx_instance = MagicMock()
        user_ctx_instance.get_context = AsyncMock(return_value={"preferred_city": "Nesebar"})
        user_ctx_instance.update_from_query = AsyncMock()
        mock_user_ctx.return_value = user_ctx_instance

        # Setup CESC personalizer
        cesc_instance = MagicMock()
        cesc_instance.should_personalize = MagicMock(return_value=True)
        cesc_instance.personalize = AsyncMock(return_value="Personalized answer")
        mock_cesc.return_value = cesc_instance

        bot = PropertyBot(mock_config)

        message = MagicMock()
        message.text = "Покажи квартиры"
        message.from_user = MagicMock()
        message.from_user.id = 12345
        message.answer = AsyncMock()
        message.bot = MagicMock()
        message.bot.send_chat_action = AsyncMock()

        await bot.handle_query(message)

        # CESC should personalize
        cesc_instance.personalize.assert_called_once()

        # Personalized answer should be sent
        call_args = message.answer.call_args[0][0]
        assert "Personalized" in call_args
