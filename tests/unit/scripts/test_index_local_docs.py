"""Regression tests for scripts/index_local_docs.py review fixes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from qdrant_client.models import PayloadSchemaType, PointStruct


def _chunk(*, text: str = "hello", doc_id: str = "doc.md", chunk_index: int = 0) -> dict:
    return {
        "id": f"{doc_id}::{chunk_index}",
        "text": text,
        "heading": "Heading",
        "source_file": doc_id,
        "doc_id": doc_id,
        "chunk_index": chunk_index,
    }


def _collection_info(*, vectors: dict | None = None, sparse_vectors: dict | None = None):
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=vectors
                if vectors is not None
                else {"dense": object(), "colbert": object()},
                sparse_vectors=sparse_vectors if sparse_vectors is not None else {"bm42": object()},
            )
        )
    )


def test_preflight_check_exits_when_required_vectors_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import index_local_docs as subject

    client = mock.MagicMock()
    client.collection_exists.return_value = True
    client.get_collection.return_value = _collection_info(
        vectors={"dense": object()}, sparse_vectors={}
    )

    with pytest.raises(SystemExit) as exc_info:
        subject.preflight_check(client, "local_docs")

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "missing vectors" in out
    assert "colbert" in out
    assert "bm42" in out


def test_upsert_points_rejects_missing_or_misaligned_embeddings() -> None:
    from scripts import index_local_docs as subject

    client = mock.MagicMock()
    chunks = [_chunk()]

    with pytest.raises(ValueError, match="Embedding count mismatch"):
        subject.upsert_points(
            client,
            "local_docs",
            chunks,
            {"dense": [[0.1, 0.2]], "sparse": [{"indices": [1], "values": [0.5]}], "colbert": None},
        )


def test_upsert_points_uses_upload_points_with_retry() -> None:
    from scripts import index_local_docs as subject

    client = mock.MagicMock()
    chunks = [_chunk()]
    embeddings = {
        "dense": [[0.1, 0.2]],
        "sparse": [{"indices": [1], "values": [0.5]}],
        "colbert": [[[0.9, 0.8]]],
    }

    count = subject.upsert_points(client, "local_docs", chunks, embeddings)

    assert count == 1
    client.upload_points.assert_called_once()
    kwargs = client.upload_points.call_args.kwargs
    assert kwargs["collection_name"] == "local_docs"
    assert kwargs["batch_size"] == 1
    assert kwargs["max_retries"] == 3
    assert kwargs["wait"] is True
    points = list(kwargs["points"])
    assert len(points) == 1
    assert isinstance(points[0], PointStruct)
    client.upsert.assert_not_called()


# --- _heading_level ---


class TestHeadingLevel:
    def test_heading_levels_1_2_3(self) -> None:
        from scripts.index_local_docs import _heading_level

        assert _heading_level("# Title") == 1
        assert _heading_level("## Section") == 2
        assert _heading_level("### Sub") == 3

    def test_non_heading_returns_none(self) -> None:
        from scripts.index_local_docs import _heading_level

        assert _heading_level("Normal text") is None
        assert _heading_level("") is None
        assert _heading_level("####No space") is None
        assert _heading_level("  ## indented") is None


# --- chunk_markdown ---


class TestChunkMarkdown:
    def test_chunk_splits_by_h2_headings(self) -> None:
        from scripts.index_local_docs import chunk_markdown

        text = "## Alpha\nContent A\n## Beta\nContent B"
        chunks = chunk_markdown(text, "test.md")
        headings = [c["heading"] for c in chunks]
        assert "Alpha" in headings
        assert "Beta" in headings
        assert len(chunks) == 2

    def test_chunk_merges_small_sections(self) -> None:
        """Sections smaller than MAX_CHUNK_CHARS stay as single chunks."""
        from scripts.index_local_docs import chunk_markdown

        text = "## A\nShort.\n## B\nAlso short."
        chunks = chunk_markdown(text, "test.md")
        assert len(chunks) == 2
        assert chunks[0]["text"] == "Short."
        assert chunks[1]["text"] == "Also short."

    def test_chunk_splits_oversized_sections(self) -> None:
        from scripts import index_local_docs as subject

        # Build a section larger than MAX_CHUNK_CHARS with multiple paragraphs
        para = "word " * 300  # ~1500 chars per paragraph
        text = "## Big\n" + para + "\n\n" + para
        chunks = subject.chunk_markdown(text, "big.md")
        assert len(chunks) >= 2
        for c in chunks:
            assert c["heading"] == "Big"

    def test_chunk_preserves_content(self) -> None:
        from scripts.index_local_docs import chunk_markdown

        text = "## Intro\nHello world\n\nSecond paragraph"
        chunks = chunk_markdown(text, "f.md")
        combined = " ".join(c["text"] for c in chunks)
        assert "Hello world" in combined
        assert "Second paragraph" in combined


# --- load_document_chunks ---


class TestLoadDocumentChunks:
    def test_load_assigns_deterministic_uuid(self, tmp_path: Path) -> None:
        from scripts.index_local_docs import load_document_chunks

        md = tmp_path / "doc.md"
        md.write_text("## Sec\nBody", encoding="utf-8")
        chunks_a = load_document_chunks(md)
        chunks_b = load_document_chunks(md)
        assert chunks_a[0]["id"] == chunks_b[0]["id"]
        # Valid UUID
        import uuid

        uuid.UUID(chunks_a[0]["id"])

    def test_load_sets_doc_id_and_chunk_index(self, tmp_path: Path) -> None:
        from scripts.index_local_docs import load_document_chunks

        md = tmp_path / "notes.md"
        md.write_text("## A\nFirst\n## B\nSecond", encoding="utf-8")
        chunks = load_document_chunks(md)
        assert len(chunks) == 2
        for i, c in enumerate(chunks):
            assert c["doc_id"] == "notes.md"
            assert c["chunk_index"] == i
            assert c["source_file"] == "notes.md"


# --- delete_doc_points ---


def test_delete_calls_qdrant_with_filter() -> None:
    from scripts.index_local_docs import delete_doc_points

    client = mock.MagicMock()
    client.delete.return_value = SimpleNamespace(operation_id=42)
    result = delete_doc_points(client, "col", "my_doc.md")
    assert result == 42
    client.delete.assert_called_once()
    call_kwargs = client.delete.call_args.kwargs
    assert call_kwargs["collection_name"] == "col"
    filt = call_kwargs["points_selector"]
    assert filt.must[0].key == "metadata.doc_id"
    assert filt.must[0].match.value == "my_doc.md"


# --- ensure_payload_indexes ---


class TestEnsurePayloadIndexes:
    def test_ensure_creates_keyword_indexes(self) -> None:
        from scripts.index_local_docs import (
            PAYLOAD_INDEX_FIELDS,
            ensure_payload_indexes,
        )

        client = mock.MagicMock()
        ensure_payload_indexes(client, "col")
        assert client.create_payload_index.call_count == len(PAYLOAD_INDEX_FIELDS)
        for call_args in client.create_payload_index.call_args_list:
            kw = call_args.kwargs
            assert kw["collection_name"] == "col"
            assert kw["field_schema"] == PayloadSchemaType.KEYWORD
            assert kw["wait"] is True

    def test_ensure_ignores_existing_index_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.index_local_docs import ensure_payload_indexes

        client = mock.MagicMock()
        client.create_payload_index.side_effect = RuntimeError("already exists")
        # Should not raise
        ensure_payload_indexes(client, "col")
        out = capsys.readouterr().out
        assert "WARNING" in out


# --- encode_hybrid_http ---


class TestEncodeHybridHttp:
    def test_encode_hybrid_batches_correctly(self) -> None:
        from scripts.index_local_docs import encode_hybrid_http

        mock_response = mock.MagicMock()
        mock_response.json.return_value = {
            "dense_vecs": [[0.1]],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
            "colbert_vecs": [[[0.2]]],
        }
        mock_response.raise_for_status = mock.MagicMock()

        with mock.patch("httpx.post", return_value=mock_response) as mock_post:
            encode_hybrid_http(["a", "b", "c"], "http://bge:8000", batch_size=2)

        assert mock_post.call_count == 2  # 2 texts + 1 text
        # First batch has 2 texts, second has 1
        first_call_texts = mock_post.call_args_list[0].kwargs["json"]["texts"]
        second_call_texts = mock_post.call_args_list[1].kwargs["json"]["texts"]
        assert first_call_texts == ["a", "b"]
        assert second_call_texts == ["c"]

    def test_encode_hybrid_returns_all_three_vectors(self) -> None:
        from scripts.index_local_docs import encode_hybrid_http

        mock_response = mock.MagicMock()
        mock_response.json.return_value = {
            "dense_vecs": [[0.1, 0.2]],
            "lexical_weights": [{"indices": [0], "values": [1.0]}],
            "colbert_vecs": [[[0.3, 0.4]]],
        }
        mock_response.raise_for_status = mock.MagicMock()

        with mock.patch("httpx.post", return_value=mock_response):
            result = encode_hybrid_http(["text"], "http://bge:8000")

        assert "dense" in result
        assert "sparse" in result
        assert "colbert" in result
        assert len(result["dense"]) == 1
        assert len(result["sparse"]) == 1
        assert len(result["colbert"]) == 1


# --- preflight_check (additional) ---


class TestPreflightCheck:
    def test_preflight_exits_when_collection_missing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from scripts.index_local_docs import preflight_check

        client = mock.MagicMock()
        client.collection_exists.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            preflight_check(client, "nonexistent")

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "does not exist" in out

    def test_preflight_passes_when_all_vectors_present(self) -> None:
        from scripts.index_local_docs import preflight_check

        client = mock.MagicMock()
        client.collection_exists.return_value = True
        client.get_collection.return_value = _collection_info()

        # Should not raise
        preflight_check(client, "col")
