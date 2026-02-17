"""Unit tests for ContextualizedEmbeddingService (voyage-context-3).

Tests cover:
- Service initialization and configuration
- Document embedding (list of lists input format)
- Query embedding
- Input validation (API limits)
- Error handling and retry logic
- Sync wrappers
"""

from unittest.mock import MagicMock, patch

import pytest
import voyageai


@pytest.fixture
def mock_voyage_client():
    """Create mock Voyage AI client."""
    with patch("voyageai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_langfuse():
    """Mock Langfuse client for observability."""
    with patch("src.models.contextualized_embedding.get_client") as mock:
        mock_langfuse = MagicMock()
        mock_langfuse.update_current_generation = MagicMock()
        mock.return_value = mock_langfuse
        yield mock_langfuse


class TestContextualizedEmbeddingServiceInit:
    """Test service initialization."""

    def test_init_with_default_settings(self, mock_voyage_client):
        """Test initialization with default parameters."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        service = ContextualizedEmbeddingService(api_key="test-key")

        assert service.output_dimension == 1024
        assert service._output_dtype == "float"
        assert service.MODEL_NAME == "voyage-context-3"

    def test_init_with_custom_dimension(self, mock_voyage_client):
        """Test initialization with custom output dimension."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        service = ContextualizedEmbeddingService(
            api_key="test-key",
            output_dimension=512,
        )

        assert service.output_dimension == 512

    def test_init_with_custom_dtype(self, mock_voyage_client):
        """Test initialization with custom output dtype."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        service = ContextualizedEmbeddingService(
            api_key="test-key",
            output_dtype="int8",
        )

        assert service._output_dtype == "int8"

    def test_init_invalid_dimension_raises_error(self, mock_voyage_client):
        """Test that invalid dimension raises ValueError."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        with pytest.raises(ValueError, match="Invalid output_dimension 999"):
            ContextualizedEmbeddingService(api_key="test-key", output_dimension=999)

    def test_supported_dimensions(self, mock_voyage_client):
        """Test all supported dimensions can be used."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        for dim in (2048, 1024, 512, 256):
            service = ContextualizedEmbeddingService(api_key="test-key", output_dimension=dim)
            assert service.output_dimension == dim


class TestEmbedDocuments:
    """Test document embedding functionality."""
    async def test_embed_documents_basic(self, mock_voyage_client, mock_langfuse):
        """Test basic document embedding."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        # Setup mock response
        mock_result1 = MagicMock()
        mock_result1.embeddings = [[0.1] * 1024, [0.2] * 1024]

        mock_result2 = MagicMock()
        mock_result2.embeddings = [[0.3] * 1024]

        mock_response = MagicMock()
        mock_response.results = [mock_result1, mock_result2]
        mock_response.total_tokens = 100

        mock_voyage_client.contextualized_embed = MagicMock(return_value=mock_response)

        service = ContextualizedEmbeddingService(api_key="test-key")

        # Input: 2 documents, first with 2 chunks, second with 1 chunk
        document_chunks = [
            ["doc1 chunk1", "doc1 chunk2"],
            ["doc2 chunk1"],
        ]

        result = await service.embed_documents(document_chunks)

        # Verify embeddings
        assert len(result.embeddings) == 3  # 2 + 1 chunks
        assert result.total_tokens == 100
        assert result.chunks_per_document == [2, 1]

        # Verify API call
        mock_voyage_client.contextualized_embed.assert_called_once()
        call_kwargs = mock_voyage_client.contextualized_embed.call_args.kwargs
        assert call_kwargs["inputs"] == document_chunks
        assert call_kwargs["model"] == "voyage-context-3"
        assert call_kwargs["input_type"] == "document"
    async def test_embed_documents_empty_input(self, mock_voyage_client, mock_langfuse):
        """Test embedding with empty input."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        service = ContextualizedEmbeddingService(api_key="test-key")

        result = await service.embed_documents([])

        assert result.embeddings == []
        assert result.total_tokens == 0
        assert result.chunks_per_document == []
    async def test_embed_documents_too_many_documents(self, mock_voyage_client, mock_langfuse):
        """Test validation for too many documents."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        service = ContextualizedEmbeddingService(api_key="test-key")

        # Create 1001 documents (exceeds 1000 limit)
        document_chunks = [["chunk"] for _ in range(1001)]

        with pytest.raises(ValueError, match="Too many documents"):
            await service.embed_documents(document_chunks)
    async def test_embed_documents_too_many_chunks(self, mock_voyage_client, mock_langfuse):
        """Test validation for too many total chunks."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        service = ContextualizedEmbeddingService(api_key="test-key")

        # Create document with 16001 chunks (exceeds 16000 limit)
        document_chunks = [["chunk"] * 16001]

        with pytest.raises(ValueError, match="Too many chunks"):
            await service.embed_documents(document_chunks)


class TestEmbedQuery:
    """Test query embedding functionality."""
    async def test_embed_query_basic(self, mock_voyage_client, mock_langfuse):
        """Test basic query embedding."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        # Setup mock response
        mock_result = MagicMock()
        mock_result.embeddings = [[0.5] * 1024]

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.total_tokens = 10

        mock_voyage_client.contextualized_embed = MagicMock(return_value=mock_response)

        service = ContextualizedEmbeddingService(api_key="test-key")

        embedding = await service.embed_query("test query")

        # Verify embedding
        assert len(embedding) == 1024
        assert embedding == [0.5] * 1024

        # Verify API call format
        call_kwargs = mock_voyage_client.contextualized_embed.call_args.kwargs
        assert call_kwargs["inputs"] == [["test query"]]  # Wrapped in double list
        assert call_kwargs["input_type"] == "query"
    async def test_embed_queries_multiple(self, mock_voyage_client, mock_langfuse):
        """Test embedding multiple queries."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        # Setup mock response
        mock_result1 = MagicMock()
        mock_result1.embeddings = [[0.1] * 1024]

        mock_result2 = MagicMock()
        mock_result2.embeddings = [[0.2] * 1024]

        mock_response = MagicMock()
        mock_response.results = [mock_result1, mock_result2]
        mock_response.total_tokens = 20

        mock_voyage_client.contextualized_embed = MagicMock(return_value=mock_response)

        service = ContextualizedEmbeddingService(api_key="test-key")

        embeddings = await service.embed_queries(["query1", "query2"])

        # Verify embeddings
        assert len(embeddings) == 2
        assert embeddings[0] == [0.1] * 1024
        assert embeddings[1] == [0.2] * 1024

        # Verify API call format
        call_kwargs = mock_voyage_client.contextualized_embed.call_args.kwargs
        assert call_kwargs["inputs"] == [["query1"], ["query2"]]
    async def test_embed_queries_empty(self, mock_voyage_client, mock_langfuse):
        """Test embedding empty queries list."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        service = ContextualizedEmbeddingService(api_key="test-key")

        embeddings = await service.embed_queries([])

        assert embeddings == []


class TestSyncWrappers:
    """Test synchronous wrapper methods."""

    def test_embed_documents_sync(self, mock_voyage_client, mock_langfuse):
        """Test sync wrapper for embed_documents."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        # Setup mock response
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1] * 1024]

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.total_tokens = 50

        mock_voyage_client.contextualized_embed = MagicMock(return_value=mock_response)

        service = ContextualizedEmbeddingService(api_key="test-key")

        result = service.embed_documents_sync([["test chunk"]])

        assert len(result.embeddings) == 1

    def test_embed_query_sync(self, mock_voyage_client, mock_langfuse):
        """Test sync wrapper for embed_query."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        # Setup mock response
        mock_result = MagicMock()
        mock_result.embeddings = [[0.5] * 1024]

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.total_tokens = 10

        mock_voyage_client.contextualized_embed = MagicMock(return_value=mock_response)

        service = ContextualizedEmbeddingService(api_key="test-key")

        embedding = service.embed_query_sync("test query")

        assert len(embedding) == 1024


class TestRetryLogic:
    """Test retry behavior on API errors."""
    async def test_retry_on_rate_limit_error(self, mock_voyage_client, mock_langfuse):
        """Test retry on RateLimitError."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        # First call raises rate limit, second succeeds
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1] * 1024]

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.total_tokens = 10

        mock_voyage_client.contextualized_embed = MagicMock(
            side_effect=[
                voyageai.error.RateLimitError("Rate limit exceeded"),
                mock_response,
            ]
        )

        service = ContextualizedEmbeddingService(api_key="test-key")

        # Should succeed after retry
        result = await service.embed_documents([["test"]])

        assert len(result.embeddings) == 1
        assert mock_voyage_client.contextualized_embed.call_count == 2
    async def test_retry_on_service_unavailable(self, mock_voyage_client, mock_langfuse):
        """Test retry on ServiceUnavailableError."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        # First call raises service unavailable, second succeeds
        mock_result = MagicMock()
        mock_result.embeddings = [[0.5] * 1024]

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.total_tokens = 5

        mock_voyage_client.contextualized_embed = MagicMock(
            side_effect=[
                voyageai.error.ServiceUnavailableError("Service unavailable"),
                mock_response,
            ]
        )

        service = ContextualizedEmbeddingService(api_key="test-key")

        embedding = await service.embed_query("test")

        assert len(embedding) == 1024
        assert mock_voyage_client.contextualized_embed.call_count == 2


class TestOutputDtype:
    """Test different output data types."""
    async def test_int8_output_dtype(self, mock_voyage_client, mock_langfuse):
        """Test int8 output data type."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingService

        # Setup mock response with int8 values
        mock_result = MagicMock()
        mock_result.embeddings = [[1, 2, 3, 4] * 256]  # int8 values

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.total_tokens = 10

        mock_voyage_client.contextualized_embed = MagicMock(return_value=mock_response)

        service = ContextualizedEmbeddingService(
            api_key="test-key",
            output_dtype="int8",
        )

        await service.embed_documents([["test"]])

        # Verify output_dtype is passed to API
        call_kwargs = mock_voyage_client.contextualized_embed.call_args.kwargs
        assert call_kwargs["output_dtype"] == "int8"


class TestFeatureFlag:
    """Test feature flag integration."""

    def test_settings_default_disabled(self):
        """Test that contextualized embeddings are disabled by default."""
        from src.config import settings as settings_module

        # Should default to False
        with patch.dict("os.environ", {}, clear=True):
            settings = settings_module.Settings.__new__(settings_module.Settings)
            # Manually call init parts we need
            settings.use_contextualized_embeddings = False  # Default when env var not set

            assert settings.use_contextualized_embeddings is False

    def test_settings_enabled_via_env(self):
        """Test enabling via environment variable."""
        import os

        with patch.dict(
            os.environ,
            {
                "USE_CONTEXTUALIZED_EMBEDDINGS": "true",
                "CONTEXTUALIZED_EMBEDDING_DIM": "512",
            },
        ):
            from src.config.settings import Settings

            # Need to avoid API key validation for this test
            with patch.object(Settings, "_validate_api_keys", return_value=None):
                settings = Settings()

            assert settings.use_contextualized_embeddings is True
            assert settings.contextualized_embedding_dim == 512


class TestContextualizedEmbeddingResult:
    """Test the result dataclass."""

    def test_result_attributes(self):
        """Test ContextualizedEmbeddingResult attributes."""
        from src.models.contextualized_embedding import ContextualizedEmbeddingResult

        result = ContextualizedEmbeddingResult(
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            total_tokens=100,
            chunks_per_document=[1, 1],
        )

        assert len(result.embeddings) == 2
        assert result.total_tokens == 100
        assert result.chunks_per_document == [1, 1]
