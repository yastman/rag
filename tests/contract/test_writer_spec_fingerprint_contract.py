# tests/contract/test_writer_spec_fingerprint_contract.py
"""Contract: QdrantHybridTargetConnector must not reuse a cached writer when
the effective target spec changes.

Closes #1605.

Audit finding:
  ``QdrantHybridTargetConnector._get_writer()`` checked only ``cls._writer is None``.
  A process calling _get_writer() with two different specs (e.g. first
  ``use_local_embeddings=True``, then ``use_local_embeddings=False``) would
  silently keep the first writer's client/config, producing stale ingestion
  behaviour.

  The docling cache already did this correctly via a ``(backend, url, timeout,
  max_tokens)`` cache-key tuple + ``_docling_key`` comparison. This contract
  requires the same pattern for the writer.

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
    REPO_ROOT
    / "src"
    / "ingestion"
    / "unified"
    / "targets"
    / "qdrant_hybrid_target.py"
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
                    targets = (
                        item.targets if isinstance(item, ast.Assign) else [item.target]
                    )
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
    assert "_writer_key" in src, (
        "_get_writer must use a _writer_key fingerprint comparison."
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


def _make_spec(*, use_local_embeddings: bool = True, voyage_model: str = "voyage-3"):
    """Create a minimal QdrantHybridTargetSpec for testing."""
    pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetSpec,
    )
    return QdrantHybridTargetSpec(
        collection_name="test_collection",
        qdrant_url="http://localhost:6333",
        use_local_embeddings=use_local_embeddings,
        voyage_model=voyage_model,
        bge_m3_url="http://localhost:8000",
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
    spec = _make_spec(use_local_embeddings=True)

    writer_a = MagicMock(name="writer_a")
    writer_b = MagicMock(name="writer_b")

    result1 = _call_get_writer(spec, writer_a)
    result2 = _call_get_writer(spec, writer_b)  # writer_b should NOT be constructed

    assert result1 is result2, (
        "Same spec must return cached writer (writer_b should not be constructed)."
    )
    assert result1 is writer_a


@requires_cocoindex
def test_different_embedding_mode_produces_new_writer() -> None:
    """Calling _get_writer with a spec that differs only in
    ``use_local_embeddings`` must produce a fresh writer instance."""
    spec_local = _make_spec(use_local_embeddings=True)
    spec_voyage = _make_spec(use_local_embeddings=False)

    writer_local = MagicMock(name="writer_local")
    writer_voyage = MagicMock(name="writer_voyage")

    result_local = _call_get_writer(spec_local, writer_local)
    result_voyage = _call_get_writer(spec_voyage, writer_voyage)

    assert result_local is writer_local
    assert result_voyage is writer_voyage
    assert result_local is not result_voyage, (
        "_get_writer must not reuse a cached writer when use_local_embeddings changes."
    )


@requires_cocoindex
def test_different_voyage_model_produces_new_writer() -> None:
    """Calling _get_writer with a different ``voyage_model`` must produce a
    fresh writer instance."""
    spec_v3 = _make_spec(use_local_embeddings=False, voyage_model="voyage-3")
    spec_v3_lite = _make_spec(use_local_embeddings=False, voyage_model="voyage-3-lite")

    writer_v3 = MagicMock(name="writer_v3")
    writer_v3_lite = MagicMock(name="writer_v3_lite")

    result_v3 = _call_get_writer(spec_v3, writer_v3)
    result_lite = _call_get_writer(spec_v3_lite, writer_v3_lite)

    assert result_v3 is writer_v3
    assert result_lite is writer_v3_lite
    assert result_v3 is not result_lite, (
        "_get_writer must not reuse a cached writer when voyage_model changes."
    )


@requires_cocoindex
def test_env_voyage_api_key_change_produces_new_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    """When spec omits voyage_api_key, the cache key must include the env fallback.

    QdrantHybridWriter receives ``spec.voyage_api_key or os.getenv("VOYAGE_API_KEY", "")``.
    The fingerprint must use that same effective value, otherwise a process that
    changes the env key between runs can silently reuse the old Voyage client.
    """
    spec = _make_spec(use_local_embeddings=False)

    writer_old_key = MagicMock(name="writer_old_key")
    writer_new_key = MagicMock(name="writer_new_key")

    monkeypatch.setenv("VOYAGE_API_KEY", "old-key")
    result_old = _call_get_writer(spec, writer_old_key)

    monkeypatch.setenv("VOYAGE_API_KEY", "new-key")
    result_new = _call_get_writer(spec, writer_new_key)

    assert result_old is writer_old_key
    assert result_new is writer_new_key
    assert result_old is not result_new, (
        "_get_writer must not reuse a cached writer when the effective "
        "VOYAGE_API_KEY fallback changes."
    )
