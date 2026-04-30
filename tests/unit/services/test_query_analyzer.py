"""Unit tests for QueryAnalyzer service (Instructor SDK)."""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from telegram_bot.services.query_analyzer import QueryAnalysisResult, QueryAnalyzer


# =============================================================================
# TestQueryAnalyzerInit
# =============================================================================


class TestQueryAnalyzerInit:
    """Tests for QueryAnalyzer initialization."""

    def test_init_stores_api_key(self):
        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
        assert analyzer.api_key == "test-api-key"

    def test_init_stores_base_url(self):
        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
        assert analyzer.base_url == "http://localhost:8000"

    def test_init_strips_trailing_slash(self):
        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000/")
        assert analyzer.base_url == "http://localhost:8000"

    def test_init_default_model(self):
        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
        assert analyzer.model == "gpt-4o-mini"

    def test_init_custom_model(self):
        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o"
        )
        assert analyzer.model == "gpt-4o"

    def test_init_creates_openai_client(self):
        from openai import AsyncOpenAI

        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
        assert isinstance(analyzer.client, AsyncOpenAI)

    def test_init_with_different_models(self):
        test_models = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "glm-4"]
        for model in test_models:
            analyzer = QueryAnalyzer(
                api_key="test-key", base_url="http://localhost:8000", model=model
            )
            assert analyzer.model == model, f"Failed for model: {model}"


# =============================================================================
# TestQueryAnalyzerAnalyze
# =============================================================================


class TestQueryAnalyzerAnalyze:
    """Tests for QueryAnalyzer.analyze method."""

    @pytest.fixture
    def analyzer(self):
        """Create QueryAnalyzer with mocked Instructor client."""
        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
        )
        analyzer._instructor_client = AsyncMock()
        return analyzer

    async def test_analyze_returns_filters_and_semantic_query(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={"price": {"lt": 100000}, "city": "Несебр"},
                semantic_query="уютная квартира с хорошим ремонтом",
            )
        )

        result = await analyzer.analyze("квартира до 100000 евро в Несебре с хорошим ремонтом")

        assert "filters" in result
        assert "semantic_query" in result
        assert result["filters"] == {"price": {"lt": 100000}, "city": "Несебр"}
        assert result["semantic_query"] == "уютная квартира с хорошим ремонтом"

    async def test_analyze_calls_instructor_sdk(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test query")
        )

        await analyzer.analyze("test query")

        analyzer._instructor_client.chat.completions.create.assert_called_once()

    async def test_analyze_uses_instructor_response_model(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_model"] is QueryAnalysisResult
        assert call_kwargs["max_retries"] == 2

    async def test_analyze_uses_zero_temperature(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.0

    async def test_analyze_sends_query_in_user_message(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        test_query = "квартира в Солнечном берегу до 50000 евро"
        await analyzer.analyze(test_query)

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        user_message = next(m for m in messages if m["role"] == "user")
        assert test_query in user_message["content"]

    async def test_analyze_uses_specified_model(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

    async def test_analyze_fallback_on_instructor_error(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Instructor validation failed")
        )

        original_query = "квартира в Бургасе"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_api_connection_error(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock())
        )

        original_query = "студия на первой линии"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_rate_limit_error(self, analyzer):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="Rate limited",
                response=mock_resp,
                body=None,
            )
        )

        original_query = "квартира с видом на море"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_timeout_error(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        original_query = "квартира с видом на море"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_returns_empty_filters_when_none_found(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="красивая квартира у моря")
        )

        result = await analyzer.analyze("красивая квартира у моря")

        assert result["filters"] == {}
        assert result["semantic_query"] == "красивая квартира у моря"

    async def test_analyze_handles_missing_semantic_query_in_response(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={"price": {"lt": 50000}}, semantic_query="")
        )

        original_query = "квартира до 50000 евро"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {"price": {"lt": 50000}}
        assert result["semantic_query"] == original_query

    async def test_analyze_handles_missing_filters_in_response(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(semantic_query="уютная квартира")
        )

        result = await analyzer.analyze("уютная квартира")

        assert result["filters"] == {}
        assert result["semantic_query"] == "уютная квартира"

    async def test_analyze_with_complex_filters(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={
                    "price": {"lt": 100000, "gt": 50000},
                    "rooms": 2,
                    "city": "Солнечный берег",
                    "area": {"gte": 50},
                    "distance_to_sea": {"lt": 500},
                },
                semantic_query="квартира с хорошим ремонтом",
            )
        )

        result = await analyzer.analyze(
            "2-комнатная квартира от 50000 до 100000 евро в Солнечном берегу"
        )

        assert result["filters"]["price"] == {"lt": 100000, "gt": 50000}
        assert result["filters"]["rooms"] == 2
        assert result["filters"]["city"] == "Солнечный берег"

    async def test_analyze_sets_max_tokens(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 1000

    async def test_analyze_with_unicode_query(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={"city": "Варна"}, semantic_query="квартира с мебелью"
            )
        )

        result = await analyzer.analyze("Ищу квартиру с мебелью в Варне")

        assert result["filters"]["city"] == "Варна"
        assert result["semantic_query"] == "квартира с мебелью"

    async def test_analyze_handles_instructor_failure(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Instructor failed")
        )

        result = await analyzer.analyze("test query")

        assert result["filters"] == {}
        assert result["semantic_query"] == "test query"


# =============================================================================
# TestQueryAnalyzerClose
# =============================================================================


class TestQueryAnalyzerClose:
    """Tests for QueryAnalyzer.close method."""

    async def test_close_calls_close_on_client(self):
        analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")
        analyzer.client = AsyncMock()

        await analyzer.close()

        analyzer.client.close.assert_called_once()


# =============================================================================
# Integration-style tests (still mocked, but testing flow)
# =============================================================================


class TestQueryAnalyzerFlow:
    """Test typical usage flow of QueryAnalyzer."""

    async def test_full_lifecycle(self):
        analyzer = QueryAnalyzer(
            api_key="test-key", base_url="http://localhost:8000", model="gpt-4o"
        )

        analyzer._instructor_client = AsyncMock()
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={"price": {"lt": 75000}}, semantic_query="квартира у моря"
            )
        )
        analyzer.client = AsyncMock()  # needed for close() assertion

        assert analyzer.api_key == "test-key"
        assert analyzer.base_url == "http://localhost:8000"
        assert analyzer.model == "gpt-4o"

        result = await analyzer.analyze("квартира до 75000 евро у моря")
        assert result["filters"] == {"price": {"lt": 75000}}
        assert result["semantic_query"] == "квартира у моря"

        await analyzer.close()
        analyzer.client.close.assert_called_once()

    async def test_multiple_queries(self):
        analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")
        analyzer._instructor_client = AsyncMock()

        responses = [
            QueryAnalysisResult(filters={"city": "Несебр"}, semantic_query="студия"),
            QueryAnalysisResult(filters={"rooms": 2}, semantic_query="квартира"),
            QueryAnalysisResult(filters={}, semantic_query="апартамент у моря"),
        ]
        analyzer._instructor_client.chat.completions.create = AsyncMock(side_effect=responses)

        result1 = await analyzer.analyze("студия в Несебре")
        result2 = await analyzer.analyze("двухкомнатная квартира")
        result3 = await analyzer.analyze("апартамент у моря")

        assert result1["filters"] == {"city": "Несебр"}
        assert result2["filters"] == {"rooms": 2}
        assert result3["filters"] == {}
        assert analyzer._instructor_client.chat.completions.create.call_count == 3

    async def test_error_recovery(self):
        analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")
        analyzer._instructor_client = AsyncMock()

        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=[
                openai.APIConnectionError(request=MagicMock()),
                QueryAnalysisResult(filters={"city": "Бургас"}, semantic_query="квартира"),
            ]
        )

        result1 = await analyzer.analyze("query1")
        assert result1["filters"] == {}
        assert result1["semantic_query"] == "query1"

        result2 = await analyzer.analyze("query2")
        assert result2["filters"] == {"city": "Бургас"}
        assert result2["semantic_query"] == "квартира"
