"""Unit tests for telegram_bot/services/query_analyzer.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_bot.services.query_analyzer import QueryAnalyzer


class TestQueryAnalyzerInit:
    """Test QueryAnalyzer initialization."""

    def test_init_defaults(self):
        """Test initialization with default model."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        assert analyzer.api_key == "test-key"
        assert analyzer.base_url == "https://api.example.com/v1"
        assert analyzer.model == "gpt-4o-mini"

    def test_init_custom_model(self):
        """Test initialization with custom model."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4",
        )

        assert analyzer.model == "gpt-4"

    def test_init_creates_client(self):
        """Test that HTTP client is created."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        assert analyzer.client is not None
        assert isinstance(analyzer.client, httpx.AsyncClient)


class TestQueryAnalyzerAnalyze:
    """Test analyze method."""

    @pytest.mark.asyncio
    async def test_analyze_extracts_price_filter(self):
        """Test that price filter is extracted correctly."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "filters": {"price": {"lt": 100000}},
                                "semantic_query": "квартира недорого",
                            }
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(analyzer.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await analyzer.analyze("квартира дешевле 100000 евро")

            assert result["filters"]["price"] == {"lt": 100000}
            assert result["semantic_query"] == "квартира недорого"

    @pytest.mark.asyncio
    async def test_analyze_extracts_city_filter(self):
        """Test that city filter is extracted correctly."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "filters": {"city": "Несебр"},
                                "semantic_query": "квартиры",
                            }
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(analyzer.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await analyzer.analyze("квартиры в Несебр")

            assert result["filters"]["city"] == "Несебр"

    @pytest.mark.asyncio
    async def test_analyze_extracts_multiple_filters(self):
        """Test that multiple filters are extracted correctly."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "filters": {
                                    "price": {"lt": 80000},
                                    "rooms": 2,
                                    "city": "Солнечный берег",
                                },
                                "semantic_query": "квартира с хорошим ремонтом",
                            }
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(analyzer.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await analyzer.analyze("2-комнатная в Солнечный берег дешевле 80000")

            assert result["filters"]["price"] == {"lt": 80000}
            assert result["filters"]["rooms"] == 2
            assert result["filters"]["city"] == "Солнечный берег"

    @pytest.mark.asyncio
    async def test_analyze_no_filters(self):
        """Test handling query with no extractable filters."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "filters": {},
                                "semantic_query": "красивая квартира с видом",
                            }
                        )
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(analyzer.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await analyzer.analyze("красивая квартира с видом на море")

            assert result["filters"] == {}
            assert result["semantic_query"] == "красивая квартира с видом"

    @pytest.mark.asyncio
    async def test_analyze_json_parse_error_fallback(self):
        """Test fallback when JSON parsing fails."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "invalid json {"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch.object(analyzer.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await analyzer.analyze("test query")

            # Should return fallback
            assert result["filters"] == {}
            assert result["semantic_query"] == "test query"

    @pytest.mark.asyncio
    async def test_analyze_api_error_fallback(self):
        """Test fallback when API call fails."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        with patch.object(analyzer.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("API Error")

            result = await analyzer.analyze("test query")

            # Should return fallback
            assert result["filters"] == {}
            assert result["semantic_query"] == "test query"

    @pytest.mark.asyncio
    async def test_analyze_uses_correct_api_format(self):
        """Test that correct API format is used."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": json.dumps({"filters": {}, "semantic_query": "test"})}}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(analyzer.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await analyzer.analyze("test query")

            # Verify call arguments
            call_args = mock_post.call_args
            assert call_args[0][0] == "https://api.example.com/v1/chat/completions"
            json_data = call_args[1]["json"]
            assert json_data["response_format"] == {"type": "json_object"}
            assert json_data["temperature"] == 0.0


class TestQueryAnalyzerClose:
    """Test close method."""

    @pytest.mark.asyncio
    async def test_close_closes_client(self):
        """Test that close() closes the HTTP client."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="https://api.example.com/v1",
        )

        with patch.object(analyzer.client, "aclose", new_callable=AsyncMock) as mock_close:
            await analyzer.close()

            mock_close.assert_called_once()
