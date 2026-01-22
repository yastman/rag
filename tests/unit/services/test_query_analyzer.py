"""Unit tests for QueryAnalyzer service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_bot.services.query_analyzer import QueryAnalyzer


# =============================================================================
# TestQueryAnalyzerInit
# =============================================================================


class TestQueryAnalyzerInit:
    """Tests for QueryAnalyzer initialization."""

    def test_init_stores_api_key(self):
        """Test that api_key is stored correctly."""
        with patch("httpx.AsyncClient"):
            analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
            assert analyzer.api_key == "test-api-key"

    def test_init_stores_base_url(self):
        """Test that base_url is stored correctly."""
        with patch("httpx.AsyncClient"):
            analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
            assert analyzer.base_url == "http://localhost:8000"

    def test_init_default_model(self):
        """Test that default model is gpt-4o-mini."""
        with patch("httpx.AsyncClient"):
            analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
            assert analyzer.model == "gpt-4o-mini"

    def test_init_custom_model(self):
        """Test that custom model is stored correctly."""
        with patch("httpx.AsyncClient"):
            analyzer = QueryAnalyzer(
                api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o"
            )
            assert analyzer.model == "gpt-4o"

    def test_init_creates_httpx_client(self):
        """Test that httpx.AsyncClient is created on init."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")

            mock_client_class.assert_called_once_with(timeout=30.0)
            assert analyzer.client == mock_client

    def test_init_with_different_models(self):
        """Test initialization with various model names."""
        test_models = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "glm-4"]

        with patch("httpx.AsyncClient"):
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
    def mock_client(self):
        """Create a mock httpx.AsyncClient."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def analyzer_with_mock_client(self, mock_client):
        """Create QueryAnalyzer with mocked client."""
        with patch("httpx.AsyncClient", return_value=mock_client):
            return QueryAnalyzer(
                api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
            )

    async def test_analyze_returns_filters_and_semantic_query(
        self, analyzer_with_mock_client, mock_client
    ):
        """Test that analyze returns dict with filters and semantic_query."""
        response_content = json.dumps(
            {
                "filters": {"price": {"lt": 100000}, "city": "Несебр"},
                "semantic_query": "уютная квартира с хорошим ремонтом",
            }
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await analyzer_with_mock_client.analyze(
            "квартира до 100000 евро в Несебре с хорошим ремонтом"
        )

        assert "filters" in result
        assert "semantic_query" in result
        assert result["filters"] == {"price": {"lt": 100000}, "city": "Несебр"}
        assert result["semantic_query"] == "уютная квартира с хорошим ремонтом"

    async def test_analyze_calls_correct_endpoint(self, analyzer_with_mock_client, mock_client):
        """Test that analyze calls the /chat/completions endpoint."""
        response_content = json.dumps({"filters": {}, "semantic_query": "test query"})

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await analyzer_with_mock_client.analyze("test query")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:8000/chat/completions"

    async def test_analyze_uses_json_response_format(self, analyzer_with_mock_client, mock_client):
        """Test that analyze requests JSON response format."""
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await analyzer_with_mock_client.analyze("test query")

        call_args = mock_client.post.call_args
        request_body = call_args[1]["json"]
        assert request_body["response_format"] == {"type": "json_object"}

    async def test_analyze_uses_zero_temperature(self, analyzer_with_mock_client, mock_client):
        """Test that analyze uses temperature 0.0 for deterministic output."""
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await analyzer_with_mock_client.analyze("test query")

        call_args = mock_client.post.call_args
        request_body = call_args[1]["json"]
        assert request_body["temperature"] == 0.0

    async def test_analyze_sends_correct_headers(self, analyzer_with_mock_client, mock_client):
        """Test that analyze sends correct authorization headers."""
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await analyzer_with_mock_client.analyze("test query")

        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-api-key"
        assert headers["Content-Type"] == "application/json"

    async def test_analyze_sends_query_in_user_message(
        self, analyzer_with_mock_client, mock_client
    ):
        """Test that query is sent in user message."""
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        test_query = "квартира в Солнечном берегу до 50000 евро"
        await analyzer_with_mock_client.analyze(test_query)

        call_args = mock_client.post.call_args
        request_body = call_args[1]["json"]
        messages = request_body["messages"]

        # Find user message
        user_message = next(m for m in messages if m["role"] == "user")
        assert test_query in user_message["content"]

    async def test_analyze_uses_specified_model(self, analyzer_with_mock_client, mock_client):
        """Test that analyze uses the configured model."""
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await analyzer_with_mock_client.analyze("test query")

        call_args = mock_client.post.call_args
        request_body = call_args[1]["json"]
        assert request_body["model"] == "gpt-4o-mini"

    async def test_analyze_fallback_on_json_parse_error(
        self, analyzer_with_mock_client, mock_client
    ):
        """Test fallback when LLM returns invalid JSON."""
        # Return invalid JSON
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not valid json {"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        original_query = "квартира в Бургасе"
        result = await analyzer_with_mock_client.analyze(original_query)

        # Should return fallback: empty filters, original query
        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_api_error(self, analyzer_with_mock_client, mock_client):
        """Test fallback when API returns an error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "API Error", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client.post.return_value = mock_response

        original_query = "студия на первой линии"
        result = await analyzer_with_mock_client.analyze(original_query)

        # Should return fallback: empty filters, original query
        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_http_error(self, analyzer_with_mock_client, mock_client):
        """Test fallback when HTTP request fails (connection error)."""
        mock_client.post.side_effect = httpx.ConnectError("Connection failed")

        original_query = "двухкомнатная квартира"
        result = await analyzer_with_mock_client.analyze(original_query)

        # Should return fallback: empty filters, original query
        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_timeout_error(self, analyzer_with_mock_client, mock_client):
        """Test fallback when HTTP request times out."""
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")

        original_query = "квартира с видом на море"
        result = await analyzer_with_mock_client.analyze(original_query)

        # Should return fallback: empty filters, original query
        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_returns_empty_filters_when_none_found(
        self, analyzer_with_mock_client, mock_client
    ):
        """Test that empty filters are returned when no filters in query."""
        response_content = json.dumps({"filters": {}, "semantic_query": "красивая квартира у моря"})

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await analyzer_with_mock_client.analyze("красивая квартира у моря")

        assert result["filters"] == {}
        assert result["semantic_query"] == "красивая квартира у моря"

    async def test_analyze_handles_missing_semantic_query_in_response(
        self, analyzer_with_mock_client, mock_client
    ):
        """Test fallback to original query when semantic_query not in response."""
        response_content = json.dumps(
            {
                "filters": {"price": {"lt": 50000}}
                # Missing semantic_query
            }
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        original_query = "квартира до 50000 евро"
        result = await analyzer_with_mock_client.analyze(original_query)

        assert result["filters"] == {"price": {"lt": 50000}}
        assert result["semantic_query"] == original_query

    async def test_analyze_handles_missing_filters_in_response(
        self, analyzer_with_mock_client, mock_client
    ):
        """Test fallback to empty filters when filters not in response."""
        response_content = json.dumps(
            {
                "semantic_query": "уютная квартира"
                # Missing filters
            }
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await analyzer_with_mock_client.analyze("уютная квартира")

        assert result["filters"] == {}
        assert result["semantic_query"] == "уютная квартира"

    async def test_analyze_with_complex_filters(self, analyzer_with_mock_client, mock_client):
        """Test analyze with complex filter combinations."""
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await analyzer_with_mock_client.analyze(
            "2-комнатная квартира от 50000 до 100000 евро в Солнечном берегу"
        )

        assert result["filters"]["price"] == {"lt": 100000, "gt": 50000}
        assert result["filters"]["rooms"] == 2
        assert result["filters"]["city"] == "Солнечный берег"

    async def test_analyze_sets_max_tokens(self, analyzer_with_mock_client, mock_client):
        """Test that analyze sets max_tokens parameter."""
        response_content = json.dumps({"filters": {}, "semantic_query": "test"})

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await analyzer_with_mock_client.analyze("test query")

        call_args = mock_client.post.call_args
        request_body = call_args[1]["json"]
        assert request_body["max_tokens"] == 1000

    async def test_analyze_with_unicode_query(self, analyzer_with_mock_client, mock_client):
        """Test analyze with cyrillic/unicode text."""
        response_content = json.dumps(
            {"filters": {"city": "Варна"}, "semantic_query": "квартира с мебелью"}
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        cyrillic_query = "Ищу квартиру с мебелью в Варне"
        result = await analyzer_with_mock_client.analyze(cyrillic_query)

        assert result["filters"]["city"] == "Варна"
        assert result["semantic_query"] == "квартира с мебелью"


# =============================================================================
# TestQueryAnalyzerClose
# =============================================================================


class TestQueryAnalyzerClose:
    """Tests for QueryAnalyzer.close method."""

    async def test_close_calls_aclose_on_client(self):
        """Test that close() calls aclose() on the HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=mock_client):
            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")

        await analyzer.close()

        mock_client.aclose.assert_called_once()

    async def test_close_can_be_called_multiple_times(self):
        """Test that close() can be called multiple times without error."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=mock_client):
            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")

        # Call close multiple times
        await analyzer.close()
        await analyzer.close()

        # aclose should be called twice
        assert mock_client.aclose.call_count == 2


# =============================================================================
# Integration-style tests (still mocked, but testing flow)
# =============================================================================


class TestQueryAnalyzerFlow:
    """Test typical usage flow of QueryAnalyzer."""

    async def test_full_lifecycle(self):
        """Test create -> use -> close lifecycle."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        response_content = json.dumps(
            {"filters": {"price": {"lt": 75000}}, "semantic_query": "квартира у моря"}
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": response_content}}]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            # Create
            analyzer = QueryAnalyzer(
                api_key="test-key", base_url="http://localhost:8000", model="gpt-4o"
            )
            assert analyzer.api_key == "test-key"
            assert analyzer.base_url == "http://localhost:8000"
            assert analyzer.model == "gpt-4o"

            # Use
            result = await analyzer.analyze("квартира до 75000 евро у моря")
            assert result["filters"] == {"price": {"lt": 75000}}
            assert result["semantic_query"] == "квартира у моря"

            # Close
            await analyzer.close()
            mock_client.aclose.assert_called_once()

    async def test_multiple_queries(self):
        """Test making multiple queries with the same analyzer."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        # Different responses for different queries
        responses = [
            {"filters": {"city": "Несебр"}, "semantic_query": "студия"},
            {"filters": {"rooms": 2}, "semantic_query": "квартира"},
            {"filters": {}, "semantic_query": "апартамент у моря"},
        ]

        mock_responses = []
        for resp_data in responses:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": json.dumps(resp_data)}}]
            }
            mock_resp.raise_for_status = MagicMock()
            mock_responses.append(mock_resp)

        mock_client.post.side_effect = mock_responses

        with patch("httpx.AsyncClient", return_value=mock_client):
            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")

            result1 = await analyzer.analyze("студия в Несебре")
            result2 = await analyzer.analyze("двухкомнатная квартира")
            result3 = await analyzer.analyze("апартамент у моря")

            assert result1["filters"] == {"city": "Несебр"}
            assert result2["filters"] == {"rooms": 2}
            assert result3["filters"] == {}
            assert mock_client.post.call_count == 3

    async def test_error_recovery(self):
        """Test that analyzer continues working after error."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        # First call fails, second succeeds
        error_response = MagicMock()
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock(status_code=500)
        )

        success_response = MagicMock()
        success_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"filters": {"city": "Бургас"}, "semantic_query": "квартира"}
                        )
                    }
                }
            ]
        }
        success_response.raise_for_status = MagicMock()

        mock_client.post.side_effect = [error_response, success_response]

        with patch("httpx.AsyncClient", return_value=mock_client):
            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")

            # First call fails, should return fallback
            result1 = await analyzer.analyze("query1")
            assert result1["filters"] == {}
            assert result1["semantic_query"] == "query1"

            # Second call succeeds
            result2 = await analyzer.analyze("query2")
            assert result2["filters"] == {"city": "Бургас"}
            assert result2["semantic_query"] == "квартира"
