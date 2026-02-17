"""Tests for VoyageRerankerService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip(
    "telegram_bot.services.voyage_reranker",
    reason="telegram_bot.services.voyage_reranker module removed",
)


class TestVoyageRerankerServiceUnit:
    """Unit tests for VoyageRerankerService."""

    def test_rerank_returns_sorted_results(self):
        """Test rerank returns results sorted by relevance."""
        from telegram_bot.services.voyage_reranker import VoyageRerankerService

        with patch("telegram_bot.services.voyage_reranker.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.rerank_sync.return_value = [
                {"index": 2, "score": 0.95},
                {"index": 0, "score": 0.80},
                {"index": 1, "score": 0.60},
            ]
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageRerankerService()
            docs = [
                {"text": "doc0", "metadata": {"id": 0}},
                {"text": "doc1", "metadata": {"id": 1}},
                {"text": "doc2", "metadata": {"id": 2}},
            ]

            results = service.rerank_sync("query", docs, top_k=3)

            # Should be sorted by score (doc2 first)
            assert results[0]["metadata"]["id"] == 2
            assert results[0]["rerank_score"] == 0.95

    def test_rerank_preserves_metadata(self):
        """Test rerank preserves original document metadata."""
        from telegram_bot.services.voyage_reranker import VoyageRerankerService

        with patch("telegram_bot.services.voyage_reranker.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.rerank_sync.return_value = [
                {"index": 0, "score": 0.9},
            ]
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageRerankerService()
            docs = [{"text": "doc", "metadata": {"city": "Бургас", "price": 50000}, "score": 0.8}]

            results = service.rerank_sync("query", docs, top_k=1)

            assert results[0]["metadata"]["city"] == "Бургас"
            assert results[0]["metadata"]["price"] == 50000
            assert results[0]["original_score"] == 0.8

    def test_rerank_empty_docs_returns_empty(self):
        """Test rerank with empty docs returns empty list."""
        from telegram_bot.services.voyage_reranker import VoyageRerankerService

        with patch("telegram_bot.services.voyage_reranker.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageRerankerService()
            results = service.rerank_sync("query", [], top_k=5)

            assert results == []

    def test_uses_custom_model(self):
        """Test service uses custom model."""
        from telegram_bot.services.voyage_reranker import VoyageRerankerService

        with patch("telegram_bot.services.voyage_reranker.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.rerank_sync.return_value = []
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageRerankerService(model="rerank-2-lite")
            service.rerank_sync("query", [{"text": "doc"}], top_k=1)

            mock_client.rerank_sync.assert_called_with(
                "query", ["doc"], model="rerank-2-lite", top_k=1
            )

    async def test_async_rerank(self):
        """Test async rerank method."""
        from telegram_bot.services.voyage_reranker import VoyageRerankerService

        with patch("telegram_bot.services.voyage_reranker.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.rerank = AsyncMock(
                return_value=[
                    {"index": 0, "score": 0.9},
                ]
            )
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageRerankerService()
            docs = [{"text": "doc", "metadata": {}}]

            results = await service.rerank("query", docs, top_k=1)

            assert len(results) == 1

    def test_extracts_text_from_different_keys(self):
        """Test extracts text from 'text' or 'page_content' keys."""
        from telegram_bot.services.voyage_reranker import VoyageRerankerService

        with patch("telegram_bot.services.voyage_reranker.VoyageClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.rerank_sync.return_value = [
                {"index": 0, "score": 0.9},
                {"index": 1, "score": 0.8},
            ]
            mock_client_class.get_instance.return_value = mock_client

            service = VoyageRerankerService()
            docs = [
                {"text": "from text key", "metadata": {}},
                {"page_content": "from page_content key", "metadata": {}},
            ]

            service.rerank_sync("query", docs, top_k=2)

            call_args = mock_client.rerank_sync.call_args[0]
            assert "from text key" in call_args[1]
            assert "from page_content key" in call_args[1]
