"""Tests for RAG pipeline."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("pymupdf", reason="pymupdf not installed (ingest extra)")
pytestmark = pytest.mark.requires_extras

from src.core.pipeline import RAGPipeline, RAGResult


@pytest.fixture(autouse=True)
def _stable_api_env(monkeypatch):
    """Keep Settings() construction deterministic in CI without real secrets."""
    monkeypatch.setenv("API_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")


class TestRAGResult:
    """Tests for RAGResult dataclass."""

    def test_rag_result_creation(self):
        """Test RAGResult can be created with all fields."""
        result = RAGResult(
            query="test query",
            results=[{"text": "doc1", "score": 0.9}],
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
        """Test RAGResult with empty results list."""
        result = RAGResult(
            query="empty",
            results=[],
            context_used=False,
            search_method="baseline",
            execution_time=0.1,
        )

        assert result.results == []


class TestRAGPipelineInit:
    """Tests for RAGPipeline initialization."""

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.ClaudeContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    def test_pipeline_init_default_settings(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_transformer,
    ):
        """Test pipeline initializes with default settings."""
        mock_transformer.return_value = MagicMock()
        mock_search_engine.return_value = MagicMock()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-for-ci"}):
            pipeline = RAGPipeline()

        mock_transformer.assert_called_once()
        mock_search_engine.assert_called_once()
        assert pipeline.settings is not None

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.OpenAIContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    def test_pipeline_init_openai_provider(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_transformer,
    ):
        """Test pipeline uses OpenAI contextualizer when configured."""
        from src.config import APIProvider, Settings

        settings = MagicMock(spec=Settings)
        settings.api_provider = APIProvider.OPENAI

        mock_transformer.return_value = MagicMock()
        mock_search_engine.return_value = MagicMock()

        RAGPipeline(settings=settings)

        mock_contextualizer.assert_called_once()

    @patch("src.core.pipeline.get_sentence_transformer")
    @patch("src.core.pipeline.create_search_engine")
    @patch("src.core.pipeline.GroqContextualizer")
    @patch("src.core.pipeline.DocumentIndexer")
    @patch("src.core.pipeline.DocumentChunker")
    @patch("src.core.pipeline.UniversalDocumentParser")
    def test_pipeline_init_groq_provider(
        self,
        mock_parser,
        mock_chunker,
        mock_indexer,
        mock_contextualizer,
        mock_search_engine,
        mock_transformer,
    ):
        """Test pipeline uses Groq contextualizer when configured."""
        from src.config import APIProvider, Settings

        settings = MagicMock(spec=Settings)
        settings.api_provider = APIProvider.GROQ

        mock_transformer.return_value = MagicMock()
        mock_search_engine.return_value = MagicMock()

        RAGPipeline(settings=settings)

        mock_contextualizer.assert_called_once()


class TestRAGPipelineSearch:
    """Tests for RAGPipeline.search()."""

    @pytest.fixture
    def mock_pipeline(self):
        """Create pipeline with mocked dependencies."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-for-ci"}):
            with patch("src.core.pipeline.get_sentence_transformer") as mock_trans:
                with patch("src.core.pipeline.create_search_engine") as mock_engine:
                    with patch("src.core.pipeline.ClaudeContextualizer"):
                        with patch("src.core.pipeline.DocumentIndexer"):
                            with patch("src.core.pipeline.DocumentChunker"):
                                with patch("src.core.pipeline.UniversalDocumentParser"):
                                    mock_trans.return_value = MagicMock()

                                    # Mock search engine
                                    mock_se = MagicMock()
                                    mock_se.search.return_value = [
                                        MagicMock(
                                            article_number="121",
                                            text="Test document",
                                            score=0.95,
                                            metadata={"source": "test"},
                                        )
                                    ]
                                    mock_se.get_name.return_value = "mock_engine"
                                    mock_engine.return_value = mock_se

                                    pipeline = RAGPipeline()
                                    yield pipeline

    async def test_search_returns_rag_result(self, mock_pipeline):
        """Test search returns RAGResult with correct structure."""
        result = await mock_pipeline.search("test query")

        assert isinstance(result, RAGResult)
        assert result.query == "test query"
        assert len(result.results) == 1
        assert result.results[0]["article_number"] == "121"

    async def test_search_respects_top_k(self, mock_pipeline):
        """Test search uses provided top_k value."""
        await mock_pipeline.search("query", top_k=5)

        mock_pipeline.search_engine.search.assert_called()

    async def test_search_tracks_execution_time(self, mock_pipeline):
        """Test search tracks execution time."""
        result = await mock_pipeline.search("query")

        assert result.execution_time >= 0

    async def test_search_uses_context_flag(self, mock_pipeline):
        """Test search respects use_context parameter."""
        result = await mock_pipeline.search("query", use_context=False)

        assert result.context_used is False

    async def test_search_includes_metadata(self, mock_pipeline):
        """Test search includes metadata in results."""
        result = await mock_pipeline.search("query")

        assert "metadata" in result.results[0]
        assert result.results[0]["metadata"] == {"source": "test"}

    async def test_search_includes_search_method(self, mock_pipeline):
        """Test search includes search method name."""
        result = await mock_pipeline.search("query")

        assert result.search_method == "mock_engine"


class TestRAGPipelineStats:
    """Tests for pipeline statistics methods."""

    @pytest.fixture
    def mock_pipeline(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-for-ci"}):
            with patch("src.core.pipeline.get_sentence_transformer"):
                with patch("src.core.pipeline.create_search_engine") as mock_engine:
                    with patch("src.core.pipeline.ClaudeContextualizer"):
                        with patch("src.core.pipeline.DocumentIndexer"):
                            with patch("src.core.pipeline.DocumentChunker"):
                                with patch("src.core.pipeline.UniversalDocumentParser"):
                                    mock_se = MagicMock()
                                    mock_se.get_name.return_value = "test_engine"
                                    mock_engine.return_value = mock_se

                                    pipeline = RAGPipeline()
                                    yield pipeline

    def test_get_stats_returns_dict(self, mock_pipeline):
        """Test get_stats returns dictionary with expected keys."""
        stats = mock_pipeline.get_stats()

        assert "api_provider" in stats
        assert "model" in stats
        assert "search_engine" in stats
        assert "collection" in stats

    def test_get_stats_includes_search_engine_name(self, mock_pipeline):
        """Test get_stats includes search engine name."""
        stats = mock_pipeline.get_stats()

        assert stats["search_engine"] == "test_engine"

    def test_get_stats_includes_contextualization_stats(self, mock_pipeline):
        """Test get_stats includes contextualization stats when available."""
        mock_pipeline.contextualizer.get_stats = MagicMock(return_value={"calls": 5})
        stats = mock_pipeline.get_stats()

        assert "contextualization_stats" in stats
        assert stats["contextualization_stats"] == {"calls": 5}

    def test_compute_metrics_placeholder(self, mock_pipeline):
        """Test _compute_metrics returns placeholder metrics."""
        results = [
            RAGResult("q1", [{"article_number": "1"}], True, "test", 0.1),
        ]
        ground_truth = [["1"]]

        metrics = mock_pipeline._compute_metrics(results, ground_truth)

        assert "recall_at_1" in metrics
        assert "mrr" in metrics
        assert "ndcg_at_10" in metrics

    def test_compute_metrics_returns_all_metrics(self, mock_pipeline):
        """Test _compute_metrics returns all expected metric keys."""
        results = [RAGResult("q1", [], True, "test", 0.1)]
        ground_truth = [["1"]]

        metrics = mock_pipeline._compute_metrics(results, ground_truth)

        expected_keys = ["recall_at_1", "recall_at_5", "recall_at_10", "ndcg_at_10", "mrr"]
        for key in expected_keys:
            assert key in metrics


class TestRAGPipelineIndex:
    """Tests for RAGPipeline.index_documents()."""

    @pytest.fixture
    def mock_pipeline(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-for-ci"}):
            with patch("src.core.pipeline.get_sentence_transformer"):
                with patch("src.core.pipeline.create_search_engine"):
                    with patch("src.core.pipeline.ClaudeContextualizer"):
                        with patch("src.core.pipeline.DocumentIndexer") as mock_idx:
                            with patch("src.core.pipeline.DocumentChunker") as mock_chk:
                                with patch("src.core.pipeline.UniversalDocumentParser") as mock_psr:
                                    pipeline = RAGPipeline()
                                    # Set mock instances
                                    pipeline.indexer = mock_idx.return_value
                                    pipeline.chunker = mock_chk.return_value
                                    pipeline.parser = mock_psr.return_value
                                    yield pipeline

    async def test_index_documents_success(self, mock_pipeline):
        """Test successful document indexing."""
        from src.ingestion.voyage_indexer import IndexStats

        # Mock parser
        mock_doc = MagicMock()
        mock_doc.content = "Test content"
        mock_doc.filename = "test.pdf"
        mock_pipeline.parser.parse_file.return_value = mock_doc

        # Mock chunker
        mock_chunk = MagicMock()
        mock_pipeline.chunker.chunk_text.return_value = [mock_chunk]

        # Mock indexer
        mock_stats = IndexStats(
            total_chunks=1, indexed_chunks=1, failed_chunks=0, duration_seconds=0.5
        )
        mock_pipeline.indexer.index_chunks = AsyncMock(return_value=mock_stats)

        stats = await mock_pipeline.index_documents(["test.pdf"])

        assert stats["total_chunks"] == 1
        assert stats["indexed_chunks"] == 1
        mock_pipeline.indexer.create_collection.assert_called_once()
        mock_pipeline.indexer.index_chunks.assert_called_once()

    async def test_index_documents_handles_exception(self, mock_pipeline):
        """Test indexing handles parser exceptions."""
        from src.ingestion.voyage_indexer import IndexStats

        mock_pipeline.parser.parse_file.side_effect = Exception("Parse error")

        # Mock indexer (empty chunks)
        mock_stats = IndexStats(
            total_chunks=0, indexed_chunks=0, failed_chunks=0, duration_seconds=0.1
        )
        mock_pipeline.indexer.index_chunks = AsyncMock(return_value=mock_stats)

        stats = await mock_pipeline.index_documents(["bad.pdf"])

        assert stats["total_chunks"] == 0
        mock_pipeline.indexer.index_chunks.assert_called_once_with(
            chunks=[], collection_name=mock_pipeline.settings.collection_name
        )


class TestRAGPipelineEvaluate:
    """Tests for RAGPipeline.evaluate()."""

    @pytest.fixture
    def mock_pipeline(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-for-ci"}):
            with patch("src.core.pipeline.get_sentence_transformer"):
                with patch("src.core.pipeline.create_search_engine"):
                    with patch("src.core.pipeline.ClaudeContextualizer"):
                        with patch("src.core.pipeline.DocumentIndexer"):
                            with patch("src.core.pipeline.DocumentChunker"):
                                with patch("src.core.pipeline.UniversalDocumentParser"):
                                    pipeline = RAGPipeline()
                                    yield pipeline

    async def test_evaluate_returns_metrics(self, mock_pipeline):
        """Test evaluate returns expected metrics dict."""
        mock_pipeline.search = AsyncMock(return_value=RAGResult("q", [], True, "test", 0.1))

        results = await mock_pipeline.evaluate(["q1", "q2"], ground_truth=[["1"], ["2"]])

        assert "total_queries" in results
        assert results["total_queries"] == 2
        assert "average_latency" in results
        assert "metrics" in results
        assert "recall_at_1" in results["metrics"]
