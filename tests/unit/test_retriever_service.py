"""Unit tests for telegram_bot/services/retriever.py."""

from unittest.mock import MagicMock, patch

import pytest

from telegram_bot.services.retriever import RetrieverService


class TestRetrieverServiceInit:
    """Test RetrieverService initialization."""

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_init_with_api_key(self, mock_qdrant):
        """Test initialization with API key."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="test-key",
            collection_name="test_collection",
        )

        assert service.url == "http://localhost:6333"
        assert service.api_key == "test-key"
        assert service.collection_name == "test_collection"
        mock_qdrant.assert_called_once_with(
            url="http://localhost:6333",
            api_key="test-key",
            timeout=5.0,
        )

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_init_without_api_key(self, mock_qdrant):
        """Test initialization without API key."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test_collection",
        )

        mock_qdrant.assert_called_once_with(
            url="http://localhost:6333",
            timeout=5.0,
        )

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_init_healthy_connection(self, mock_qdrant):
        """Test that healthy connection sets _is_healthy True."""
        mock_client = MagicMock()
        mock_client.get_collections.return_value = []
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        assert service._is_healthy is True
        assert service.client is not None

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_init_connection_failure(self, mock_qdrant):
        """Test that connection failure sets _is_healthy False."""
        mock_qdrant.side_effect = Exception("Connection refused")

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        assert service._is_healthy is False
        assert service.client is None


class TestRetrieverServiceSearch:
    """Test RetrieverService search method."""

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_search_returns_empty_when_unhealthy(self, mock_qdrant):
        """Test that search returns empty list when unhealthy."""
        mock_qdrant.side_effect = Exception("Connection refused")

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        result = service.search([0.1, 0.2, 0.3])

        assert result == []

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_search_returns_formatted_results(self, mock_qdrant):
        """Test that search returns properly formatted results."""
        mock_point = MagicMock()
        mock_point.payload = {
            "page_content": "Sample text content",
            "metadata": {"city": "Varna", "price": 50000},
        }
        mock_point.score = 0.95

        mock_results = MagicMock()
        mock_results.points = [mock_point]

        mock_client = MagicMock()
        mock_client.query_points.return_value = mock_results
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        results = service.search([0.1, 0.2, 0.3])

        assert len(results) == 1
        assert results[0]["text"] == "Sample text content"
        assert results[0]["metadata"]["city"] == "Varna"
        assert results[0]["score"] == 0.95

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_search_with_filters(self, mock_qdrant):
        """Test search with filters."""
        mock_results = MagicMock()
        mock_results.points = []

        mock_client = MagicMock()
        mock_client.query_points.return_value = mock_results
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        filters = {"city": "Varna", "rooms": 2}
        service.search([0.1, 0.2, 0.3], filters=filters)

        # Verify query_points was called
        mock_client.query_points.assert_called_once()

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_search_handles_exception(self, mock_qdrant):
        """Test that search handles exceptions gracefully."""
        mock_client = MagicMock()
        mock_client.query_points.side_effect = Exception("Search failed")
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        results = service.search([0.1, 0.2, 0.3])

        assert results == []
        assert service._is_healthy is False


class TestBuildFilter:
    """Test filter building methods."""

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_build_base_filter_returns_none(self, mock_qdrant):
        """Test that _build_base_filter returns None."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        result = service._build_base_filter()

        assert result is None

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_build_filter_empty_returns_none(self, mock_qdrant):
        """Test that _build_filter with empty dict returns None."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        result = service._build_filter({})

        assert result is None

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_build_filter_string_match(self, mock_qdrant):
        """Test filter building with string match."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        result = service._build_filter({"city": "Varna"})

        assert result is not None
        assert len(result.must) == 1

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_build_filter_int_match(self, mock_qdrant):
        """Test filter building with integer match."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        result = service._build_filter({"rooms": 2})

        assert result is not None
        assert len(result.must) == 1

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_build_filter_range_lt(self, mock_qdrant):
        """Test filter building with less-than range."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        result = service._build_filter({"price": {"lt": 100000}})

        assert result is not None
        assert len(result.must) == 1

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_build_filter_range_gte(self, mock_qdrant):
        """Test filter building with greater-than-or-equal range."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        result = service._build_filter({"area": {"gte": 50}})

        assert result is not None
        assert len(result.must) == 1

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_build_filter_combined(self, mock_qdrant):
        """Test filter building with multiple conditions."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        filters = {
            "city": "Nesebar",
            "rooms": 2,
            "price": {"lt": 100000},
        }
        result = service._build_filter(filters)

        assert result is not None
        assert len(result.must) == 3

    @patch("telegram_bot.services.retriever.QdrantClient")
    def test_build_filter_range_multiple_operators(self, mock_qdrant):
        """Test filter building with multiple range operators."""
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        service = RetrieverService(
            url="http://localhost:6333",
            api_key="",
            collection_name="test",
        )

        result = service._build_filter({"price": {"gte": 50000, "lte": 100000}})

        assert result is not None
        assert len(result.must) == 1
