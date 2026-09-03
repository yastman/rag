"""Tests for the Markdown-only ingestion parser (#3235).

The parser replaced the Docling ``NativeDoclingAdapter``: production
ingestion accepts exactly ``.md`` files and must chunk them deterministically
with the stdlib only. These tests pin the split contract, the error paths,
and the generic ``Chunk`` metadata conversion consumed by
``QdrantHybridWriter``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.ingestion.markdown import (
    SUPPORTED_MARKDOWN_SUFFIXES,
    MarkdownParser,
    generate_doc_id,
)


# ---------------------------------------------------------------------------
# 1. File-level contract — suffix gate and reads
# ---------------------------------------------------------------------------


def test_supported_suffixes_are_markdown_only() -> None:
    """Production ingestion is Markdown-only; no converter formats remain."""
    assert {".md"} == SUPPORTED_MARKDOWN_SUFFIXES
    assert {".md"} == MarkdownParser.SUPPORTED_SUFFIXES


def test_parser_rejects_non_markdown_suffix(tmp_path: Path) -> None:
    """Non-Markdown input is rejected before any content is read."""
    pdf_like = tmp_path / "not_a_real.pdf"
    pdf_like.write_bytes(b"%PDF-1.7 fake")
    txt = tmp_path / "notes.txt"
    txt.write_text("plain text", encoding="utf-8")

    parser = MarkdownParser()
    for path in (pdf_like, txt):
        with pytest.raises(ValueError, match="Markdown-only"):
            parser.chunk_file_sync(path)


def test_parser_raises_on_missing_file(tmp_path: Path) -> None:
    parser = MarkdownParser()
    with pytest.raises(FileNotFoundError):
        parser.chunk_file_sync(tmp_path / "does_not_exist.md")


def test_parser_reads_utf8_strict(tmp_path: Path) -> None:
    """UTF-8 is read strictly; invalid bytes fail loudly, not silently."""
    doc = tmp_path / "doc.md"
    doc.write_bytes(b"# ok\n\n\xed\xa0\x80 surrogate")

    with pytest.raises(UnicodeDecodeError):
        MarkdownParser().chunk_file_sync(doc)


# ---------------------------------------------------------------------------
# 2. Deterministic splitting contract
# ---------------------------------------------------------------------------


def test_headings_split_sections_with_hierarchical_stack(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(
        "# Overview\n\nIntro text.\n\n## Details\n\nDetail text.\n\n### Deep\n\nDeep text.\n",
        encoding="utf-8",
    )
    chunks = MarkdownParser().chunk_file_sync(doc)

    assert [c.headings for c in chunks] == [
        ["Overview"],
        ["Overview", "Details"],
        ["Overview", "Details", "Deep"],
    ]
    assert [c.seq_no for c in chunks] == [0, 1, 2]
    assert "Intro text." in chunks[0].text
    assert chunks[2].text == "Overview > Details > Deep\nDeep text."


def test_heading_context_is_prepended_like_old_contextualize(tmp_path: Path) -> None:
    """Chunk text carries the 'H1 > H2' context line (HybridChunker parity)."""
    doc = tmp_path / "doc.md"
    doc.write_text("# Guide\n\nBody paragraph.\n", encoding="utf-8")

    chunks = MarkdownParser().chunk_file_sync(doc)

    assert chunks[0].text == "Guide\nBody paragraph."


def test_preamble_before_first_heading_gets_no_headings(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("Preamble text.\n\n# After\n\nBody.\n", encoding="utf-8")

    chunks = MarkdownParser().chunk_file_sync(doc)

    assert chunks[0].headings == []
    assert "Preamble text." in chunks[0].text
    assert chunks[1].headings == ["After"]


def test_headings_inside_code_fences_do_not_split(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(
        "# Section\n\n```bash\n# this is a comment, not a heading\nrun.sh\n```\n\nStill same section.\n",
        encoding="utf-8",
    )
    chunks = MarkdownParser().chunk_file_sync(doc)

    assert len(chunks) == 1
    assert chunks[0].headings == ["Section"]
    assert "# this is a comment, not a heading" in chunks[0].text


def test_empty_sections_are_dropped(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("# Empty\n\n## Also empty\n\n# Real\n\ncontent\n", encoding="utf-8")

    chunks = MarkdownParser().chunk_file_sync(doc)

    assert len(chunks) == 1
    assert chunks[0].headings == ["Real"]


def test_oversized_sections_split_deterministically(tmp_path: Path) -> None:
    """Same input → same chunk sequence; every piece respects the budget."""
    paragraph = "word " * 40  # 200 chars
    body = "\n\n".join([paragraph] * 12)  # ~2400 chars
    doc = tmp_path / "doc.md"
    doc.write_text(f"# Big\n\n{body}\n", encoding="utf-8")

    parser = MarkdownParser(max_tokens=128)  # 512 chars budget
    first = parser.chunk_file_sync(doc)
    second = MarkdownParser(max_tokens=128).chunk_file_sync(doc)

    assert [c.text for c in first] == [c.text for c in second]
    assert len(first) >= 4
    context_allowance = len("Big\n")
    for chunk in first:
        assert len(chunk.text) <= 128 * 4 + context_allowance
        assert chunk.headings == ["Big"]
    assert [c.seq_no for c in first] == list(range(len(first)))


def test_oversized_single_paragraph_hard_splits_without_loss(tmp_path: Path) -> None:
    """A paragraph with no blank lines is hard-cut, keeping all content."""
    body = "abcdefgh" * 300  # 2400 chars, single line
    doc = tmp_path / "doc.md"
    doc.write_text(f"# Wall\n\n{body}\n", encoding="utf-8")

    chunks = MarkdownParser(max_tokens=128).chunk_file_sync(doc)

    joined = "".join(c.text.split("\n", 1)[1] if "\n" in c.text else c.text for c in chunks)
    assert joined == body
    assert len(chunks) > 1


def test_chunking_is_repeatable_across_runs(tmp_path: Path) -> None:
    """Identical files (different paths) produce identical chunk texts."""
    content = "# A\n\none\n\n## B\n\ntwo\n\n# C\n\nthree\n"
    first = MarkdownParser().chunk_file_sync(_write(tmp_path / "a.md", content))
    second = MarkdownParser().chunk_file_sync(_write(tmp_path / "b.md", content))

    assert [c.text for c in first] == [c.text for c in second]


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 3. Generic Chunk conversion — payload/id compatibility
# ---------------------------------------------------------------------------


def test_to_ingestion_chunks_preserves_generic_contract(tmp_path: Path) -> None:
    doc = _write(tmp_path / "doc.md", "# Overview\n\nIntro.\n\n## Details\n\nMore.\n")
    parser = MarkdownParser()
    parsed = parser.chunk_file_sync(doc)
    chunks = parser.to_ingestion_chunks(parsed, source="docs/doc.md", source_type="md")

    assert len(chunks) == 2
    first_meta = chunks[0].extra_metadata or {}
    assert first_meta["source"] == "docs/doc.md"
    assert first_meta["source_type"] == "md"
    assert first_meta["chunk_order"] == 0
    assert first_meta["section"] == "Overview"
    assert first_meta["parser"] == "markdown"
    assert chunks[1].extra_metadata["chunk_order"] == 1
    assert chunks[1].section == "Overview > Details"


def test_doc_id_is_deterministic_sha256_prefix(tmp_path: Path) -> None:
    doc = _write(tmp_path / "doc.md", "# x\n\ny\n")
    parser = MarkdownParser()
    parsed = parser.chunk_file_sync(doc)

    source = "docs/fixed.md"
    chunks_a = parser.to_ingestion_chunks(parsed, source=source, source_type="md")
    chunks_b = parser.to_ingestion_chunks(parsed, source=source, source_type="md")

    expected = hashlib.sha256(source.encode()).hexdigest()[:16]
    assert generate_doc_id(source) == expected
    assert chunks_a[0].article_number == expected
    assert (chunks_a[0].extra_metadata or {})["doc_id"] == expected
    assert (chunks_a[0].extra_metadata or {})["doc_id"] == (chunks_b[0].extra_metadata or {})[
        "doc_id"
    ]


def test_different_sources_yield_different_doc_ids(tmp_path: Path) -> None:
    doc = _write(tmp_path / "doc.md", "# x\n\ny\n")
    parser = MarkdownParser()
    parsed = parser.chunk_file_sync(doc)

    a = parser.to_ingestion_chunks(parsed, source="path/a.md", source_type="md")
    b = parser.to_ingestion_chunks(parsed, source="path/b.md", source_type="md")

    assert (a[0].extra_metadata or {})["doc_id"] != (b[0].extra_metadata or {})["doc_id"]


def test_chunk_order_supports_stable_point_locations(tmp_path: Path) -> None:
    """chunk_order in extra_metadata keeps QdrantHybridWriter point ids stable."""
    doc = _write(tmp_path / "doc.md", "# A\n\none\n\n# B\n\ntwo\n")
    parser = MarkdownParser()
    chunks = parser.to_ingestion_chunks(parser.chunk_file_sync(doc), source="d.md")

    assert [c.extra_metadata["chunk_order"] for c in chunks] == [0, 1]
    assert [c.order for c in chunks] == [0, 1]
    assert all(c.page_range is None for c in chunks)
