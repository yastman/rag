"""Tests for unified VoyageService."""

from unittest.mock import MagicMock, patch

import pytest


class TestVoyageServiceUnit:
    """Unit tests for VoyageService (no API calls)."""

    def test_init_creates_client_with_api_key(self):
        """Test initialization creates voyageai.Client."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            service = VoyageService(api_key="test-key")

            mock_client_class.assert_called_once_with(api_key="test-key")
            assert service._model_docs == "voyage-4-large"
            assert service._model_queries == "voyage-4-lite"
            assert service._model_rerank == "rerank-2.5"

    def test_init_with_custom_models(self):
        """Test initialization with custom model names."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(
                api_key="test-key",
                model_docs="voyage-3-large",
                model_queries="voyage-3-lite",
                model_rerank="rerank-2",
            )

            assert service._model_docs == "voyage-3-large"
            assert service._model_queries == "voyage-3-lite"
            assert service._model_rerank == "rerank-2"

    async def test_embed_documents_batches_large_input(self):
        """Test embed_documents splits into batches of 128."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            # Return different number of embeddings for each batch
            mock_client.embed.side_effect = [
                MagicMock(embeddings=[[0.1] * 1024] * 128),  # First batch: 128
                MagicMock(embeddings=[[0.1] * 1024] * 72),  # Second batch: 72
            ]
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")

            # 200 texts should result in 2 batches (128 + 72)
            texts = [f"text_{i}" for i in range(200)]
            result = await service.embed_documents(texts)

            # Result should have 200 embeddings
            assert len(result) == 200
            # Should be called twice (2 batches)
            assert mock_client.embed.call_count == 2
            # First batch: 128 texts
            first_call = mock_client.embed.call_args_list[0]
            assert len(first_call[1]["texts"]) == 128
            # Second batch: 72 texts
            second_call = mock_client.embed.call_args_list[1]
            assert len(second_call[1]["texts"]) == 72

    async def test_embed_documents_uses_document_model(self):
        """Test embed_documents uses model_docs."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key", model_docs="voyage-4-large")
            await service.embed_documents(["test"])

            call_kwargs = mock_client.embed.call_args[1]
            assert call_kwargs["model"] == "voyage-4-large"
            assert call_kwargs["input_type"] == "document"

    async def test_embed_query_uses_query_model(self):
        """Test embed_query uses model_queries (asymmetric retrieval)."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key", model_queries="voyage-4-lite")
            await service.embed_query("test query")

            call_kwargs = mock_client.embed.call_args[1]
            assert call_kwargs["model"] == "voyage-4-lite"
            assert call_kwargs["input_type"] == "query"

    async def test_embed_documents_empty_list(self):
        """Test embed_documents with empty list returns empty."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(api_key="test-key")
            result = await service.embed_documents([])

            assert result == []

    async def test_rerank_returns_formatted_results(self):
        """Test rerank returns list of dicts with index and score."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.index = 1
            mock_result.relevance_score = 0.95
            mock_result.document = "doc1"
            mock_client.rerank.return_value = MagicMock(results=[mock_result])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")
            result = await service.rerank("query", ["doc0", "doc1"])

            assert len(result) == 1
            assert result[0]["index"] == 1
            assert result[0]["relevance_score"] == 0.95
            assert result[0]["document"] == "doc1"

    async def test_rerank_empty_documents(self):
        """Test rerank with empty documents returns empty list."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(api_key="test-key")
            result = await service.rerank("query", [])

            assert result == []

    async def test_rerank_uses_rerank_model(self):
        """Test rerank uses model_rerank."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.rerank.return_value = MagicMock(results=[])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key", model_rerank="rerank-2.5")
            await service.rerank("query", ["doc"])

            call_kwargs = mock_client.rerank.call_args[1]
            assert call_kwargs["model"] == "rerank-2.5"


class TestVoyageServiceBackwardCompatibility:
    """Tests to ensure VoyageService can replace existing services."""

    async def test_can_replace_voyage_embedding_service(self):
        """Test VoyageService provides same interface as VoyageEmbeddingService."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            # VoyageService should have same methods as VoyageEmbeddingService
            service = VoyageService(api_key="test-key")

            # embed_query (async) - primary method used in bot.py
            result = await service.embed_query("test")
            assert len(result) == 1024

            # embed_documents (async) - used for indexing
            result = await service.embed_documents(["test"])
            assert len(result) == 1

    async def test_can_replace_voyage_reranker_service(self):
        """Test VoyageService provides same interface as VoyageRerankerService."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.index = 0
            mock_result.relevance_score = 0.9
            mock_result.document = "doc"
            mock_client.rerank.return_value = MagicMock(results=[mock_result])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")

            # rerank (async) - primary method used in bot.py
            result = await service.rerank("query", ["doc"])
            assert len(result) == 1
            assert "relevance_score" in result[0]

    def test_sync_methods_work(self):
        """Test sync wrappers for non-async code."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")

            # embed_query_sync
            result = service.embed_query_sync("test")
            assert len(result) == 1024

            # embed_documents_sync
            result = service.embed_documents_sync(["test"])
            assert len(result) == 1


class TestVoyageServiceMatryoshka:
    """Tests for Matryoshka embedding support."""

    def test_matryoshka_dims_constant(self):
        """Test supported dimensions are defined."""
        from telegram_bot.services.voyage import VoyageService

        assert VoyageService.MATRYOSHKA_DIMS == (2048, 1024, 512, 256)
        assert VoyageService.DEFAULT_DIM == 1024

    async def test_embed_documents_matryoshka_passes_output_dimension(self):
        """Test embed_documents_matryoshka passes output_dimension to API."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 512])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")
            await service.embed_documents_matryoshka(["test"], output_dimension=512)

            call_kwargs = mock_client.embed.call_args[1]
            assert call_kwargs["output_dimension"] == 512

    async def test_embed_query_matryoshka_passes_output_dimension(self):
        """Test embed_query_matryoshka passes output_dimension to API."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 256])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")
            await service.embed_query_matryoshka("test query", output_dimension=256)

            call_kwargs = mock_client.embed.call_args[1]
            assert call_kwargs["output_dimension"] == 256

    async def test_embed_documents_matryoshka_invalid_dimension_raises(self):
        """Test embed_documents_matryoshka raises for invalid dimensions."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(api_key="test-key")

            with pytest.raises(ValueError) as exc_info:
                await service.embed_documents_matryoshka(["test"], output_dimension=999)

            assert "Invalid output_dimension 999" in str(exc_info.value)
            assert "Supported: (2048, 1024, 512, 256)" in str(exc_info.value)

    async def test_embed_query_matryoshka_invalid_dimension_raises(self):
        """Test embed_query_matryoshka raises for invalid dimensions."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(api_key="test-key")

            with pytest.raises(ValueError) as exc_info:
                await service.embed_query_matryoshka("test", output_dimension=100)

            assert "Invalid output_dimension 100" in str(exc_info.value)

    async def test_embed_documents_matryoshka_empty_list(self):
        """Test embed_documents_matryoshka with empty list returns empty."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(api_key="test-key")
            result = await service.embed_documents_matryoshka([])

            assert result == []

    async def test_embed_documents_matryoshka_batches_correctly(self):
        """Test embed_documents_matryoshka batches like embed_documents."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.side_effect = [
                MagicMock(embeddings=[[0.1] * 512] * 128),
                MagicMock(embeddings=[[0.1] * 512] * 22),
            ]
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")
            texts = [f"text_{i}" for i in range(150)]
            result = await service.embed_documents_matryoshka(texts, output_dimension=512)

            assert len(result) == 150
            assert mock_client.embed.call_count == 2

    def test_matryoshka_sync_methods_work(self):
        """Test sync wrappers for Matryoshka methods."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 512])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")

            # embed_documents_matryoshka_sync
            result = service.embed_documents_matryoshka_sync(["test"], output_dimension=512)
            assert len(result) == 1

            # embed_query_matryoshka_sync
            result = service.embed_query_matryoshka_sync("test", output_dimension=512)
            assert len(result) == 512
