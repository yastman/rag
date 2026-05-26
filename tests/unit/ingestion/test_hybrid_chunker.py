"""Unit tests for the public HybridChunker adapter (#1235).

The legacy ``DocumentChunker`` (FIXED_SIZE / SLIDING_WINDOW / SEMANTIC) is
self-deprecated. Issue #1235 directs production code to migrate to
``docling_core.transforms.chunker.HybridChunker``.

This PR introduces a tested public adapter so follow-up call-site
migrations (cocoindex_flow, core/pipeline) are mechanical:

* ``make_hybrid_chunker`` — thin factory that lazily imports
  ``HybridChunker`` and surfaces a clear ImportError when the optional
  ``ingest`` extra is not installed.
* ``chunks_to_chunk_objects`` — converts ``HybridChunker.chunk(doc)`` output
  into the legacy ``src.ingestion.chunker.Chunk`` dataclass so existing
  consumers (indexer, contextual loader) keep working.

Verified shape via Context7 (``/docling-project/docling-core``):
``HybridChunker(max_tokens=, merge_peers=, tokenizer=)``; ``chunk(doc)``
returns chunks exposing a ``text`` attribute.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# make_hybrid_chunker
# ---------------------------------------------------------------------------


def test_make_hybrid_chunker_returns_configured_instance():
    """Forwards max_tokens / merge_peers to the underlying HybridChunker."""
    from src.ingestion import hybrid_chunker as mod

    fake_cls = MagicMock()
    fake_cls.return_value = MagicMock(name="hybrid")

    with patch.object(mod, "_load_hybrid_chunker_cls", return_value=fake_cls):
        instance = mod.make_hybrid_chunker(max_tokens=256, merge_peers=False)

    fake_cls.assert_called_once_with(max_tokens=256, merge_peers=False)
    assert instance is fake_cls.return_value


def test_make_hybrid_chunker_forwards_tokenizer_when_provided():
    from src.ingestion import hybrid_chunker as mod

    fake_cls = MagicMock()
    sentinel_tokenizer = object()

    with patch.object(mod, "_load_hybrid_chunker_cls", return_value=fake_cls):
        mod.make_hybrid_chunker(tokenizer=sentinel_tokenizer)

    call_kwargs = fake_cls.call_args.kwargs
    assert call_kwargs.get("tokenizer") is sentinel_tokenizer


def test_make_hybrid_chunker_omits_tokenizer_kwarg_when_none():
    """When tokenizer is None, the SDK falls back to its own default — we
    must not pass ``tokenizer=None`` because that would override the SDK's
    default factory with a literal None."""
    from src.ingestion import hybrid_chunker as mod

    fake_cls = MagicMock()

    with patch.object(mod, "_load_hybrid_chunker_cls", return_value=fake_cls):
        mod.make_hybrid_chunker()

    assert "tokenizer" not in fake_cls.call_args.kwargs


def test_make_hybrid_chunker_raises_clear_import_error_when_unavailable():
    from src.ingestion import hybrid_chunker as mod

    with patch.object(mod, "_load_hybrid_chunker_cls", return_value=None):
        with pytest.raises(ImportError) as ei:
            mod.make_hybrid_chunker()

    msg = str(ei.value)
    assert "HybridChunker" in msg
    assert "ingest" in msg, "Error message must point operators at the optional extra."


def test_make_hybrid_chunker_uses_documented_defaults():
    """Defaults match the project chunking contract (max_tokens=1024, merge_peers=True)."""
    from src.ingestion import hybrid_chunker as mod

    fake_cls = MagicMock()
    with patch.object(mod, "_load_hybrid_chunker_cls", return_value=fake_cls):
        mod.make_hybrid_chunker()

    kwargs = fake_cls.call_args.kwargs
    assert kwargs.get("max_tokens") == 1024
    assert kwargs.get("merge_peers") is True


# ---------------------------------------------------------------------------
# chunks_to_chunk_objects
# ---------------------------------------------------------------------------


def test_chunks_to_chunk_objects_handles_attribute_text():
    from src.ingestion.chunker import Chunk
    from src.ingestion.hybrid_chunker import chunks_to_chunk_objects

    raw = [
        SimpleNamespace(text="первый чанк"),
        SimpleNamespace(text="второй чанк"),
    ]
    out = chunks_to_chunk_objects(raw, document_name="doc.md", article_number="art-1")
    assert len(out) == 2
    assert all(isinstance(c, Chunk) for c in out)
    assert out[0].text == "первый чанк"
    assert out[0].document_name == "doc.md"
    assert out[0].article_number == "art-1"
    assert out[0].chunk_id == 0
    assert out[1].chunk_id == 1


def test_chunks_to_chunk_objects_handles_dict_text():
    from src.ingestion.hybrid_chunker import chunks_to_chunk_objects

    raw = [{"text": "dict chunk"}]
    out = chunks_to_chunk_objects(raw, document_name="d.md")
    assert len(out) == 1
    assert out[0].text == "dict chunk"


def test_chunks_to_chunk_objects_skips_empty_text():
    from src.ingestion.hybrid_chunker import chunks_to_chunk_objects

    raw = [
        SimpleNamespace(text="kept"),
        SimpleNamespace(text=""),
        SimpleNamespace(text=None),
        {"text": ""},
        SimpleNamespace(),  # no text attr
        SimpleNamespace(text="kept again"),
    ]
    out = chunks_to_chunk_objects(raw, document_name="d.md")
    assert [c.text for c in out] == ["kept", "kept again"]


def test_chunks_to_chunk_objects_preserves_order_indices():
    from src.ingestion.hybrid_chunker import chunks_to_chunk_objects

    raw = [SimpleNamespace(text=f"chunk-{i}") for i in range(5)]
    out = chunks_to_chunk_objects(raw, document_name="d.md")
    assert [c.chunk_id for c in out] == [0, 1, 2, 3, 4]
    assert [c.order for c in out] == [0, 1, 2, 3, 4]


def test_chunks_to_chunk_objects_returns_empty_for_empty_iter():
    from src.ingestion.hybrid_chunker import chunks_to_chunk_objects

    assert chunks_to_chunk_objects([], document_name="d.md") == []


def test_chunks_to_chunk_objects_default_article_number_is_empty_string():
    """The legacy Chunk dataclass requires article_number; the adapter must
    supply a stable default ('') so callers that do not track article numbers
    (markdown notes, generic web pages) still get a valid Chunk."""
    from src.ingestion.hybrid_chunker import chunks_to_chunk_objects

    out = chunks_to_chunk_objects([SimpleNamespace(text="x")], document_name="d.md")
    assert out[0].article_number == ""


# ---------------------------------------------------------------------------
# Integration: full round-trip with real HybridChunker on a tiny document
# ---------------------------------------------------------------------------


def test_round_trip_with_real_hybrid_chunker_on_tiny_doc():
    """Smoke test against the actual HybridChunker, when ingest extra is installed.

    Confirms the adapter accepts the SDK's chunk objects unchanged and
    produces non-empty Chunk dataclasses.
    """
    pytest.importorskip("docling_core")
    from docling_core.types.doc import DocItemLabel, DoclingDocument

    from src.ingestion.hybrid_chunker import (
        chunks_to_chunk_objects,
        make_hybrid_chunker,
    )

    doc = DoclingDocument(name="ingest-1235-test")
    doc.add_title(text="Title")
    doc.add_heading(text="Section A", level=1)
    doc.add_text(label=DocItemLabel.PARAGRAPH, text="Lorem ipsum dolor sit amet. " * 8)

    chunker = make_hybrid_chunker(max_tokens=64, merge_peers=True)
    raw_chunks = list(chunker.chunk(doc))
    assert raw_chunks, "HybridChunker must emit at least one chunk for non-empty doc"

    out = chunks_to_chunk_objects(raw_chunks, document_name="ingest-1235-test", article_number="t")
    assert out, "Adapter must yield at least one Chunk for a non-empty input"
    for c in out:
        assert c.text.strip()
        assert c.document_name == "ingest-1235-test"
        assert c.article_number == "t"
