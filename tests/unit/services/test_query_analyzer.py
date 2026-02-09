"""Unit tests for QueryAnalyzer service (OpenAI SDK)."""

import json
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from telegram_bot.services.query_analyzer import QueryAnalyzer


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


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
        """Create QueryAnalyzer with mocked OpenAI client."""
        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
        )
        analyzer.client = AsyncMock()
        return analyzer

    async def test_analyze_returns_filters_and_semantic_query(self, analyzer):
        response_content = json.dumps(
            {
                "filters": {"price": {"lt": 100000}, "city": "Несебр"},
                "semantic_query": "уютная квартира с хорошим ремонтом",
            }
        )
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze("квартира до 100000 евро в Несебре с хорошим ремонтом")

        assert "filters" in result
        assert "semantic_query" in result
        assert result["filters"] == {"price": {"lt": 100000}, "city": "Несебр"}
        assert result["semantic_query"] == "уютная квартира с хорошим ремонтом"

    async def test_analyze_calls_openai_sdk(self, analyzer):
        response_content = json.dumps({"filters": {}, "semantic_query": "test query"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        await analyzer.analyze("test query")

        analyzer.client.chat.completions.create.assert_called_once()

    async def test_analyze_uses_json_response_format(self, analyzer):
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer.client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    async def test_analyze_uses_zero_temperature(self, analyzer):
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer.client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.0

    async def test_analyze_sends_query_in_user_message(self, analyzer):
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        test_query = "квартира в Солнечном берегу до 50000 евро"
        await analyzer.analyze(test_query)

        call_kwargs = analyzer.client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        user_message = next(m for m in messages if m["role"] == "user")
        assert test_query in user_message["content"]

    async def test_analyze_uses_specified_model(self, analyzer):
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer.client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

    async def test_analyze_fallback_on_json_parse_error(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("not valid json {")
        )

        original_query = "квартира в Бургасе"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_api_connection_error(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(
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
        analyzer.client.chat.completions.create = AsyncMock(
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
        analyzer.client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        original_query = "квартира с видом на море"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_returns_empty_filters_when_none_found(self, analyzer):
        response_content = json.dumps({"filters": {}, "semantic_query": "красивая квартира у моря"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze("красивая квартира у моря")

        assert result["filters"] == {}
        assert result["semantic_query"] == "красивая квартира у моря"

    async def test_analyze_handles_missing_semantic_query_in_response(self, analyzer):
        response_content = json.dumps({"filters": {"price": {"lt": 50000}}})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        original_query = "квартира до 50000 евро"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {"price": {"lt": 50000}}
        assert result["semantic_query"] == original_query

    async def test_analyze_handles_missing_filters_in_response(self, analyzer):
        response_content = json.dumps({"semantic_query": "уютная квартира"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze("уютная квартира")

        assert result["filters"] == {}
        assert result["semantic_query"] == "уютная квартира"

    async def test_analyze_with_complex_filters(self, analyzer):
        response_content = json.dumps(
            {
                "filters": {
                    "price": {"lt": 100000, "gt": 50000},
                    "rooms": 2,
                    "city": "Солнечный берег",
                    "area": {"gte": 50},
                    "distance_to_sea": {"lt": 500},
                },
                "semantic_query": "квартира с хорошим ремонтом",
            }
        )
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze(
            "2-комнатная квартира от 50000 до 100000 евро в Солнечном берегу"
        )

        assert result["filters"]["price"] == {"lt": 100000, "gt": 50000}
        assert result["filters"]["rooms"] == 2
        assert result["filters"]["city"] == "Солнечный берег"

    async def test_analyze_sets_max_tokens(self, analyzer):
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer.client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 1000

    async def test_analyze_with_unicode_query(self, analyzer):
        response_content = json.dumps(
            {"filters": {"city": "Варна"}, "semantic_query": "квартира с мебелью"}
        )
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze("Ищу квартиру с мебелью в Варне")

        assert result["filters"]["city"] == "Варна"
        assert result["semantic_query"] == "квартира с мебелью"

    async def test_analyze_handles_none_content(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(return_value=_mock_completion(None))

        result = await analyzer.analyze("test query")

        assert result["filters"] == {}
        assert result["semantic_query"] == "test query"

    async def test_analyze_handles_non_dict_json(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("[1, 2, 3]")
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

        response_content = json.dumps(
            {"filters": {"price": {"lt": 75000}}, "semantic_query": "квартира у моря"}
        )
        analyzer.client = AsyncMock()
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

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
        analyzer.client = AsyncMock()

        responses = [
            _mock_completion(
                json.dumps({"filters": {"city": "Несебр"}, "semantic_query": "студия"})
            ),
            _mock_completion(json.dumps({"filters": {"rooms": 2}, "semantic_query": "квартира"})),
            _mock_completion(json.dumps({"filters": {}, "semantic_query": "апартамент у моря"})),
        ]
        analyzer.client.chat.completions.create = AsyncMock(side_effect=responses)

        result1 = await analyzer.analyze("студия в Несебре")
        result2 = await analyzer.analyze("двухкомнатная квартира")
        result3 = await analyzer.analyze("апартамент у моря")

        assert result1["filters"] == {"city": "Несебр"}
        assert result2["filters"] == {"rooms": 2}
        assert result3["filters"] == {}
        assert analyzer.client.chat.completions.create.call_count == 3

    async def test_error_recovery(self):
        analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")
        analyzer.client = AsyncMock()

        success_response = _mock_completion(
            json.dumps({"filters": {"city": "Бургас"}, "semantic_query": "квартира"})
        )
        analyzer.client.chat.completions.create = AsyncMock(
            side_effect=[
                openai.APIConnectionError(request=MagicMock()),
                success_response,
            ]
        )

        result1 = await analyzer.analyze("query1")
        assert result1["filters"] == {}
        assert result1["semantic_query"] == "query1"

        result2 = await analyzer.analyze("query2")
        assert result2["filters"] == {"city": "Бургас"}
        assert result2["semantic_query"] == "квартира"
