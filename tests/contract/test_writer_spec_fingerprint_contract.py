# tests/contract/test_writer_spec_fingerprint_contract.py
"""Contract: QdrantHybridTargetConnector must not reuse a cached writer when
the effective target spec changes.

Closes #1605. Updated for #2631 (Voyage removed; BGE-M3 is the sole path).

Tests are split into two sections:
- Static (AST-only): always run, no cocoindex needed.
- Behavioural: skip when cocoindex is not installed (ingest extra).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_MODULE_PATH = (
    REPO_ROOT / "src" / "ingestion" / "unified" / "targets" / "qdrant_hybrid_target.py"
)


# ---------------------------------------------------------------------------
# Static contract: source-code shape
# ---------------------------------------------------------------------------


def _read_src() -> str:
    return TARGET_MODULE_PATH.read_text(encoding="utf-8")


def test_writer_key_attribute_exists_in_class_body() -> None:
    """``QdrantHybridTargetConnector`` must declare a ``_writer_key`` class
    attribute so that key comparisons work across instances."""
    src = _read_src()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "QdrantHybridTargetConnector":
            for item in ast.walk(node):
                if isinstance(item, (ast.Assign, ast.AnnAssign)):
                    targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                    for t in targets:
                        if isinstance(t, ast.Name) and t.id == "_writer_key":
                            return
    pytest.fail(
        "QdrantHybridTargetConnector must declare '_writer_key' class attribute "
        "(same pattern as _docling_key)."
    )


def test_get_writer_contains_key_comparison() -> None:
    """The ``_get_writer`` method must compare the spec fingerprint against
    ``_writer_key`` (not just check ``_writer is None``)."""
    src = _read_src()
    assert "_writer_key" in src, "_get_writer must use a _writer_key fingerprint comparison."


def test_no_voyage_fields_in_spec() -> None:
    """QdrantHybridTargetSpec must not contain voyage_api_key or voyage_model (#2631)."""
    src = _read_src()
    assert "voyage_api_key" not in src, (
        "voyage_api_key must be removed from QdrantHybridTargetSpec (#2631)"
    )
    assert "voyage_model" not in src, (
        "voyage_model must be removed from QdrantHybridTargetSpec (#2631)"
    )


# ---------------------------------------------------------------------------
# Behavioural contract: distinct specs produce distinct writers
# (requires cocoindex ingest extra)
# ---------------------------------------------------------------------------

requires_cocoindex = pytest.mark.skipif(
    importlib.util.find_spec("cocoindex") is None,
    reason="cocoindex not installed (ingest extra)",
)


@pytest.fixture(autouse=True)
def reset_connector_state():
    """Reset class-level state between tests."""
    try:
        from src.ingestion.unified.targets.qdrant_hybrid_target import (
            QdrantHybridTargetConnector,
        )
    except Exception:
        yield
        return
    original_writer = QdrantHybridTargetConnector._writer
    original_key = QdrantHybridTargetConnector._writer_key
    yield
    QdrantHybridTargetConnector._writer = original_writer
    QdrantHybridTargetConnector._writer_key = original_key


def _make_spec(*, bge_m3_url: str = "http://localhost:8000", bge_m3_concurrency: int = 1):
    """Create a minimal QdrantHybridTargetSpec for testing."""
    pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetSpec,
    )

    return QdrantHybridTargetSpec(
        collection_name="test_collection",
        qdrant_url="http://localhost:6333",
        bge_m3_url=bge_m3_url,
        bge_m3_concurrency=bge_m3_concurrency,
    )


def _call_get_writer(spec, writer_instance):
    """Call _get_writer with a mocked QdrantHybridWriter constructor."""
    pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
    )

    with patch(
        "src.ingestion.unified.targets.qdrant_hybrid_target.QdrantHybridWriter",
        return_value=writer_instance,
    ):
        return QdrantHybridTargetConnector._get_writer(spec)


@requires_cocoindex
def test_same_spec_returns_cached_writer() -> None:
    """Calling _get_writer twice with identical spec must return the same
    writer instance (cache hit)."""
    spec = _make_spec()

    writer_a = MagicMock(name="writer_a")
    writer_b = MagicMock(name="writer_b")

    result1 = _call_get_writer(spec, writer_a)
    result2 = _call_get_writer(spec, writer_b)  # writer_b should NOT be constructed

    assert result1 is result2, (
        "Same spec must return cached writer (writer_b should not be constructed)."
    )
    assert result1 is writer_a


@requires_cocoindex
def test_different_bge_m3_url_produces_new_writer() -> None:
    """Calling _get_writer with a different bge_m3_url must produce a fresh writer."""
    spec_a = _make_spec(bge_m3_url="http://localhost:8000")
    spec_b = _make_spec(bge_m3_url="http://bge-m3-alt:8000")

    writer_a = MagicMock(name="writer_a")
    writer_b = MagicMock(name="writer_b")

    result_a = _call_get_writer(spec_a, writer_a)
    result_b = _call_get_writer(spec_b, writer_b)

    assert result_a is writer_a
    assert result_b is writer_b
    assert result_a is not result_b, (
        "_get_writer must not reuse a cached writer when bge_m3_url changes."
    )


@requires_cocoindex
def test_different_concurrency_produces_new_writer() -> None:
    """Calling _get_writer with different bge_m3_concurrency must produce a fresh writer."""
    spec_1 = _make_spec(bge_m3_concurrency=1)
    spec_4 = _make_spec(bge_m3_concurrency=4)

    writer_1 = MagicMock(name="writer_1")
    writer_4 = MagicMock(name="writer_4")

    result_1 = _call_get_writer(spec_1, writer_1)
    result_4 = _call_get_writer(spec_4, writer_4)

    assert result_1 is writer_1
    assert result_4 is writer_4
    assert result_1 is not result_4, (
        "_get_writer must not reuse a cached writer when bge_m3_concurrency changes."
    )
