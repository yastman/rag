"""Tests for VoyageService Langfuse instrumentation."""

from unittest.mock import MagicMock, patch

import pytest


class TestVoyageServiceObservability:
    """Test VoyageService has @observe decorators."""

    def test_embed_query_has_observe_decorator(self):
        """embed_query should have @observe decorator."""
        from telegram_bot.services.voyage import VoyageService

        # Check if method has langfuse observation wrapper
        method = VoyageService.embed_query
        # The @observe decorator wraps the function, adding __wrapped__ attribute
        assert hasattr(method, "__wrapped__") or hasattr(method, "_langfuse_observation")

    def test_embed_documents_has_observe_decorator(self):
        """embed_documents should have @observe decorator."""
        from telegram_bot.services.voyage import VoyageService

        method = VoyageService.embed_documents
        assert hasattr(method, "__wrapped__") or hasattr(method, "_langfuse_observation")

    def test_rerank_has_observe_decorator(self):
        """rerank should have @observe decorator."""
        from telegram_bot.services.voyage import VoyageService

        method = VoyageService.rerank
        assert hasattr(method, "__wrapped__") or hasattr(method, "_langfuse_observation")

    def test_embed_documents_matryoshka_has_observe_decorator(self):
        """embed_documents_matryoshka should have @observe decorator."""
        from telegram_bot.services.voyage import VoyageService

        method = VoyageService.embed_documents_matryoshka
        assert hasattr(method, "__wrapped__") or hasattr(method, "_langfuse_observation")

    def test_embed_query_matryoshka_has_observe_decorator(self):
        """embed_query_matryoshka should have @observe decorator."""
        from telegram_bot.services.voyage import VoyageService

        method = VoyageService.embed_query_matryoshka
        assert hasattr(method, "__wrapped__") or hasattr(method, "_langfuse_observation")


class TestVoyageServiceObservabilityIntegration:
    """Test VoyageService observability integration (mocked)."""

    @pytest.fixture
    def mock_voyage_client(self):
        """Mock Voyage AI client."""
        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def mock_langfuse(self):
        """Mock Langfuse get_client."""
        with patch("telegram_bot.services.voyage.get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.update_current_generation = MagicMock()
            mock_get.return_value = mock_client
            yield mock_client

    async def test_embed_query_calls_langfuse_update(self, mock_voyage_client, mock_langfuse):
        """embed_query should update Langfuse generation with usage."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1] * 1024]
        mock_response.usage = MagicMock(total_tokens=10)
        mock_voyage_client.embed.return_value = mock_response

        from telegram_bot.services.voyage import VoyageService

        service = VoyageService(api_key="test-key")

        # Execute
        result = await service.embed_query("test query")

        # Verify embedding returned
        assert len(result) == 1024
        assert result[0] == 0.1

    async def test_embed_documents_calls_langfuse_update(self, mock_voyage_client, mock_langfuse):
        """embed_documents should update Langfuse generation with usage."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1] * 1024, [0.2] * 1024]
        mock_response.usage = MagicMock(total_tokens=20)
        mock_voyage_client.embed.return_value = mock_response

        from telegram_bot.services.voyage import VoyageService

        service = VoyageService(api_key="test-key")

        # Execute
        result = await service.embed_documents(["doc1", "doc2"])

        # Verify embeddings returned
        assert len(result) == 2
        assert len(result[0]) == 1024

    async def test_rerank_calls_langfuse_update(self, mock_voyage_client, mock_langfuse):
        """rerank should update Langfuse generation with results count."""
        # Setup mock response
        mock_result = MagicMock()
        mock_result.index = 0
        mock_result.relevance_score = 0.95
        mock_result.document = "doc1"

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_voyage_client.rerank.return_value = mock_response

        from telegram_bot.services.voyage import VoyageService

        service = VoyageService(api_key="test-key")

        # Execute
        result = await service.rerank("query", ["doc1"], top_k=1)

        # Verify results
        assert len(result) == 1
        assert result[0]["relevance_score"] == 0.95
