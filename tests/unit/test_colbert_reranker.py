"""Tests for ColBERT reranker service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestColbertRerankerService:
    """Tests for ColbertRerankerService."""

    @pytest.fixture
    def service(self):
        from telegram_bot.services.colbert_reranker import ColbertRerankerService

        return ColbertRerankerService(base_url="http://localhost:8000")
    async def test_rerank_returns_sorted_results(self, service):
        """Test rerank returns results with index and score."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 1, "score": 0.95},
                {"index": 0, "score": 0.72},
            ],
            "processing_time": 0.1,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            results = await service.rerank(
                query="test",
                documents=["doc1", "doc2"],
                top_k=2,
            )

            assert len(results) == 2
            assert results[0]["index"] == 1
            assert results[0]["score"] == 0.95
            # Verify contract matches bot expectations
            assert "index" in results[0]
            assert "score" in results[0]
    async def test_rerank_empty_documents(self, service):
        """Test rerank with empty documents returns empty list."""
        results = await service.rerank(query="test", documents=[], top_k=5)
        assert results == []
    async def test_rerank_calls_correct_endpoint(self, service):
        """Test rerank calls /rerank endpoint with correct payload."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"index": 0, "score": 0.8}],
            "processing_time": 0.05,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await service.rerank(
                query="квартира",
                documents=["doc1"],
                top_k=3,
            )

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/rerank" in call_args[0][0]
            payload = call_args[1]["json"]
            assert payload["query"] == "квартира"
            assert payload["documents"] == ["doc1"]
            assert payload["top_k"] == 3
    async def test_close_client(self, service):
        """Test close method closes the HTTP client."""
        with patch.object(service._client, "aclose", new_callable=AsyncMock) as mock_close:
            await service.close()
            mock_close.assert_called_once()
