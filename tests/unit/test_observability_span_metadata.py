"""Static tests for observability span metadata.

AST-based tests for @observe decorator metadata (as_type, capture_input, capture_output)
on BGE-M3, Qdrant, and RAG pipeline spans. No runtime SDK calls or network I/O.
"""

import ast
from pathlib import Path

import pytest


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
