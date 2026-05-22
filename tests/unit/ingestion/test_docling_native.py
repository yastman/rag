"""Tests for feature-flagged native Docling ingestion adapter."""

from __future__ import annotations

import sys
import types
from pathlib import Path


def test_native_docling_adapter_preserves_ingestion_contract(tmp_path: Path) -> None:
    from src.ingestion.docling_native import NativeDoclingAdapter

    class _FakeDocument:
        def export_to_markdown(self) -> str:
            return "# Overview\n\nIntro block.\n\n## Details\n\nSecond block.\n"

    class _FakeResult:
        document = _FakeDocument()

    class _FakeConverter:
        def convert(self, source: str | Path) -> _FakeResult:
            assert Path(source).name == "sample.md"
            return _FakeResult()

    file_path = tmp_path / "sample.md"
    file_path.write_text("# Placeholder\n", encoding="utf-8")

    adapter = NativeDoclingAdapter(max_tokens=80, converter=_FakeConverter())
    docling_chunks = adapter.chunk_file_sync(file_path)
    ingestion_chunks = adapter.to_ingestion_chunks(
        docling_chunks,
        source="docs/sample.md",
        source_type="md",
    )

    assert len(docling_chunks) == 2
    assert docling_chunks[0].headings == ["Overview"]
    assert docling_chunks[1].headings == ["Details"]

    first_meta = ingestion_chunks[0].extra_metadata or {}
    second_meta = ingestion_chunks[1].extra_metadata or {}
    assert first_meta["source"] == "docs/sample.md"
    assert first_meta["source_type"] == "md"
    assert first_meta["chunk_order"] == 0
    assert first_meta["section"] == "Overview"
    assert second_meta["chunk_order"] == 1
    assert second_meta["section"] == "Details"
    assert "docling_meta" in first_meta


def test_unified_config_selects_docling_backend(monkeypatch) -> None:
    from src.ingestion.unified.config import UnifiedConfig

    cocoindex = types.ModuleType("cocoindex")
    cocoindex_op = types.ModuleType("cocoindex.op")

    class _FakeTargetSpec:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def _target_connector(**_: object):
        def decorator(cls):
            return cls

        return decorator

    cocoindex_op.TargetSpec = _FakeTargetSpec
    cocoindex_op.target_connector = _target_connector
    monkeypatch.setitem(sys.modules, "cocoindex", cocoindex)
    monkeypatch.setitem(sys.modules, "cocoindex.op", cocoindex_op)

    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    monkeypatch.setenv("DOCLING_BACKEND", "docling_native")
    config = UnifiedConfig()
    spec = QdrantHybridTargetSpec.from_config(config)

    QdrantHybridTargetConnector._docling = None
    adapter = QdrantHybridTargetConnector._get_docling(spec)

    assert config.docling_backend == "docling_native"
    assert spec.docling_backend == "docling_native"
    assert adapter.__class__.__name__ == "NativeDoclingAdapter"
