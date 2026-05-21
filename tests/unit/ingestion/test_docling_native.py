"""Tests for feature-flagged native Docling ingestion adapter."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch


def test_native_docling_adapter_preserves_ingestion_contract(tmp_path: Path) -> None:
    from src.ingestion.docling_native import NativeDoclingAdapter

    class _FakeProv:
        def __init__(self, page_no: int) -> None:
            self.page_no = page_no

    class _FakeDocItem:
        def __init__(self, page_no: int) -> None:
            self.prov = [_FakeProv(page_no)]

    class _FakeMeta:
        def __init__(self, headings: list[str], doc_items: list[_FakeDocItem]) -> None:
            self.headings = headings
            self.doc_items = doc_items

    class _FakeChunk:
        def __init__(self, text: str, headings: list[str], page_no: int) -> None:
            self.text = text
            self.meta = _FakeMeta(headings=headings, doc_items=[_FakeDocItem(page_no)])

    class _FakeDocument:
        """Stub DoclingDocument for HybridChunker."""

    class _FakeResult:
        document = _FakeDocument()

    class _FakeConverter:
        def convert(self, source: str | Path) -> _FakeResult:
            assert Path(source).name == "sample.md"
            return _FakeResult()

    fake_chunks = [
        _FakeChunk(text="Intro block.", headings=["Overview"], page_no=1),
        _FakeChunk(text="Second block.", headings=["Details"], page_no=2),
    ]

    class _FakeChunker:
        def __init__(self, **kwargs: object) -> None:
            self._kwargs = kwargs

        def chunk(self, doc: object) -> list[_FakeChunk]:
            return fake_chunks

    file_path = tmp_path / "sample.md"
    file_path.write_text("# Placeholder\n", encoding="utf-8")

    with patch("src.ingestion.docling_native.RuntimeHybridChunker", _FakeChunker):
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
    assert docling_chunks[0].page_range == (1, 1)
    assert docling_chunks[1].page_range == (2, 2)

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
