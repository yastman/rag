"""Unit tests for telegram_bot/services/query_analyzer.py (OpenAI SDK)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.query_analyzer import QueryAnalyzer


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


class TestQueryAnalyzerInit:
    """Test QueryAnalyzer initialization."""

    def test_init_defaults(self):
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )
        assert analyzer.api_key == "test-key"
        assert analyzer.base_url == "https://api.example.com/v1"
        assert analyzer.model == "gpt-4o-mini"

    def test_init_custom_model(self):
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4",
        )
        assert analyzer.model == "gpt-4"

    def test_init_creates_openai_client(self):
        from openai import AsyncOpenAI

        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )
        assert analyzer.client is not None
        assert isinstance(analyzer.client, AsyncOpenAI)


class TestQueryAnalyzerAnalyze:
    """Test analyze method."""

    @pytest.fixture
    def analyzer(self):
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )
        analyzer.client = AsyncMock()
        return analyzer
    async def test_analyze_extracts_price_filter(self, analyzer):
        response_content = json.dumps(
            {"filters": {"price": {"lt": 100000}}, "semantic_query": "квартира недорого"}
        )
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze("квартира дешевле 100000 евро")

        assert result["filters"]["price"] == {"lt": 100000}
        assert result["semantic_query"] == "квартира недорого"
    async def test_analyze_extracts_city_filter(self, analyzer):
        response_content = json.dumps({"filters": {"city": "Несебр"}, "semantic_query": "квартиры"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze("квартиры в Несебр")

        assert result["filters"]["city"] == "Несебр"
    async def test_analyze_extracts_multiple_filters(self, analyzer):
        response_content = json.dumps(
            {
                "filters": {
                    "price": {"lt": 80000},
                    "rooms": 2,
                    "city": "Солнечный берег",
                },
                "semantic_query": "квартира с хорошим ремонтом",
            }
        )
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze("2-комнатная в Солнечный берег дешевле 80000")

        assert result["filters"]["price"] == {"lt": 80000}
        assert result["filters"]["rooms"] == 2
        assert result["filters"]["city"] == "Солнечный берег"
    async def test_analyze_no_filters(self, analyzer):
        response_content = json.dumps(
            {"filters": {}, "semantic_query": "красивая квартира с видом"}
        )
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        result = await analyzer.analyze("красивая квартира с видом на море")

        assert result["filters"] == {}
        assert result["semantic_query"] == "красивая квартира с видом"
    async def test_analyze_json_parse_error_fallback(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("invalid json {")
        )

        result = await analyzer.analyze("test query")

        assert result["filters"] == {}
        assert result["semantic_query"] == "test query"
    async def test_analyze_api_error_fallback(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        result = await analyzer.analyze("test query")

        assert result["filters"] == {}
        assert result["semantic_query"] == "test query"
    async def test_analyze_uses_correct_api_format(self, analyzer):
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_content)
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer.client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}
        assert call_kwargs["temperature"] == 0.0


class TestQueryAnalyzerClose:
    """Test close method."""
    async def test_close_closes_client(self):
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )
        analyzer.client = AsyncMock()

        await analyzer.close()

        analyzer.client.close.assert_called_once()
