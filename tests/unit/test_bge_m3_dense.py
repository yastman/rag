"""Tests for BGE-M3 dense embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBgeM3DenseService:
    """Tests for BgeM3DenseService."""

    @pytest.fixture
    def service(self):
        from telegram_bot.services.bge_m3_dense import BgeM3DenseService

        return BgeM3DenseService(base_url="http://localhost:8000")

    async def test_embed_query_returns_vector(self, service):
        """Test embed_query returns 1024-dim vector."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "dense_vecs": [[0.1] * 1024],
            "processing_time": 0.05,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await service.embed_query("test query")

            assert len(result) == 1024
            assert isinstance(result, list)
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/encode/dense" in call_args[0][0]

    async def test_embed_documents_batch(self, service):
        """Test embed_documents handles batching."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "dense_vecs": [[0.1] * 1024, [0.2] * 1024],
            "processing_time": 0.1,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await service.embed_documents(["doc1", "doc2"])

            assert len(result) == 2
            assert all(len(v) == 1024 for v in result)

    async def test_embed_documents_empty_list(self, service):
        """Test embed_documents with empty list returns empty list."""
        result = await service.embed_documents([])
        assert result == []

    async def test_embed_documents_large_batch(self, service):
        """Test embed_documents handles large batches correctly."""
        # Create 40 documents (more than BATCH_SIZE of 32)
        docs = [f"doc{i}" for i in range(40)]

        mock_response1 = MagicMock()
        mock_response1.json.return_value = {
            "dense_vecs": [[0.1] * 1024] * 32,
            "processing_time": 0.1,
        }
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.json.return_value = {
            "dense_vecs": [[0.2] * 1024] * 8,
            "processing_time": 0.05,
        }
        mock_response2.raise_for_status = MagicMock()

        with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [mock_response1, mock_response2]

            result = await service.embed_documents(docs)

            assert len(result) == 40
            assert mock_post.call_count == 2

    async def test_close_client(self, service):
        """Test close method closes the HTTP client."""
        with patch.object(service._client, "aclose", new_callable=AsyncMock) as mock_close:
            await service.close()
            mock_close.assert_called_once()
