"""Tests for feature-flagged native Docling ingestion adapter (#1235 SDK migration).

The native path (``NativeDoclingAdapter``) used to chunk documents with a
naive ``_chunk_markdown`` + ``_split_text`` pair that segmented by markdown
headings and then split long sections by character count. Issue #1235 calls
out the deprecated character-based splitter directly.

The migration replaces that path with the SDK-native
``docling_core.transforms.chunker.HybridChunker``, which performs
tokenization-aware chunking on a ``DoclingDocument`` while preserving
hierarchical structure (headings).

Tests inject a fake chunker via the new constructor parameter so the unit
suite does not need a real tokenizer or model download.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.ingestion.docling_native import NativeDoclingAdapter


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


class _FakeDocument:
    """Stand-in for ``DoclingDocument`` — only needs to be passable to chunker."""


class _FakeResult:
    document = _FakeDocument()


class _FakeConverter:
    """Stand-in for ``docling.document_converter.DocumentConverter``."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def convert(self, source: Path) -> _FakeResult:
        self.calls.append(Path(source))
        return _FakeResult()


@dataclass
class _FakeChunkMeta:
    """Stand-in for ``HybridChunker`` chunk-meta with headings."""

    headings: list[str]


@dataclass
class _FakeChunk:
    """Stand-in for ``HybridChunker`` chunk output (chunk.text, chunk.meta.headings)."""

    text: str
    meta: _FakeChunkMeta


class _FakeChunker:
    """Records ``.chunk(doc)`` calls and returns canned chunks.

    Mirrors the public API of ``docling_core.transforms.chunker.HybridChunker``
    that ``NativeDoclingAdapter`` relies on: callable ``chunk(doc) -> iterable``
    where each chunk has ``.text`` and ``.meta.headings``.
    """

    def __init__(self, chunks: list[_FakeChunk]) -> None:
        self._chunks = chunks
        self.calls: list[Any] = []

    def chunk(self, doc: Any) -> list[_FakeChunk]:
        self.calls.append(doc)
        return list(self._chunks)


class _ContextualizingFakeChunker(_FakeChunker):
    """Fake chunker with the Docling contextualize API."""

    def __init__(self, chunks: list[_FakeChunk]) -> None:
        super().__init__(chunks)
        self.contextualize_calls: list[_FakeChunk] = []

    def contextualize(self, chunk: _FakeChunk) -> str:
        self.contextualize_calls.append(chunk)
        headings = " > ".join(chunk.meta.headings)
        return f"{headings}\n{chunk.text}" if headings else chunk.text


@pytest.fixture
def sample_md_path(tmp_path: Path) -> Path:
    file_path = tmp_path / "sample.md"
    file_path.write_text("# Placeholder\n", encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------------
# 1. Public chunking contract — adapter delegates to HybridChunker
# ---------------------------------------------------------------------------


def test_native_adapter_delegates_chunking_to_injected_chunker(
    sample_md_path: Path,
) -> None:
    """``chunk_file_sync`` must call the injected chunker on the converted document."""
    converter = _FakeConverter()
    chunker = _FakeChunker(
        [
            _FakeChunk(text="Intro block.", meta=_FakeChunkMeta(headings=["Overview"])),
            _FakeChunk(text="Second block.", meta=_FakeChunkMeta(headings=["Details"])),
        ]
    )

    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)
    chunks = adapter.chunk_file_sync(sample_md_path)

    # Adapter actually invoked the chunker on the converted document.
    assert len(chunker.calls) == 1, "HybridChunker.chunk() must be called exactly once per file"

    # Output is the canned chunks, normalized into DoclingChunk dataclass.
    assert len(chunks) == 2
    assert chunks[0].text == "Intro block."
    assert chunks[1].text == "Second block."


def test_native_adapter_preserves_headings_from_chunk_meta(
    sample_md_path: Path,
) -> None:
    """Heading metadata must round-trip from HybridChunker chunk.meta.headings into DoclingChunk."""
    converter = _FakeConverter()
    chunker = _FakeChunker(
        [
            _FakeChunk(text="Intro block.", meta=_FakeChunkMeta(headings=["Overview"])),
            _FakeChunk(
                text="Detail block.",
                meta=_FakeChunkMeta(headings=["Overview", "Details"]),
            ),
        ]
    )

    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)
    chunks = adapter.chunk_file_sync(sample_md_path)

    assert chunks[0].headings == ["Overview"]
    assert chunks[1].headings == ["Overview", "Details"]


def test_native_adapter_contextualize_true_uses_chunker_contextualize(
    sample_md_path: Path,
) -> None:
    """Default text path must use Docling contextualization for embedding text."""
    converter = _FakeConverter()
    raw_chunk = _FakeChunk(text="Intro block.", meta=_FakeChunkMeta(headings=["Overview"]))
    chunker = _ContextualizingFakeChunker([raw_chunk])

    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)
    chunks = adapter.chunk_file_sync(sample_md_path, contextualize=True)

    assert chunker.contextualize_calls == [raw_chunk]
    assert chunks[0].text == "Overview\nIntro block."
    assert chunks[0].headings == ["Overview"]
    assert chunks[0].metadata == {"parser": "docling_native"}


def test_native_adapter_contextualize_false_preserves_raw_text(
    sample_md_path: Path,
) -> None:
    """Raw-text path must bypass chunker contextualization."""
    converter = _FakeConverter()
    raw_chunk = _FakeChunk(text="Intro block.", meta=_FakeChunkMeta(headings=["Overview"]))
    chunker = _ContextualizingFakeChunker([raw_chunk])

    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)
    chunks = adapter.chunk_file_sync(sample_md_path, contextualize=False)

    assert chunker.contextualize_calls == []
    assert chunks[0].text == "Intro block."
    assert chunks[0].headings == ["Overview"]


def test_native_adapter_assigns_sequential_seq_numbers(
    sample_md_path: Path,
) -> None:
    """seq_no must be 0-indexed monotonic so downstream ordering stays stable."""
    converter = _FakeConverter()
    chunker = _FakeChunker(
        [_FakeChunk(text=f"Block {i}.", meta=_FakeChunkMeta(headings=[])) for i in range(3)]
    )

    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)
    chunks = adapter.chunk_file_sync(sample_md_path)

    assert [c.seq_no for c in chunks] == [0, 1, 2]


def test_native_adapter_skips_empty_chunks(sample_md_path: Path) -> None:
    """Whitespace-only chunks emitted by HybridChunker are dropped (defensive)."""
    converter = _FakeConverter()
    chunker = _FakeChunker(
        [
            _FakeChunk(text="real text", meta=_FakeChunkMeta(headings=[])),
            _FakeChunk(text="   ", meta=_FakeChunkMeta(headings=[])),
            _FakeChunk(text="", meta=_FakeChunkMeta(headings=[])),
            _FakeChunk(text="more real text", meta=_FakeChunkMeta(headings=[])),
        ]
    )

    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)
    chunks = adapter.chunk_file_sync(sample_md_path)

    assert len(chunks) == 2
    assert [c.text for c in chunks] == ["real text", "more real text"]


# ---------------------------------------------------------------------------
# 2. Deprecated naive splitter must be gone
# ---------------------------------------------------------------------------


def test_native_adapter_does_not_expose_deprecated_split_text() -> None:
    """``_split_text`` was the deprecated character-count splitter (#1235); it must be gone."""
    assert not hasattr(NativeDoclingAdapter, "_split_text"), (
        "NativeDoclingAdapter._split_text was the deprecated character-based "
        "splitter called out in issue #1235. The HybridChunker migration replaces "
        "it with tokenization-aware chunking; the helper must not come back."
    )


def test_native_adapter_does_not_expose_naive_chunk_markdown() -> None:
    """``_chunk_markdown`` was the markdown-heading segmenter; it must be gone too."""
    assert not hasattr(NativeDoclingAdapter, "_chunk_markdown"), (
        "NativeDoclingAdapter._chunk_markdown segmented by raw markdown headings "
        "and then called the deprecated _split_text. HybridChunker handles both "
        "structural and tokenization concerns; the helper must not come back."
    )


# ---------------------------------------------------------------------------
# 3. End-to-end ingestion contract preserved (Chunk objects round-trip metadata)
# ---------------------------------------------------------------------------


def test_native_docling_adapter_preserves_ingestion_contract(
    sample_md_path: Path,
) -> None:
    """The adapter still produces DoclingChunk → Chunk with the documented metadata shape."""
    converter = _FakeConverter()
    chunker = _FakeChunker(
        [
            _FakeChunk(text="Intro block.", meta=_FakeChunkMeta(headings=["Overview"])),
            _FakeChunk(text="Second block.", meta=_FakeChunkMeta(headings=["Details"])),
        ]
    )

    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)
    docling_chunks = adapter.chunk_file_sync(sample_md_path)
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


# ---------------------------------------------------------------------------
# 4. Error-path contracts preserved
# ---------------------------------------------------------------------------


def test_native_adapter_raises_on_missing_file(tmp_path: Path) -> None:
    converter = _FakeConverter()
    chunker = _FakeChunker([])
    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)

    missing = tmp_path / "does_not_exist.md"
    with pytest.raises(FileNotFoundError):
        adapter.chunk_file_sync(missing)


def test_native_adapter_raises_on_unsupported_format(tmp_path: Path) -> None:
    converter = _FakeConverter()
    chunker = _FakeChunker([])
    adapter = NativeDoclingAdapter(max_tokens=80, converter=converter, chunker=chunker)

    weird = tmp_path / "not_supported.xyz"
    weird.write_text("hi", encoding="utf-8")
    with pytest.raises(ValueError):
        adapter.chunk_file_sync(weird)


# ---------------------------------------------------------------------------
# 5. Existing unified-config selection contract (kept verbatim)
# ---------------------------------------------------------------------------


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
