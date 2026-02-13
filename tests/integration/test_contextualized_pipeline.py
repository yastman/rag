"""Integration tests for Voyage Contextualized Embeddings pipeline.

Tests the ContextualizedEmbeddingService and its integration with the RAG pipeline.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestContextualizedEmbeddingService:
    """Tests for ContextualizedEmbeddingService initialization and configuration."""

    def test_service_initialization(self):
        """Test service initializes with correct parameters."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client"):
            service = ContextualizedEmbeddingService(
                api_key="test-key",
                output_dimension=1024,
                output_dtype="float",
            )

            assert service.MODEL_NAME == "voyage-context-3"
            assert service.output_dimension == 1024

    def test_service_rejects_invalid_dimension(self):
        """Test service rejects unsupported dimensions."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with pytest.raises(ValueError, match="Invalid output_dimension"):
            ContextualizedEmbeddingService(
                api_key="test-key",
                output_dimension=768,  # Not supported
            )

    def test_supported_dimensions(self):
        """Test all supported Matryoshka dimensions."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        supported = (2048, 1024, 512, 256)

        for dim in supported:
            with patch("voyageai.Client"):
                service = ContextualizedEmbeddingService(
                    api_key="test-key",
                    output_dimension=dim,
                )
                assert service.output_dimension == dim


class TestContextualizedDocumentEmbedding:
    """Tests for document embedding functionality."""
    async def test_embed_single_document(self):
        """Test embedding a single document with multiple chunks."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client") as mock_client_class:
            # Setup mock
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
            mock_response = MagicMock()
            mock_response.results = [mock_result]
            mock_response.total_tokens = 150
            mock_client.contextualized_embed.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = ContextualizedEmbeddingService(api_key="test-key")

            # Embed document with 3 chunks
            doc_chunks = [["chunk 1", "chunk 2", "chunk 3"]]
            result = await service.embed_documents(doc_chunks)

            assert len(result.embeddings) == 3
            assert result.total_tokens == 150
            assert result.chunks_per_document == [3]

            # Verify API was called correctly
            mock_client.contextualized_embed.assert_called_once()
            call_kwargs = mock_client.contextualized_embed.call_args[1]
            assert call_kwargs["inputs"] == doc_chunks
            assert call_kwargs["model"] == "voyage-context-3"
            assert call_kwargs["input_type"] == "document"
    async def test_embed_multiple_documents(self):
        """Test embedding multiple documents in one call."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()

            # Two documents: 2 chunks and 3 chunks
            mock_result1 = MagicMock()
            mock_result1.embeddings = [[0.1] * 1024, [0.2] * 1024]
            mock_result2 = MagicMock()
            mock_result2.embeddings = [[0.3] * 1024, [0.4] * 1024, [0.5] * 1024]

            mock_response = MagicMock()
            mock_response.results = [mock_result1, mock_result2]
            mock_response.total_tokens = 250
            mock_client.contextualized_embed.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = ContextualizedEmbeddingService(api_key="test-key")

            doc_chunks = [
                ["doc1 chunk1", "doc1 chunk2"],
                ["doc2 chunk1", "doc2 chunk2", "doc2 chunk3"],
            ]
            result = await service.embed_documents(doc_chunks)

            assert len(result.embeddings) == 5  # 2 + 3
            assert result.chunks_per_document == [2, 3]
    async def test_embed_empty_list(self):
        """Test embedding empty document list."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            service = ContextualizedEmbeddingService(api_key="test-key")

            result = await service.embed_documents([])

            assert result.embeddings == []
            assert result.total_tokens == 0
            assert result.chunks_per_document == []
            mock_client.contextualized_embed.assert_not_called()


class TestContextualizedQueryEmbedding:
    """Tests for query embedding functionality."""
    async def test_embed_single_query(self):
        """Test embedding a single query."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.5] * 1024]
            mock_response = MagicMock()
            mock_response.results = [mock_result]
            mock_response.total_tokens = 10
            mock_client.contextualized_embed.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = ContextualizedEmbeddingService(api_key="test-key")

            embedding = await service.embed_query("test query")

            assert len(embedding) == 1024
            assert embedding[0] == 0.5

            # Verify API called with query wrapped in nested list
            call_kwargs = mock_client.contextualized_embed.call_args[1]
            assert call_kwargs["inputs"] == [["test query"]]
            assert call_kwargs["input_type"] == "query"
    async def test_embed_multiple_queries(self):
        """Test embedding multiple queries."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_result1 = MagicMock()
            mock_result1.embeddings = [[0.1] * 1024]
            mock_result2 = MagicMock()
            mock_result2.embeddings = [[0.2] * 1024]
            mock_response = MagicMock()
            mock_response.results = [mock_result1, mock_result2]
            mock_response.total_tokens = 20
            mock_client.contextualized_embed.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = ContextualizedEmbeddingService(api_key="test-key")

            embeddings = await service.embed_queries(["query 1", "query 2"])

            assert len(embeddings) == 2
            assert embeddings[0][0] == 0.1
            assert embeddings[1][0] == 0.2
    async def test_embed_empty_queries(self):
        """Test embedding empty query list."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            service = ContextualizedEmbeddingService(api_key="test-key")

            embeddings = await service.embed_queries([])

            assert embeddings == []


class TestContextualizedValidation:
    """Tests for input validation."""
    async def test_too_many_documents(self):
        """Test rejection when too many documents."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client"):
            service = ContextualizedEmbeddingService(api_key="test-key")

            # Create 1001 documents (exceeds 1000 limit)
            doc_chunks = [["chunk"] for _ in range(1001)]

            with pytest.raises(ValueError, match="Too many documents"):
                await service.embed_documents(doc_chunks)
    async def test_too_many_chunks(self):
        """Test rejection when too many total chunks."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client"):
            service = ContextualizedEmbeddingService(api_key="test-key")

            # Create documents with 16001 total chunks (exceeds 16000 limit)
            # 100 documents with 161 chunks each = 16100 chunks
            doc_chunks = [["chunk"] * 161 for _ in range(100)]

            with pytest.raises(ValueError, match="Too many chunks"):
                await service.embed_documents(doc_chunks)


class TestContextualizedSyncWrappers:
    """Tests for synchronous wrapper methods."""

    def test_embed_documents_sync(self):
        """Test sync wrapper for document embedding."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.1] * 1024]
            mock_response = MagicMock()
            mock_response.results = [mock_result]
            mock_response.total_tokens = 10
            mock_client.contextualized_embed.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = ContextualizedEmbeddingService(api_key="test-key")

            result = service.embed_documents_sync([["chunk"]])

            assert len(result.embeddings) == 1

    def test_embed_query_sync(self):
        """Test sync wrapper for query embedding."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.5] * 1024]
            mock_response = MagicMock()
            mock_response.results = [mock_result]
            mock_response.total_tokens = 5
            mock_client.contextualized_embed.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = ContextualizedEmbeddingService(api_key="test-key")

            embedding = service.embed_query_sync("test")

            assert len(embedding) == 1024


class TestContextualizedOutputDtypes:
    """Tests for different output data types."""

    def test_float_dtype(self):
        """Test float output dtype."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client"):
            service = ContextualizedEmbeddingService(
                api_key="test-key",
                output_dtype="float",
            )
            assert service._output_dtype == "float"

    def test_int8_dtype(self):
        """Test int8 output dtype."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client"):
            service = ContextualizedEmbeddingService(
                api_key="test-key",
                output_dtype="int8",
            )
            assert service._output_dtype == "int8"

    def test_binary_dtype(self):
        """Test binary output dtype."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with patch("voyageai.Client"):
            service = ContextualizedEmbeddingService(
                api_key="test-key",
                output_dtype="binary",
            )
            assert service._output_dtype == "binary"


class TestContextualizedSettingsIntegration:
    """Tests for settings integration."""

    def test_settings_has_contextualized_flag(self):
        """Test settings includes contextualized embeddings flag."""
        with patch.dict(
            "os.environ",
            {
                "VOYAGE_API_KEY": "test",
                "USE_CONTEXTUALIZED_EMBEDDINGS": "true",
                "CONTEXTUALIZED_EMBEDDING_DIM": "2048",
            },
        ):
            from importlib import reload

            from src.config import settings

            reload(settings)

            # Create fresh settings instance
            s = settings.Settings()

            assert s.use_contextualized_embeddings is True
            assert s.contextualized_embedding_dim == 2048

    def test_settings_defaults(self):
        """Test default values for contextualized settings."""
        with patch.dict(
            "os.environ",
            {"VOYAGE_API_KEY": "test"},
            clear=True,
        ):
            from importlib import reload

            from src.config import settings

            reload(settings)

            s = settings.Settings()

            assert s.use_contextualized_embeddings is False
            assert s.contextualized_embedding_dim == 1024

    def test_to_dict_includes_contextualized(self):
        """Test to_dict includes contextualized settings."""
        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test"}):
            from src.config.settings import Settings

            s = Settings()
            d = s.to_dict()

            assert "use_contextualized_embeddings" in d
            assert "contextualized_embedding_dim" in d


class TestContextualizedResultDataclass:
    """Tests for ContextualizedEmbeddingResult dataclass."""

    def test_result_dataclass_creation(self):
        """Test creating result dataclass."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingResult

        result = ContextualizedEmbeddingResult(
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            total_tokens=100,
            chunks_per_document=[2],
        )

        assert len(result.embeddings) == 2
        assert result.total_tokens == 100
        assert result.chunks_per_document == [2]

    def test_result_multiple_documents(self):
        """Test result with multiple documents."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingResult

        result = ContextualizedEmbeddingResult(
            embeddings=[[0.1], [0.2], [0.3], [0.4], [0.5]],
            total_tokens=500,
            chunks_per_document=[2, 3],
        )

        assert len(result.embeddings) == 5
        assert sum(result.chunks_per_document) == 5


class TestContextualizedAPILimits:
    """Tests for API limit constants."""

    def test_api_limits(self):
        """Test API limit constants are correct."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        assert ContextualizedEmbeddingService.MAX_DOCUMENTS_PER_REQUEST == 1000
        assert ContextualizedEmbeddingService.MAX_CHUNKS_PER_REQUEST == 16000
        assert ContextualizedEmbeddingService.MAX_TOKENS_PER_DOCUMENT == 32000
        assert ContextualizedEmbeddingService.MAX_TOTAL_TOKENS == 120000

    def test_supported_dims(self):
        """Test supported dimensions constant."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        assert ContextualizedEmbeddingService.SUPPORTED_DIMS == (2048, 1024, 512, 256)
        assert ContextualizedEmbeddingService.DEFAULT_DIM == 1024
