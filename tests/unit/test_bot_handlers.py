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
        bm42_url="http://localhost:8000",
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
