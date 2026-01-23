"""Unit tests for telegram_bot/services/voyage.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.voyage import VoyageService


class TestVoyageServiceInit:
    """Test VoyageService initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default models."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(api_key="test-key")

            assert service._model_docs == "voyage-4-large"
            assert service._model_queries == "voyage-4-lite"
            assert service._model_rerank == "rerank-2.5"

    def test_init_with_custom_models(self):
        """Test initialization with custom models."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(
                api_key="test-key",
                model_docs="voyage-3-large",
                model_queries="voyage-3-lite",
                model_rerank="rerank-2",
            )

            assert service._model_docs == "voyage-3-large"
            assert service._model_queries == "voyage-3-lite"
            assert service._model_rerank == "rerank-2"

    def test_init_creates_client(self):
        """Test that client is created with API key."""
        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_client:
            VoyageService(api_key="test-api-key")

            mock_client.assert_called_once_with(api_key="test-api-key")

    def test_batch_size_constant(self):
        """Test that BATCH_SIZE is correctly set."""
        assert VoyageService.BATCH_SIZE == 128

    def test_matryoshka_dims_constant(self):
        """Test that MATRYOSHKA_DIMS contains valid dimensions."""
        assert VoyageService.MATRYOSHKA_DIMS == (2048, 1024, 512, 256)


class TestEmbedDocuments:
    """Test document embedding."""

    @pytest.mark.asyncio
    async def test_embed_documents_empty_list(self):
        """Test embedding empty list returns empty list."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(api_key="test-key")

            result = await service.embed_documents([])

            assert result == []

    @pytest.mark.asyncio
    async def test_embed_documents_single_batch(self):
        """Test embedding documents within single batch."""
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.embed.return_value = mock_response
            mock_client.return_value = mock_client_instance

            service = VoyageService(api_key="test-key")

            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = mock_response

                result = await service.embed_documents(["doc1", "doc2"])

                assert len(result) == 2
                assert result[0] == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_embed_documents_batching(self):
        """Test that documents are batched correctly."""
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1] * 1024] * 128

        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.embed.return_value = mock_response
            mock_client.return_value = mock_client_instance

            service = VoyageService(api_key="test-key")

            # Create 200 documents (should require 2 batches)
            docs = [f"doc{i}" for i in range(200)]

            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = mock_response

                result = await service.embed_documents(docs)

                # Should have called to_thread twice (128 + 72 docs)
                assert mock_to_thread.call_count == 2


class TestEmbedQuery:
    """Test query embedding."""

    @pytest.mark.asyncio
    async def test_embed_query_returns_single_embedding(self):
        """Test that embed_query returns a single embedding."""
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1, 0.2, 0.3, 0.4]]

        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.embed.return_value = mock_response
            mock_client.return_value = mock_client_instance

            service = VoyageService(api_key="test-key")

            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = mock_response

                result = await service.embed_query("test query")

                assert result == [0.1, 0.2, 0.3, 0.4]

    @pytest.mark.asyncio
    async def test_embed_query_uses_query_model(self):
        """Test that embed_query uses the query model."""
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1]]

        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.embed.return_value = mock_response
            mock_client.return_value = mock_client_instance

            service = VoyageService(api_key="test-key")

            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = mock_response

                await service.embed_query("test query")

                # Check that to_thread was called with query model
                call_args = mock_to_thread.call_args
                assert call_args is not None


class TestRerank:
    """Test reranking."""

    @pytest.mark.asyncio
    async def test_rerank_empty_documents(self):
        """Test reranking with empty documents returns empty list."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(api_key="test-key")

            result = await service.rerank("query", [])

            assert result == []

    @pytest.mark.asyncio
    async def test_rerank_returns_formatted_results(self):
        """Test that rerank returns properly formatted results."""
        mock_result1 = MagicMock()
        mock_result1.index = 0
        mock_result1.relevance_score = 0.95
        mock_result1.document = "doc1"

        mock_result2 = MagicMock()
        mock_result2.index = 1
        mock_result2.relevance_score = 0.85
        mock_result2.document = "doc2"

        mock_response = MagicMock()
        mock_response.results = [mock_result1, mock_result2]

        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.rerank.return_value = mock_response
            mock_client.return_value = mock_client_instance

            service = VoyageService(api_key="test-key")

            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = mock_response

                result = await service.rerank("query", ["doc1", "doc2"])

                assert len(result) == 2
                assert result[0]["index"] == 0
                assert result[0]["relevance_score"] == 0.95
                assert result[0]["document"] == "doc1"


class TestMatryoshkaEmbeddings:
    """Test Matryoshka embeddings."""

    @pytest.mark.asyncio
    async def test_matryoshka_invalid_dimension(self):
        """Test that invalid dimension raises ValueError."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(api_key="test-key")

            with pytest.raises(ValueError, match="Invalid output_dimension"):
                await service.embed_documents_matryoshka(["doc"], output_dimension=100)

    @pytest.mark.asyncio
    async def test_matryoshka_valid_dimensions(self):
        """Test that valid dimensions are accepted."""
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1] * 512]

        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.embed.return_value = mock_response
            mock_client.return_value = mock_client_instance

            service = VoyageService(api_key="test-key")

            for dim in (2048, 1024, 512, 256):
                with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                    mock_to_thread.return_value = mock_response

                    # Should not raise
                    await service.embed_documents_matryoshka(["doc"], output_dimension=dim)

    @pytest.mark.asyncio
    async def test_matryoshka_empty_list(self):
        """Test Matryoshka embedding with empty list."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(api_key="test-key")

            result = await service.embed_documents_matryoshka([])

            assert result == []

    @pytest.mark.asyncio
    async def test_matryoshka_query_invalid_dimension(self):
        """Test that invalid dimension raises ValueError for query."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(api_key="test-key")

            with pytest.raises(ValueError, match="Invalid output_dimension"):
                await service.embed_query_matryoshka("query", output_dimension=100)


class TestSyncWrappers:
    """Test synchronous wrapper methods."""

    def test_embed_documents_sync_calls_async(self):
        """Test that sync wrapper calls async method."""
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1, 0.2]]

        with patch("telegram_bot.services.voyage.voyageai.Client") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.embed.return_value = mock_response
            mock_client.return_value = mock_client_instance

            service = VoyageService(api_key="test-key")

            with patch.object(service, "embed_documents", new_callable=AsyncMock) as mock_async:
                mock_async.return_value = [[0.1, 0.2]]

                with patch("asyncio.run") as mock_run:
                    mock_run.return_value = [[0.1, 0.2]]

                    result = service.embed_documents_sync(["doc"])

                    assert mock_run.called

    def test_embed_query_sync_calls_async(self):
        """Test that sync query wrapper calls async method."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(api_key="test-key")

            with patch("asyncio.run") as mock_run:
                mock_run.return_value = [0.1, 0.2]

                result = service.embed_query_sync("query")

                assert mock_run.called

    def test_rerank_sync_calls_async(self):
        """Test that sync rerank wrapper calls async method."""
        with patch("telegram_bot.services.voyage.voyageai.Client"):
            service = VoyageService(api_key="test-key")

            with patch("asyncio.run") as mock_run:
                mock_run.return_value = [{"index": 0, "relevance_score": 0.9}]

                result = service.rerank_sync("query", ["doc"])

                assert mock_run.called
