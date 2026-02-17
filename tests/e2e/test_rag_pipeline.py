"""E2E tests for RAG pipeline workflow.

These tests verify the complete RAG pipeline from document ingestion to search results.
They use mocks to avoid requiring external services but test the full flow.
"""

from unittest.mock import MagicMock, patch

from src.core.pipeline import RAGPipeline, RAGResult


class TestRAGPipelineInit:
    """Test RAGPipeline initialization."""

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.ClaudeContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    def test_pipeline_init_creates_components(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test that pipeline initializes all components."""
        _pipeline = RAGPipeline()

        mock_embedding.assert_called_once_with("BAAI/bge-m3")
        mock_search_engine.assert_called_once()
        mock_contextualizer.assert_called_once()
        mock_indexer.assert_called_once()
        mock_chunker.assert_called_once()
        mock_parser.assert_called_once_with(use_cache=True)

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.ClaudeContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    def test_pipeline_init_with_custom_settings(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test pipeline with custom settings."""
        from src.config import Settings

        custom_settings = MagicMock(spec=Settings)
        custom_settings.api_provider = MagicMock()
        custom_settings.api_provider.value = "claude"

        pipeline = RAGPipeline(settings=custom_settings)

        assert pipeline.settings == custom_settings


class TestRAGPipelineContextualizer:
    """Test contextualizer creation based on API provider."""

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    @patch("src.core.pipeline.ClaudeContextualizer")
    def test_creates_claude_contextualizer(
        self,
        mock_claude,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test Claude contextualizer is created for Claude provider."""
        from src.config import APIProvider

        mock_settings = MagicMock()
        mock_settings.api_provider = APIProvider.CLAUDE

        _pipeline = RAGPipeline(settings=mock_settings)

        mock_claude.assert_called_once()

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    @patch("src.core.pipeline.OpenAIContextualizer")
    def test_creates_openai_contextualizer(
        self,
        mock_openai,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test OpenAI contextualizer is created for OpenAI provider."""
        from src.config import APIProvider

        mock_settings = MagicMock()
        mock_settings.api_provider = APIProvider.OPENAI

        _pipeline = RAGPipeline(settings=mock_settings)

        mock_openai.assert_called_once()

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    @patch("src.core.pipeline.GroqContextualizer")
    def test_creates_groq_contextualizer(
        self,
        mock_groq,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test Groq contextualizer is created for Groq provider."""
        from src.config import APIProvider

        mock_settings = MagicMock()
        mock_settings.api_provider = APIProvider.GROQ

        _pipeline = RAGPipeline(settings=mock_settings)

        mock_groq.assert_called_once()


class TestRAGPipelineSearch:
    """Test RAG pipeline search functionality."""

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.ClaudeContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    async def test_search_returns_rag_result(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test that search returns RAGResult."""
        # Setup mock search results
        mock_result = MagicMock()
        mock_result.article_number = "121"
        mock_result.text = "Test article text"
        mock_result.score = 0.95
        mock_result.metadata = {"source": "test"}

        mock_engine = MagicMock()
        mock_engine.search.return_value = [mock_result]
        mock_engine.get_name.return_value = "mock_engine"
        mock_search_engine.return_value = mock_engine

        mock_settings = MagicMock()
        mock_settings.top_k = 10
        mock_settings.score_threshold = 0.5
        mock_settings.enable_query_expansion = False

        pipeline = RAGPipeline(settings=mock_settings)
        result = await pipeline.search("test query")

        assert isinstance(result, RAGResult)
        assert result.query == "test query"
        assert len(result.results) == 1
        assert result.results[0]["article_number"] == "121"
        assert result.execution_time > 0

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.ClaudeContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    async def test_search_with_custom_top_k(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test search with custom top_k parameter."""
        mock_engine = MagicMock()
        mock_engine.search.return_value = []
        mock_engine.get_name.return_value = "mock_engine"
        mock_search_engine.return_value = mock_engine

        mock_settings = MagicMock()
        mock_settings.top_k = 10
        mock_settings.score_threshold = 0.5
        mock_settings.enable_query_expansion = False

        pipeline = RAGPipeline(settings=mock_settings)
        await pipeline.search("test query", top_k=5)

        # Verify custom top_k was used
        call_args = mock_engine.search.call_args
        assert call_args.kwargs["top_k"] == 5


class TestRAGPipelineEvaluate:
    """Test RAG pipeline evaluate method."""

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.ClaudeContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    async def test_evaluate_multiple_queries(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test evaluating multiple queries."""
        mock_result = MagicMock()
        mock_result.article_number = "121"
        mock_result.text = "Test text"
        mock_result.score = 0.9
        mock_result.metadata = {}

        mock_engine = MagicMock()
        mock_engine.search.return_value = [mock_result]
        mock_engine.get_name.return_value = "mock_engine"
        mock_search_engine.return_value = mock_engine

        mock_settings = MagicMock()
        mock_settings.top_k = 10
        mock_settings.score_threshold = 0.5
        mock_settings.enable_query_expansion = False

        pipeline = RAGPipeline(settings=mock_settings)

        queries = ["query 1", "query 2", "query 3"]
        result = await pipeline.evaluate(queries)

        assert result["total_queries"] == 3
        assert "average_latency" in result
        assert len(result["results"]) == 3

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.ClaudeContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    async def test_evaluate_with_ground_truth(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test evaluate with ground truth computes metrics."""
        mock_result = MagicMock()
        mock_result.article_number = "121"
        mock_result.text = "Test"
        mock_result.score = 0.9
        mock_result.metadata = {}

        mock_engine = MagicMock()
        mock_engine.search.return_value = [mock_result]
        mock_engine.get_name.return_value = "mock_engine"
        mock_search_engine.return_value = mock_engine

        mock_settings = MagicMock()
        mock_settings.top_k = 10
        mock_settings.score_threshold = 0.5
        mock_settings.enable_query_expansion = False

        pipeline = RAGPipeline(settings=mock_settings)

        queries = ["query 1"]
        ground_truth = [["121"]]
        result = await pipeline.evaluate(queries, ground_truth)

        assert "metrics" in result
        assert "recall_at_1" in result["metrics"]


class TestRAGPipelineStats:
    """Test RAG pipeline statistics."""

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.ClaudeContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    def test_get_stats_returns_dict(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_embedding,
    ):
        """Test get_stats returns pipeline statistics."""
        mock_engine = MagicMock()
        mock_engine.get_name.return_value = "HybridRRFColBERT"
        mock_search_engine.return_value = mock_engine

        mock_settings = MagicMock()
        mock_settings.api_provider.value = "claude"
        mock_settings.model_name = "claude-3"
        mock_settings.collection_name = "test_collection"

        pipeline = RAGPipeline(settings=mock_settings)
        stats = pipeline.get_stats()

        assert stats["api_provider"] == "claude"
        assert stats["model"] == "claude-3"
        assert stats["search_engine"] == "HybridRRFColBERT"
        assert stats["collection"] == "test_collection"


class TestRAGResult:
    """Test RAGResult dataclass."""

    def test_rag_result_creation(self):
        """Test RAGResult creation with all fields."""
        result = RAGResult(
            query="test query",
            results=[{"text": "result 1"}],
            context_used=True,
            search_method="hybrid",
            execution_time=0.5,
        )

        assert result.query == "test query"
        assert len(result.results) == 1
        assert result.context_used is True
        assert result.search_method == "hybrid"
        assert result.execution_time == 0.5

    def test_rag_result_empty_results(self):
        """Test RAGResult with empty results."""
        result = RAGResult(
            query="query",
            results=[],
            context_used=False,
            search_method="baseline",
            execution_time=0.1,
        )

        assert len(result.results) == 0
