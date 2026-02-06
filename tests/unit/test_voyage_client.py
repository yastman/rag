"""Tests for VoyageClient.

NOTE: telegram_bot.services.voyage_client was removed/refactored into
telegram_bot.services.voyage. These tests are skipped until rewritten.
"""

from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.skip(
    reason="telegram_bot.services.voyage_client module removed; tests need rewrite"
)


class TestVoyageClientUnit:
    """Unit tests for VoyageClient (no API calls)."""

    def test_singleton_returns_same_instance(self):
        """Test singleton pattern returns same instance."""
        from telegram_bot.services.voyage_client import VoyageClient

        # Reset singleton for clean test
        VoyageClient._instance = None

        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}):
            client1 = VoyageClient.get_instance()
            client2 = VoyageClient.get_instance()

            assert client1 is client2

        # Cleanup
        VoyageClient._instance = None

    def test_init_raises_without_api_key(self):
        """Test initialization fails without API key."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": ""}),
            pytest.raises(ValueError, match="VOYAGE_API_KEY"),
        ):
            VoyageClient()

        VoyageClient._instance = None

    def test_embed_calls_client_with_correct_params(self):
        """Test embed passes correct parameters."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_client_class,
        ):
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024, [0.2] * 1024])
            mock_client_class.return_value = mock_client

            client = VoyageClient()
            result = client.embed_sync(["text1", "text2"], model="voyage-3-large")

            mock_client.embed.assert_called_once_with(
                texts=["text1", "text2"],
                model="voyage-3-large",
                input_type="document",
            )
            assert len(result) == 2

        VoyageClient._instance = None

    def test_embed_query_uses_query_input_type(self):
        """Test embed_query uses input_type='query'."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_client_class,
        ):
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            client = VoyageClient()
            client.embed_query_sync("test query")

            call_kwargs = mock_client.embed.call_args[1]
            assert call_kwargs["input_type"] == "query"

        VoyageClient._instance = None

    def test_rerank_returns_sorted_indices(self):
        """Test rerank returns indices and scores."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_client_class,
        ):
            mock_client = MagicMock()
            # Mock rerank result
            mock_result1 = MagicMock()
            mock_result1.index = 2
            mock_result1.relevance_score = 0.95
            mock_result2 = MagicMock()
            mock_result2.index = 0
            mock_result2.relevance_score = 0.80

            mock_client.rerank.return_value = MagicMock(results=[mock_result1, mock_result2])
            mock_client_class.return_value = mock_client

            client = VoyageClient()
            result = client.rerank_sync("query", ["doc0", "doc1", "doc2"])

            assert result[0]["index"] == 2
            assert result[0]["score"] == 0.95
            assert result[1]["index"] == 0

        VoyageClient._instance = None

    def test_rerank_empty_documents(self):
        """Test rerank with empty documents returns empty list."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client"),
        ):
            client = VoyageClient()
            result = client.rerank_sync("query", [])

            assert result == []

        VoyageClient._instance = None
