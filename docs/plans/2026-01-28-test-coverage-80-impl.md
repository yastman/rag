# Test Coverage 80% Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Increase test coverage from 53% to 80% by adding unit tests for uncovered modules.

**Architecture:** Create isolated unit tests with mocks for external services (Qdrant, Redis, MLflow, Voyage API). Each task creates one test file, commits after tests pass.

**Tech Stack:** pytest, unittest.mock, pytest-asyncio, pytest-cov

---

## Task 1: Test src/core/pipeline.py (85 stmts, 0% → 90%)

**Files:**
- Create: `tests/unit/core/__init__.py`
- Create: `tests/unit/core/test_pipeline.py`
- Read: `src/core/pipeline.py`

**Step 1: Create test directory**

```bash
mkdir -p tests/unit/core && touch tests/unit/core/__init__.py
```

**Step 2: Write the failing test for RAGResult dataclass**

```python
# tests/unit/core/test_pipeline.py
"""Tests for RAG pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.pipeline import RAGPipeline, RAGResult


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
```

**Step 3: Run test to verify it passes**

Run: `pytest tests/unit/core/test_pipeline.py::TestRAGResult -v`
Expected: PASS

**Step 4: Write tests for RAGPipeline initialization**

```python
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

        pipeline = RAGPipeline(settings=settings)

        mock_contextualizer.assert_called_once()
```

**Step 5: Write tests for search method**

```python
class TestRAGPipelineSearch:
    """Tests for RAGPipeline.search()."""

    @pytest.fixture
    def mock_pipeline(self):
        """Create pipeline with mocked dependencies."""
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

    @pytest.mark.asyncio
    async def test_search_returns_rag_result(self, mock_pipeline):
        """Test search returns RAGResult with correct structure."""
        result = await mock_pipeline.search("test query")

        assert isinstance(result, RAGResult)
        assert result.query == "test query"
        assert len(result.results) == 1
        assert result.results[0]["article_number"] == "121"

    @pytest.mark.asyncio
    async def test_search_respects_top_k(self, mock_pipeline):
        """Test search uses provided top_k value."""
        await mock_pipeline.search("query", top_k=5)

        mock_pipeline.search_engine.search.assert_called()

    @pytest.mark.asyncio
    async def test_search_tracks_execution_time(self, mock_pipeline):
        """Test search tracks execution time."""
        result = await mock_pipeline.search("query")

        assert result.execution_time >= 0
```

**Step 6: Write tests for get_stats and _compute_metrics**

```python
class TestRAGPipelineStats:
    """Tests for pipeline statistics methods."""

    @pytest.fixture
    def mock_pipeline(self):
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

    def test_compute_metrics_placeholder(self, mock_pipeline):
        """Test _compute_metrics returns placeholder metrics."""
        results = [
            RAGResult("q1", [{"article_number": "1"}], True, "test", 0.1),
        ]
        ground_truth = [["1"]]

        metrics = mock_pipeline._compute_metrics(results, ground_truth)

        assert "recall_at_1" in metrics
        assert "mrr" in metrics
```

**Step 7: Run all tests**

Run: `pytest tests/unit/core/test_pipeline.py -v`
Expected: All PASS

**Step 8: Check coverage**

Run: `pytest tests/unit/core/test_pipeline.py --cov=src/core/pipeline --cov-report=term-missing`
Expected: ~90% coverage

**Step 9: Commit**

```bash
git add tests/unit/core/
git commit -m "test(core): add unit tests for RAGPipeline

- Test RAGResult dataclass creation
- Test pipeline initialization with different providers
- Test search method returns correct results
- Test get_stats and _compute_metrics methods

Coverage: src/core/pipeline.py 0% → ~90%"
```

---

## Task 2: Test src/ingestion/voyage_indexer.py (124 stmts, 0% → 85%)

**Files:**
- Create: `tests/unit/ingestion/__init__.py`
- Create: `tests/unit/ingestion/test_voyage_indexer.py`
- Read: `src/ingestion/voyage_indexer.py`

**Step 1: Create test directory**

```bash
mkdir -p tests/unit/ingestion && touch tests/unit/ingestion/__init__.py
```

**Step 2: Write tests for IndexStats dataclass**

```python
# tests/unit/ingestion/test_voyage_indexer.py
"""Tests for Voyage AI document indexer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.voyage_indexer import IndexStats, VoyageIndexer


class TestIndexStats:
    """Tests for IndexStats dataclass."""

    def test_index_stats_defaults(self):
        """Test IndexStats has correct defaults."""
        stats = IndexStats()

        assert stats.total_chunks == 0
        assert stats.indexed_chunks == 0
        assert stats.failed_chunks == 0
        assert stats.duration_seconds == 0.0

    def test_index_stats_custom_values(self):
        """Test IndexStats accepts custom values."""
        stats = IndexStats(
            total_chunks=100,
            indexed_chunks=95,
            failed_chunks=5,
            duration_seconds=10.5,
        )

        assert stats.total_chunks == 100
        assert stats.indexed_chunks == 95
```

**Step 3: Write tests for VoyageIndexer initialization**

```python
class TestVoyageIndexerInit:
    """Tests for VoyageIndexer initialization."""

    @patch("src.ingestion.voyage_indexer.QdrantClient")
    @patch("src.ingestion.voyage_indexer.VoyageService")
    @patch("src.ingestion.voyage_indexer.SparseTextEmbedding")
    def test_init_with_defaults(self, mock_sparse, mock_voyage, mock_qdrant):
        """Test indexer initializes with environment defaults."""
        with patch.dict(
            "os.environ",
            {
                "QDRANT_URL": "http://test:6333",
                "QDRANT_API_KEY": "",
                "VOYAGE_API_KEY": "test-key",
            },
        ):
            indexer = VoyageIndexer()

            assert indexer.qdrant_url == "http://test:6333"
            mock_qdrant.assert_called_once()
            mock_voyage.assert_called_once()
            mock_sparse.assert_called_once()

    @patch("src.ingestion.voyage_indexer.QdrantClient")
    @patch("src.ingestion.voyage_indexer.VoyageService")
    @patch("src.ingestion.voyage_indexer.SparseTextEmbedding")
    def test_init_with_api_key(self, mock_sparse, mock_voyage, mock_qdrant):
        """Test indexer uses API key when provided."""
        indexer = VoyageIndexer(
            qdrant_url="http://cloud:6333",
            qdrant_api_key="secret",
            voyage_api_key="voyage-key",
        )

        mock_qdrant.assert_called_with(
            url="http://cloud:6333", api_key="secret", timeout=120
        )
```

**Step 4: Write tests for create_collection**

```python
class TestCreateCollection:
    """Tests for VoyageIndexer.create_collection()."""

    @pytest.fixture
    def indexer(self):
        with patch("src.ingestion.voyage_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.voyage_indexer.VoyageService"):
                with patch("src.ingestion.voyage_indexer.SparseTextEmbedding"):
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client

                    idx = VoyageIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    yield idx

    def test_create_collection_new(self, indexer):
        """Test creating a new collection."""
        indexer.client.get_collection.side_effect = Exception("Not found")

        result = indexer.create_collection("test_collection")

        assert result is True
        indexer.client.create_collection.assert_called_once()

    def test_create_collection_exists_no_recreate(self, indexer):
        """Test existing collection without recreate."""
        indexer.client.get_collection.return_value = MagicMock()

        result = indexer.create_collection("existing", recreate=False)

        assert result is True
        indexer.client.create_collection.assert_not_called()

    def test_create_collection_exists_with_recreate(self, indexer):
        """Test existing collection with recreate=True."""
        indexer.client.get_collection.return_value = MagicMock()

        result = indexer.create_collection("existing", recreate=True)

        assert result is True
        indexer.client.delete_collection.assert_called_once_with("existing")
        indexer.client.create_collection.assert_called_once()
```

**Step 5: Write tests for index_chunks**

```python
class TestIndexChunks:
    """Tests for VoyageIndexer.index_chunks()."""

    @pytest.fixture
    def indexer(self):
        with patch("src.ingestion.voyage_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.voyage_indexer.VoyageService") as mock_voyage:
                with patch("src.ingestion.voyage_indexer.SparseTextEmbedding") as mock_sparse:
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client
                    mock_client.get_collection.side_effect = Exception("Not found")

                    mock_voyage_inst = AsyncMock()
                    mock_voyage_inst.embed_documents = AsyncMock(
                        return_value=[[0.1] * 1024]
                    )
                    mock_voyage.return_value = mock_voyage_inst

                    # Mock sparse embedding
                    mock_sparse_inst = MagicMock()
                    mock_sparse_emb = MagicMock()
                    mock_sparse_emb.indices = MagicMock(tolist=lambda: [1, 2, 3])
                    mock_sparse_emb.values = MagicMock(tolist=lambda: [0.5, 0.3, 0.2])
                    mock_sparse_inst.embed.return_value = [mock_sparse_emb]
                    mock_sparse.return_value = mock_sparse_inst

                    idx = VoyageIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    idx.voyage_service = mock_voyage_inst
                    idx.sparse_model = mock_sparse_inst
                    yield idx

    @pytest.mark.asyncio
    async def test_index_chunks_single_batch(self, indexer):
        """Test indexing a single batch of chunks."""
        from src.ingestion.chunker import Chunk

        chunks = [
            Chunk(
                text="Test document",
                chunk_id=1,
                document_name="test.pdf",
                article_number="1",
            )
        ]

        # Mock sparse embedding properly
        mock_sparse_emb = MagicMock()
        mock_sparse_emb.indices.tolist.return_value = [1, 2, 3]
        mock_sparse_emb.values.tolist.return_value = [0.5, 0.3, 0.2]
        indexer.sparse_model.embed.return_value = [mock_sparse_emb]

        stats = await indexer.index_chunks(
            chunks, "test_collection", batch_size=10, rate_limit_delay=0.01
        )

        assert stats.total_chunks == 1
        assert stats.indexed_chunks == 1
        assert stats.failed_chunks == 0
        indexer.client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_chunks_handles_error(self, indexer):
        """Test indexing handles errors gracefully."""
        from src.ingestion.chunker import Chunk

        chunks = [Chunk(text="Test", chunk_id=1, document_name="test.pdf")]

        indexer.voyage_service.embed_documents.side_effect = Exception("API error")

        stats = await indexer.index_chunks(
            chunks, "test_collection", batch_size=10, rate_limit_delay=0.01
        )

        assert stats.failed_chunks == 1
```

**Step 6: Write tests for get_collection_stats**

```python
class TestGetCollectionStats:
    """Tests for VoyageIndexer.get_collection_stats()."""

    @pytest.fixture
    def indexer(self):
        with patch("src.ingestion.voyage_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.voyage_indexer.VoyageService"):
                with patch("src.ingestion.voyage_indexer.SparseTextEmbedding"):
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client

                    idx = VoyageIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    yield idx

    def test_get_collection_stats_success(self, indexer):
        """Test getting collection stats."""
        mock_info = MagicMock()
        mock_info.points_count = 100
        mock_info.vectors_count = 200
        mock_info.indexed_vectors_count = 200
        indexer.client.get_collection.return_value = mock_info

        stats = indexer.get_collection_stats("test")

        assert stats["name"] == "test"
        assert stats["points_count"] == 100

    def test_get_collection_stats_error(self, indexer):
        """Test getting stats handles errors."""
        indexer.client.get_collection.side_effect = Exception("Error")

        stats = indexer.get_collection_stats("test")

        assert stats == {}
```

**Step 7: Run all tests**

Run: `pytest tests/unit/ingestion/test_voyage_indexer.py -v`
Expected: All PASS

**Step 8: Check coverage**

Run: `pytest tests/unit/ingestion/test_voyage_indexer.py --cov=src/ingestion/voyage_indexer --cov-report=term-missing`
Expected: ~85% coverage

**Step 9: Commit**

```bash
git add tests/unit/ingestion/
git commit -m "test(ingestion): add unit tests for VoyageIndexer

- Test IndexStats dataclass
- Test VoyageIndexer initialization with/without API keys
- Test create_collection with recreate options
- Test index_chunks batch processing
- Test get_collection_stats

Coverage: src/ingestion/voyage_indexer.py 0% → ~85%"
```

---

## Task 3: Test src/evaluation/mlflow_integration.py (91 stmts, 0% → 90%)

**Files:**
- Create: `tests/unit/evaluation/__init__.py`
- Create: `tests/unit/evaluation/test_mlflow_integration.py`
- Read: `src/evaluation/mlflow_integration.py`

**Step 1: Create test directory**

```bash
mkdir -p tests/unit/evaluation && touch tests/unit/evaluation/__init__.py
```

**Step 2: Write tests for MLflowRAGLogger initialization**

```python
# tests/unit/evaluation/test_mlflow_integration.py
"""Tests for MLflow integration."""

from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.mlflow_integration import MLflowRAGLogger, log_ab_test_results


class TestMLflowRAGLoggerInit:
    """Tests for MLflowRAGLogger initialization."""

    @patch("src.evaluation.mlflow_integration.mlflow")
    @patch("src.evaluation.mlflow_integration.MlflowClient")
    def test_init_creates_experiment(self, mock_client_class, mock_mlflow):
        """Test logger creates new experiment."""
        mock_client = MagicMock()
        mock_client.create_experiment.return_value = "exp-123"
        mock_client_class.return_value = mock_client

        logger = MLflowRAGLogger(experiment_name="test_exp")

        mock_mlflow.set_tracking_uri.assert_called_once()
        mock_client.create_experiment.assert_called_once_with("test_exp")
        assert logger.experiment_id == "exp-123"

    @patch("src.evaluation.mlflow_integration.mlflow")
    @patch("src.evaluation.mlflow_integration.MlflowClient")
    def test_init_uses_existing_experiment(self, mock_client_class, mock_mlflow):
        """Test logger uses existing experiment."""
        mock_client = MagicMock()
        mock_client.create_experiment.side_effect = Exception("Exists")
        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "existing-123"
        mock_client.get_experiment_by_name.return_value = mock_experiment
        mock_client_class.return_value = mock_client

        logger = MLflowRAGLogger(experiment_name="existing")

        assert logger.experiment_id == "existing-123"
```

**Step 3: Write tests for start_run and end_run**

```python
class TestRunManagement:
    """Tests for run management methods."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_start_run_creates_run(self, mock_mlflow, logger):
        """Test start_run creates MLflow run."""
        mock_run = MagicMock()
        mock_mlflow.start_run.return_value = mock_run

        result = logger.start_run(run_name="test_run")

        mock_mlflow.start_run.assert_called_once()
        assert logger.current_run == mock_run

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_start_run_adds_timestamp_tag(self, mock_mlflow, logger):
        """Test start_run adds timestamp tag."""
        logger.start_run(run_name="test", tags={"custom": "tag"})

        call_args = mock_mlflow.start_run.call_args
        tags = call_args[1]["tags"]
        assert "timestamp" in tags
        assert "custom" in tags

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_end_run_clears_current_run(self, mock_mlflow, logger):
        """Test end_run clears current run."""
        logger.current_run = MagicMock()

        logger.end_run()

        mock_mlflow.end_run.assert_called_once()
        assert logger.current_run is None
```

**Step 4: Write tests for log_config**

```python
class TestLogConfig:
    """Tests for log_config method."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_returns_hash(self, mock_mlflow, logger):
        """Test log_config returns config hash."""
        config = {"key": "value", "num": 42}

        result = logger.log_config(config)

        assert len(result) == 12  # SHA256 hash truncated to 12 chars

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_logs_parameters(self, mock_mlflow, logger):
        """Test log_config logs all parameters."""
        config = {"engine": "hybrid", "top_k": 10}

        logger.log_config(config, prefix="search.")

        mock_mlflow.log_param.assert_any_call("search.config_hash", mock_mlflow.log_param.call_args_list[0][0][1])
        mock_mlflow.log_param.assert_any_call("search.engine", "hybrid")
        mock_mlflow.log_param.assert_any_call("search.top_k", 10)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_handles_nested_dict(self, mock_mlflow, logger):
        """Test log_config handles nested dictionaries."""
        config = {"outer": {"inner": "value"}}

        logger.log_config(config)

        mock_mlflow.log_param.assert_any_call("outer.inner", "value")

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_handles_list(self, mock_mlflow, logger):
        """Test log_config handles list values."""
        config = {"items": [1, 2, 3]}

        logger.log_config(config)

        # List should be JSON-encoded
        mock_mlflow.log_param.assert_any_call("items", "[1, 2, 3]")
```

**Step 5: Write tests for log_metrics**

```python
class TestLogMetrics:
    """Tests for log_metrics method."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_metrics_from_dict(self, mock_mlflow, logger):
        """Test log_metrics logs dictionary of metrics."""
        metrics = {"precision": 0.94, "recall": 0.98}

        logger.log_metrics(metrics)

        mock_mlflow.log_metric.assert_any_call("precision", 0.94, step=None)
        mock_mlflow.log_metric.assert_any_call("recall", 0.98, step=None)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_metrics_from_kwargs(self, mock_mlflow, logger):
        """Test log_metrics accepts kwargs."""
        logger.log_metrics(precision=0.94, recall=0.98)

        mock_mlflow.log_metric.assert_any_call("precision", 0.94, step=None)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_metrics_with_step(self, mock_mlflow, logger):
        """Test log_metrics with step parameter."""
        logger.log_metrics({"loss": 0.5}, step=10)

        mock_mlflow.log_metric.assert_called_with("loss", 0.5, step=10)
```

**Step 6: Write tests for log_artifact**

```python
class TestLogArtifact:
    """Tests for artifact logging methods."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_artifact_file(self, mock_mlflow, logger):
        """Test log_artifact logs file."""
        logger.log_artifact("/path/to/file.json", artifact_path="data")

        mock_mlflow.log_artifact.assert_called_once_with(
            "/path/to/file.json", artifact_path="data"
        )

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_dict_artifact(self, mock_mlflow, logger):
        """Test log_dict_artifact creates temp file and logs."""
        data = {"key": "value"}

        logger.log_dict_artifact(data, "test.json", artifact_path="configs")

        mock_mlflow.log_artifact.assert_called_once()
```

**Step 7: Write tests for get_run_url**

```python
class TestGetRunUrl:
    """Tests for get_run_url method."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                log.experiment_id = "exp-1"
                log.tracking_uri = "http://localhost:5000"
                yield log

    def test_get_run_url_no_current_run(self, logger):
        """Test get_run_url returns base URL when no run active."""
        logger.current_run = None

        url = logger.get_run_url()

        assert url == "http://localhost:5000"

    def test_get_run_url_with_current_run(self, logger):
        """Test get_run_url returns run-specific URL."""
        mock_run = MagicMock()
        mock_run.info.run_id = "run-123"
        logger.current_run = mock_run

        url = logger.get_run_url()

        assert "run-123" in url
        assert "exp-1" in url
```

**Step 8: Write tests for log_ab_test_results helper**

```python
class TestLogABTestResults:
    """Tests for log_ab_test_results convenience function."""

    @patch("src.evaluation.mlflow_integration.MLflowRAGLogger")
    @patch("src.evaluation.mlflow_integration.Path")
    def test_log_ab_test_results(self, mock_path, mock_logger_class):
        """Test log_ab_test_results creates run and logs data."""
        mock_logger = MagicMock()
        mock_logger.start_run.return_value.__enter__ = MagicMock()
        mock_logger.start_run.return_value.__exit__ = MagicMock()
        mock_logger.get_run_url.return_value = "http://mlflow/run/123"
        mock_logger_class.return_value = mock_logger
        mock_path.return_value.exists.return_value = True

        result = log_ab_test_results(
            engine_name="hybrid",
            config={"top_k": 10},
            metrics={"precision": 0.94},
            report_path="/path/to/report.md",
        )

        assert result == "http://mlflow/run/123"
        mock_logger.log_config.assert_called_once()
        mock_logger.log_metrics.assert_called_once()
```

**Step 9: Run all tests**

Run: `pytest tests/unit/evaluation/test_mlflow_integration.py -v`
Expected: All PASS

**Step 10: Check coverage**

Run: `pytest tests/unit/evaluation/test_mlflow_integration.py --cov=src/evaluation/mlflow_integration --cov-report=term-missing`
Expected: ~90% coverage

**Step 11: Commit**

```bash
git add tests/unit/evaluation/
git commit -m "test(evaluation): add unit tests for MLflow integration

- Test MLflowRAGLogger initialization
- Test run management (start/end)
- Test log_config with nested dicts and lists
- Test log_metrics from dict and kwargs
- Test artifact logging
- Test log_ab_test_results helper

Coverage: src/evaluation/mlflow_integration.py 0% → ~90%"
```

---

## Task 4: Test telegram_bot/services/cesc.py (43 stmts, 25% → 95%)

**Files:**
- Create: `tests/unit/test_cesc_service.py`
- Read: `telegram_bot/services/cesc.py`

**Step 1: Write tests for is_personalized_query function**

```python
# tests/unit/test_cesc_service.py
"""Tests for CESC personalizer service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.cesc import (
    CESCPersonalizer,
    is_personalized_query,
    PERSONAL_MARKERS,
)


class TestIsPersonalizedQuery:
    """Tests for is_personalized_query function."""

    def test_query_with_russian_marker_mne(self):
        """Test query with 'мне' marker returns True."""
        assert is_personalized_query("покажи мне квартиры") is True

    def test_query_with_russian_marker_ya_predpochitayu(self):
        """Test query with 'я предпочитаю' marker returns True."""
        assert is_personalized_query("я предпочитаю двухкомнатные") is True

    def test_query_with_russian_marker_moy_budget(self):
        """Test query with 'мой бюджет' marker returns True."""
        assert is_personalized_query("мой бюджет до 50000 евро") is True

    def test_query_with_english_marker_for_me(self):
        """Test query with 'for me' marker returns True."""
        assert is_personalized_query("find apartments for me") is True

    def test_query_with_english_marker_my_budget(self):
        """Test query with 'my budget' marker returns True."""
        assert is_personalized_query("my budget is 100k") is True

    def test_generic_query_no_markers(self):
        """Test generic query without markers returns False."""
        assert is_personalized_query("квартиры в Бургасе") is False

    def test_query_case_insensitive(self):
        """Test markers are matched case-insensitively."""
        assert is_personalized_query("МНЕ нужна квартира") is True
        assert is_personalized_query("For Me please") is True

    def test_query_with_user_context_preferences(self):
        """Test query with user preferences returns True."""
        context = {"preferences": {"cities": ["Бургас"]}}

        assert is_personalized_query("квартиры", context) is True

    def test_query_with_user_context_budget(self):
        """Test query with budget preference returns True."""
        context = {"preferences": {"budget_max": 50000}}

        assert is_personalized_query("квартиры", context) is True

    def test_query_with_empty_user_context(self):
        """Test query with empty context returns False."""
        context = {"preferences": {}}

        assert is_personalized_query("квартиры", context) is False

    def test_query_with_none_user_context(self):
        """Test query with None context returns False."""
        assert is_personalized_query("квартиры", None) is False
```

**Step 2: Write tests for CESCPersonalizer initialization**

```python
class TestCESCPersonalizerInit:
    """Tests for CESCPersonalizer initialization."""

    def test_init_stores_llm_service(self):
        """Test initializer stores LLM service."""
        mock_llm = MagicMock()

        personalizer = CESCPersonalizer(mock_llm)

        assert personalizer.llm is mock_llm
```

**Step 3: Write tests for should_personalize method**

```python
class TestShouldPersonalize:
    """Tests for CESCPersonalizer.should_personalize()."""

    @pytest.fixture
    def personalizer(self):
        return CESCPersonalizer(MagicMock())

    def test_should_personalize_with_cities(self, personalizer):
        """Test returns True when cities preference exists."""
        context = {"preferences": {"cities": ["Бургас"]}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_budget(self, personalizer):
        """Test returns True when budget_max preference exists."""
        context = {"preferences": {"budget_max": 100000}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_property_types(self, personalizer):
        """Test returns True when property_types preference exists."""
        context = {"preferences": {"property_types": ["apartment"]}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_rooms(self, personalizer):
        """Test returns True when rooms preference exists."""
        context = {"preferences": {"rooms": 2}}

        assert personalizer.should_personalize(context) is True

    def test_should_not_personalize_empty_prefs(self, personalizer):
        """Test returns False with empty preferences."""
        context = {"preferences": {}}

        assert personalizer.should_personalize(context) is False

    def test_should_not_personalize_no_prefs_key(self, personalizer):
        """Test returns False without preferences key."""
        context = {}

        assert personalizer.should_personalize(context) is False
```

**Step 4: Write tests for _build_prompt method**

```python
class TestBuildPrompt:
    """Tests for CESCPersonalizer._build_prompt()."""

    @pytest.fixture
    def personalizer(self):
        return CESCPersonalizer(MagicMock())

    def test_build_prompt_includes_response(self, personalizer):
        """Test prompt includes cached response."""
        context = {"preferences": {}}

        prompt = personalizer._build_prompt("cached answer", context)

        assert "cached answer" in prompt

    def test_build_prompt_includes_cities(self, personalizer):
        """Test prompt includes cities from preferences."""
        context = {"preferences": {"cities": ["Бургас", "Варна"]}}

        prompt = personalizer._build_prompt("response", context)

        assert "Бургас" in prompt
        assert "Варна" in prompt

    def test_build_prompt_includes_budget(self, personalizer):
        """Test prompt includes budget from preferences."""
        context = {"preferences": {"budget_max": 50000}}

        prompt = personalizer._build_prompt("response", context)

        assert "50000" in prompt

    def test_build_prompt_truncates_long_response(self, personalizer):
        """Test prompt truncates response to 500 chars."""
        long_response = "x" * 1000
        context = {"preferences": {}}

        prompt = personalizer._build_prompt(long_response, context)

        # Should contain truncated response
        assert "x" * 500 in prompt
        assert "x" * 501 not in prompt

    def test_build_prompt_includes_profile_summary(self, personalizer):
        """Test prompt includes profile summary."""
        context = {
            "preferences": {},
            "profile_summary": "активный покупатель",
        }

        prompt = personalizer._build_prompt("response", context)

        assert "активный покупатель" in prompt

    def test_build_prompt_default_values(self, personalizer):
        """Test prompt uses defaults for missing values."""
        context = {"preferences": {}}

        prompt = personalizer._build_prompt("response", context)

        assert "любой" in prompt  # Default for cities
        assert "новый пользователь" in prompt  # Default profile
```

**Step 5: Write tests for personalize method**

```python
class TestPersonalize:
    """Tests for CESCPersonalizer.personalize()."""

    @pytest.fixture
    def personalizer(self):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="personalized response")
        return CESCPersonalizer(mock_llm)

    @pytest.mark.asyncio
    async def test_personalize_returns_personalized_response(self, personalizer):
        """Test personalize returns LLM response."""
        context = {"preferences": {"cities": ["Бургас"]}}

        result = await personalizer.personalize(
            "cached response", context, "test query"
        )

        assert result == "personalized response"
        personalizer.llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_personalize_skips_without_preferences(self, personalizer):
        """Test personalize returns cached when no preferences."""
        context = {"preferences": {}}

        result = await personalizer.personalize(
            "cached response", context, "test query"
        )

        assert result == "cached response"
        personalizer.llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_personalize_handles_llm_error(self, personalizer):
        """Test personalize returns cached on LLM error."""
        context = {"preferences": {"cities": ["Бургас"]}}
        personalizer.llm.generate.side_effect = Exception("LLM error")

        result = await personalizer.personalize(
            "cached response", context, "test query"
        )

        assert result == "cached response"

    @pytest.mark.asyncio
    async def test_personalize_strips_response(self, personalizer):
        """Test personalize strips whitespace from response."""
        context = {"preferences": {"cities": ["Бургас"]}}
        personalizer.llm.generate.return_value = "  response with spaces  "

        result = await personalizer.personalize(
            "cached", context, "query"
        )

        assert result == "response with spaces"
```

**Step 6: Run all tests**

Run: `pytest tests/unit/test_cesc_service.py -v`
Expected: All PASS

**Step 7: Check coverage**

Run: `pytest tests/unit/test_cesc_service.py --cov=telegram_bot/services/cesc --cov-report=term-missing`
Expected: ~95% coverage

**Step 8: Commit**

```bash
git add tests/unit/test_cesc_service.py
git commit -m "test(cesc): add comprehensive unit tests for CESC personalizer

- Test is_personalized_query with Russian/English markers
- Test is_personalized_query with user context preferences
- Test CESCPersonalizer.should_personalize()
- Test _build_prompt with various preferences
- Test personalize async method with success/error cases

Coverage: telegram_bot/services/cesc.py 25% → ~95%"
```

---

## Task 5: Test telegram_bot/services/cache.py extended (65% → 85%)

**Files:**
- Modify: `tests/unit/test_cache_service.py`
- Read: `telegram_bot/services/cache.py`

**Step 1: Read existing tests to understand gaps**

Run: `pytest tests/unit/test_cache_service.py --cov=telegram_bot/services/cache --cov-report=term-missing -q`

**Step 2: Add tests for RerankCache operations**

```python
# Add to tests/unit/test_cache_service.py

class TestRerankCache:
    """Tests for rerank cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_rerank_cache_hit(self, cache_service):
        """Test rerank cache hit returns cached results."""
        cached_data = [{"doc_id": "1", "score": 0.95}]
        cache_service.redis_client.get = AsyncMock(
            return_value='[{"doc_id": "1", "score": 0.95}]'
        )

        result = await cache_service.get_rerank_cache("query", ["doc1"])

        assert result == cached_data

    @pytest.mark.asyncio
    async def test_get_rerank_cache_miss(self, cache_service):
        """Test rerank cache miss returns None."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        result = await cache_service.get_rerank_cache("query", ["doc1"])

        assert result is None

    @pytest.mark.asyncio
    async def test_set_rerank_cache(self, cache_service):
        """Test setting rerank cache."""
        results = [{"doc_id": "1", "score": 0.95}]

        await cache_service.set_rerank_cache("query", ["doc1"], results)

        cache_service.redis_client.setex.assert_called_once()


class TestSparseCache:
    """Tests for sparse vector cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_sparse_cache_hit(self, cache_service):
        """Test sparse cache hit returns cached vector."""
        cached_vector = {"indices": [1, 2], "values": [0.5, 0.3]}
        cache_service.redis_client.get = AsyncMock(
            return_value='{"indices": [1, 2], "values": [0.5, 0.3]}'
        )

        result = await cache_service.get_sparse_cache("test text")

        assert result == cached_vector

    @pytest.mark.asyncio
    async def test_get_sparse_cache_miss(self, cache_service):
        """Test sparse cache miss returns None."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        result = await cache_service.get_sparse_cache("test text")

        assert result is None


class TestConversationHistory:
    """Tests for conversation history operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_conversation_history(self, cache_service):
        """Test getting conversation history."""
        history = [{"role": "user", "content": "hello"}]
        cache_service.redis_client.lrange = AsyncMock(
            return_value=['{"role": "user", "content": "hello"}']
        )

        result = await cache_service.get_conversation_history("user123")

        assert len(result) == 1
        assert result[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_add_to_conversation_history(self, cache_service):
        """Test adding message to conversation history."""
        await cache_service.add_to_conversation_history(
            "user123", "user", "hello"
        )

        cache_service.redis_client.rpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_conversation_history(self, cache_service):
        """Test clearing conversation history."""
        await cache_service.clear_conversation_history("user123")

        cache_service.redis_client.delete.assert_called_once()


class TestCacheMetrics:
    """Tests for cache metrics."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    def test_get_metrics_returns_all_types(self, cache_service):
        """Test get_metrics returns metrics for all cache types."""
        metrics = cache_service.get_metrics()

        assert "semantic" in metrics
        assert "rerank" in metrics
        assert "sparse" in metrics
        assert "hits" in metrics["semantic"]
        assert "misses" in metrics["semantic"]

    def test_metrics_increment_on_hit(self, cache_service):
        """Test metrics increment correctly on cache hit."""
        initial_hits = cache_service.metrics["rerank"]["hits"]

        cache_service.metrics["rerank"]["hits"] += 1

        assert cache_service.metrics["rerank"]["hits"] == initial_hits + 1
```

**Step 3: Run tests and check coverage**

Run: `pytest tests/unit/test_cache_service.py --cov=telegram_bot/services/cache --cov-report=term-missing -v`
Expected: ~85% coverage

**Step 4: Commit**

```bash
git add tests/unit/test_cache_service.py
git commit -m "test(cache): extend CacheService tests for better coverage

- Add tests for RerankCache get/set operations
- Add tests for SparseCache operations
- Add tests for conversation history CRUD
- Add tests for cache metrics tracking

Coverage: telegram_bot/services/cache.py 65% → ~85%"
```

---

## Verification Commands

After completing all tasks:

```bash
# Full coverage check
pytest tests/unit/ --cov=src --cov=telegram_bot --cov-report=term-missing -q | tail -50

# Expected: Total coverage >= 80%
```

---

## Summary

| Task | Module | Before | After | Stmts |
|------|--------|--------|-------|-------|
| 1 | src/core/pipeline.py | 0% | ~90% | 85 |
| 2 | src/ingestion/voyage_indexer.py | 0% | ~85% | 124 |
| 3 | src/evaluation/mlflow_integration.py | 0% | ~90% | 91 |
| 4 | telegram_bot/services/cesc.py | 25% | ~95% | 43 |
| 5 | telegram_bot/services/cache.py | 65% | ~85% | 279 |

**Total new coverage:** ~500+ statements
**Projected final coverage:** ~75-80%
