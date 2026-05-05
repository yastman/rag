"""Static and runtime tests for observability span metadata.

AST-based tests for @observe decorator metadata (as_type, capture_input, capture_output)
on BGE-M3, Qdrant, and RAG pipeline spans.

Runtime tests verify model/collection metadata is passed to update_current_span.
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.bge_m3_client import BGE_M3_MODEL_NAME, BGEM3Client
from telegram_bot.services.qdrant import QdrantService


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _collect_observe_decorators(file_path: Path) -> dict[str, dict]:
    """Return dict: span_name -> {as_type, capture_input, capture_output, line}."""
    results: dict[str, dict] = {}
    tree = ast.parse(file_path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            is_observe = (isinstance(func, ast.Attribute) and func.attr == "observe") or (
                isinstance(func, ast.Name) and func.id == "observe"
            )
            if not is_observe:
                continue
            kwargs = {kw.arg: kw.value for kw in decorator.keywords}
            name_node = kwargs.get("name")
            if not isinstance(name_node, ast.Constant):
                continue
            span_name = name_node.value
            at = kwargs.get("as_type")
            ci = kwargs.get("capture_input")
            co = kwargs.get("capture_output")
            results[span_name] = {
                "as_type": getattr(at, "value", None) if at else None,
                "capture_input": getattr(ci, "value", None) if ci else None,
                "capture_output": getattr(co, "value", None) if co else None,
                "line": node.lineno,
            }
    return results


class TestBGEM3SpanMetadata:
    """BGE-M3 client spans must be typed as embedding with capture disabled."""

    @pytest.fixture(scope="class")
    def bge_spans(self):
        path = REPO_ROOT / "telegram_bot" / "services" / "bge_m3_client.py"
        return _collect_observe_decorators(path)

    @pytest.mark.parametrize(
        "span_name",
        [
            "bge-m3-encode-dense",
            "bge-m3-encode-sparse",
            "bge-m3-encode-hybrid",
            "bge-m3-rerank",
            "bge-m3-encode-colbert",
        ],
    )
    def test_bge_span_has_embedding_type_and_capture_disabled(self, bge_spans, span_name):
        assert span_name in bge_spans, f"Span '{span_name}' not found"
        info = bge_spans[span_name]
        assert info["as_type"] == "embedding", (
            f"Span '{span_name}' must have as_type='embedding' (got {info['as_type']!r})"
        )
        assert info["capture_input"] is False, (
            f"Span '{span_name}' must have capture_input=False (got {info['capture_input']!r})"
        )
        assert info["capture_output"] is False, (
            f"Span '{span_name}' must have capture_output=False (got {info['capture_output']!r})"
        )


class TestQdrantSpanMetadata:
    """Qdrant retrieval spans must be typed as retriever with capture disabled."""

    @pytest.fixture(scope="class")
    def qdrant_spans(self):
        path = REPO_ROOT / "telegram_bot" / "services" / "qdrant.py"
        return _collect_observe_decorators(path)

    @pytest.mark.parametrize(
        "span_name",
        [
            "qdrant-hybrid-search-rrf",
            "qdrant-hybrid-search-rrf-colbert",
            "qdrant-batch-search-rrf",
            "qdrant-search-score-boosting",
            "qdrant-mmr-rerank",
        ],
    )
    def test_qdrant_retrieval_span_has_retriever_type_and_capture_disabled(
        self, qdrant_spans, span_name
    ):
        assert span_name in qdrant_spans, f"Span '{span_name}' not found"
        info = qdrant_spans[span_name]
        assert info["as_type"] == "retriever", (
            f"Span '{span_name}' must have as_type='retriever' (got {info['as_type']!r})"
        )
        assert info["capture_input"] is False, (
            f"Span '{span_name}' must have capture_input=False (got {info['capture_input']!r})"
        )
        assert info["capture_output"] is False, (
            f"Span '{span_name}' must have capture_output=False (got {info['capture_output']!r})"
        )


class TestRAGPipelineSpanMetadata:
    """RAG pipeline spans must have correct as_type and capture flags."""

    @pytest.fixture(scope="class")
    def rag_spans(self):
        path = REPO_ROOT / "telegram_bot" / "agents" / "rag_pipeline.py"
        return _collect_observe_decorators(path)

    def test_grade_documents_has_evaluator_type(self, rag_spans):
        assert "grade-documents" in rag_spans, "Span 'grade-documents' not found"
        info = rag_spans["grade-documents"]
        assert info["as_type"] == "evaluator", (
            f"Span 'grade-documents' must have as_type='evaluator' (got {info['as_type']!r})"
        )

    def test_grade_documents_is_light_span(self, rag_spans):
        """grade-documents is a light span: must NOT have capture_input=False."""
        info = rag_spans["grade-documents"]
        assert info["capture_input"] is not False, (
            "grade-documents should not have capture_input=False (light span)"
        )


class TestBGEServiceWarmup:
    """BGE-M3 API service must not create Langfuse traces during warmup."""

    def test_app_py_has_no_observe_decorators(self):
        """services/bge-m3-api/app.py uses raw model calls and must not import @observe."""
        path = REPO_ROOT / "services" / "bge-m3-api" / "app.py"
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                is_observe = (isinstance(func, ast.Attribute) and func.attr == "observe") or (
                    isinstance(func, ast.Name) and func.id == "observe"
                )
                if is_observe:
                    pytest.fail(f"app.py must not use @observe decorators (line {node.lineno})")

    def test_warmup_encode_result_discarded(self):
        """Lifespan warmup must call model.encode() as a bare expression (result discarded)."""
        path = REPO_ROOT / "services" / "bge-m3-api" / "app.py"
        tree = ast.parse(path.read_text())
        lifespan_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
                lifespan_node = node
                break
        assert lifespan_node is not None, "lifespan function not found in app.py"

        found_bare_encode = False
        for child in ast.walk(lifespan_node):
            if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
                call = child.value
                func = call.func
                if isinstance(func, ast.Attribute) and func.attr == "encode":
                    found_bare_encode = True
                    break
        assert found_bare_encode, (
            "lifespan warmup must call model.encode() as a bare expression (discarded)"
        )


class TestBGEM3SpanRuntimeMetadata:
    """Runtime tests for BGE-M3 span metadata."""

    @pytest.fixture
    def mock_lf(self):
        mock = MagicMock()
        mock.update_current_span = MagicMock()
        return mock

    @pytest.fixture
    def bge_client(self):
        client = BGEM3Client(base_url="http://test")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={"dense_vecs": [[0.1] * 1024], "processing_time": 0.1}
        )
        client._client = AsyncMock()
        client._client.is_closed = False
        client._client.post = AsyncMock(return_value=mock_resp)
        return client

    async def test_encode_dense_exposes_model_metadata(self, mock_lf, bge_client):
        with patch("telegram_bot.services.bge_m3_client.get_client", return_value=mock_lf):
            await bge_client.encode_dense(["hello"])
        metadata_calls = [
            c for c in mock_lf.update_current_span.call_args_list if "metadata" in c.kwargs
        ]
        assert any(c.kwargs["metadata"].get("model") == BGE_M3_MODEL_NAME for c in metadata_calls)

    async def test_encode_sparse_exposes_model_metadata(self, mock_lf, bge_client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={"lexical_weights": [{"a": 0.1}], "processing_time": 0.1}
        )
        bge_client._client.post = AsyncMock(return_value=mock_resp)
        with patch("telegram_bot.services.bge_m3_client.get_client", return_value=mock_lf):
            await bge_client.encode_sparse(["hello"])
        metadata_calls = [
            c for c in mock_lf.update_current_span.call_args_list if "metadata" in c.kwargs
        ]
        assert any(c.kwargs["metadata"].get("model") == BGE_M3_MODEL_NAME for c in metadata_calls)

    async def test_encode_hybrid_exposes_model_metadata(self, mock_lf, bge_client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={
                "dense_vecs": [[0.1] * 1024],
                "lexical_weights": [{"a": 0.1}],
                "processing_time": 0.1,
            }
        )
        bge_client._client.post = AsyncMock(return_value=mock_resp)
        with patch("telegram_bot.services.bge_m3_client.get_client", return_value=mock_lf):
            await bge_client.encode_hybrid(["hello"])
        metadata_calls = [
            c for c in mock_lf.update_current_span.call_args_list if "metadata" in c.kwargs
        ]
        assert any(c.kwargs["metadata"].get("model") == BGE_M3_MODEL_NAME for c in metadata_calls)

    async def test_rerank_exposes_model_metadata(self, mock_lf, bge_client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={"results": [{"index": 0, "score": 0.9}], "processing_time": 0.1}
        )
        bge_client._client.post = AsyncMock(return_value=mock_resp)
        with patch("telegram_bot.services.bge_m3_client.get_client", return_value=mock_lf):
            await bge_client.rerank("query", ["doc1", "doc2"])
        metadata_calls = [
            c for c in mock_lf.update_current_span.call_args_list if "metadata" in c.kwargs
        ]
        assert any(c.kwargs["metadata"].get("model") == BGE_M3_MODEL_NAME for c in metadata_calls)

    async def test_encode_colbert_exposes_model_metadata(self, mock_lf, bge_client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={"colbert_vecs": [[[0.1] * 1024]], "processing_time": 0.1}
        )
        bge_client._client.post = AsyncMock(return_value=mock_resp)
        with patch("telegram_bot.services.bge_m3_client.get_client", return_value=mock_lf):
            await bge_client.encode_colbert(["hello"])
        metadata_calls = [
            c for c in mock_lf.update_current_span.call_args_list if "metadata" in c.kwargs
        ]
        assert any(c.kwargs["metadata"].get("model") == BGE_M3_MODEL_NAME for c in metadata_calls)


class TestQdrantSpanRuntimeMetadata:
    """Runtime tests for Qdrant retrieval span metadata."""

    @pytest.fixture
    def mock_lf(self):
        mock = MagicMock()
        mock.update_current_span = MagicMock()
        return mock

    @pytest.fixture
    def qdrant_service(self):
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            svc = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
                quantization_mode="scalar",
            )
            svc._client = AsyncMock()
            svc._collection_validated = True
            return svc

    def _assert_collection_metadata(self, mock_lf, collection_name, quantization_mode):
        metadata_calls = [
            c for c in mock_lf.update_current_span.call_args_list if "metadata" in c.kwargs
        ]
        assert any(
            c.kwargs["metadata"].get("collection") == collection_name
            and c.kwargs["metadata"].get("quantization_mode") == quantization_mode
            for c in metadata_calls
        )

    async def test_hybrid_search_rrf_exposes_collection_metadata(self, mock_lf, qdrant_service):
        qdrant_service._client.query_points = AsyncMock(return_value=MagicMock(points=[]))
        with patch("telegram_bot.services.qdrant.get_client", return_value=mock_lf):
            await qdrant_service.hybrid_search_rrf(dense_vector=[0.1] * 1024)
        self._assert_collection_metadata(mock_lf, "test_collection_scalar", "scalar")

    async def test_hybrid_search_rrf_colbert_exposes_collection_metadata(
        self, mock_lf, qdrant_service
    ):
        qdrant_service._client.query_points = AsyncMock(return_value=MagicMock(points=[]))
        with patch("telegram_bot.services.qdrant.get_client", return_value=mock_lf):
            await qdrant_service.hybrid_search_rrf_colbert(
                dense_vector=[0.1] * 1024,
                colbert_query=[[0.1] * 1024],
            )
        self._assert_collection_metadata(mock_lf, "test_collection_scalar", "scalar")

    async def test_batch_search_rrf_exposes_collection_metadata(self, mock_lf, qdrant_service):
        qdrant_service._client.query_batch_points = AsyncMock(return_value=[])
        with patch("telegram_bot.services.qdrant.get_client", return_value=mock_lf):
            await qdrant_service.batch_search_rrf(queries=[{"dense_vector": [0.1] * 1024}])
        self._assert_collection_metadata(mock_lf, "test_collection_scalar", "scalar")

    async def test_search_with_score_boosting_exposes_collection_metadata(
        self, mock_lf, qdrant_service
    ):
        qdrant_service._client.query_points = AsyncMock(return_value=MagicMock(points=[]))
        with patch("telegram_bot.services.qdrant.get_client", return_value=mock_lf):
            await qdrant_service.search_with_score_boosting(dense_vector=[0.1] * 1024)
        self._assert_collection_metadata(mock_lf, "test_collection_scalar", "scalar")

    def test_mmr_rerank_exposes_collection_metadata(self, mock_lf, qdrant_service):
        with patch("telegram_bot.services.qdrant.get_client", return_value=mock_lf):
            qdrant_service.mmr_rerank(
                points=[{"id": "1", "score": 0.9, "text": "a", "metadata": {}}],
                embeddings=[[0.1] * 1024],
            )
        self._assert_collection_metadata(mock_lf, "test_collection_scalar", "scalar")
