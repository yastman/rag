"""Tests for VoyageEmbeddingService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip(
    "telegram_bot.services.voyage_embeddings",
    reason="telegram_bot.services.voyage_embeddings module removed",
)


class TestVoyageEmbeddingServiceUnit:
    """Unit tests for VoyageEmbeddingService."""

    def test_embed_query_returns_vector(self):
        """Test embed_query returns embedding vector."""
        from telegram_bot.services.voyage_embeddings import VoyageEmbeddingService

        with patch("telegram_bot.services.voyage_embeddings.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed_query_sync.return_value = [0.1] * 1024
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageEmbeddingService()
            result = service.embed_query_sync("test query")

            assert len(result) == 1024
            mock_client.embed_query_sync.assert_called_once_with(
                "test query", model="voyage-3-large"
            )

    def test_embed_documents_returns_vectors(self):
        """Test embed_documents returns list of vectors."""
        from telegram_bot.services.voyage_embeddings import VoyageEmbeddingService

        with patch("telegram_bot.services.voyage_embeddings.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed_sync.return_value = [[0.1] * 1024, [0.2] * 1024]
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageEmbeddingService()
            result = service.embed_documents_sync(["doc1", "doc2"])

            assert len(result) == 2
            mock_client.embed_sync.assert_called_once()

    def test_uses_custom_model(self):
        """Test service uses custom model when specified."""
        from telegram_bot.services.voyage_embeddings import VoyageEmbeddingService

        with patch("telegram_bot.services.voyage_embeddings.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed_query_sync.return_value = [0.1] * 512
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageEmbeddingService(model="voyage-3-lite")
            service.embed_query_sync("test")

            mock_client.embed_query_sync.assert_called_with("test", model="voyage-3-lite")

    async def test_async_embed_query(self):
        """Test async embed_query method."""
        from telegram_bot.services.voyage_embeddings import VoyageEmbeddingService

        with patch("telegram_bot.services.voyage_embeddings.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed_query = AsyncMock(return_value=[0.1] * 1024)
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageEmbeddingService()
            result = await service.embed_query("test query")

            assert len(result) == 1024

    def test_batch_embed_splits_large_batches(self):
        """Test batch embedding splits large batches."""
        from telegram_bot.services.voyage_embeddings import VoyageEmbeddingService

        with patch("telegram_bot.services.voyage_embeddings.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            # Return different vectors for each batch
            mock_client.embed_sync.side_effect = [
                [[0.1] * 1024] * 128,  # First batch
                [[0.2] * 1024] * 50,  # Second batch
            ]
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageEmbeddingService()
            texts = ["text"] * 178  # More than batch size of 128
            result = service.embed_documents_sync(texts)

            assert len(result) == 178
            assert mock_client.embed_sync.call_count == 2
