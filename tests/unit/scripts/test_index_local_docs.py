"""Regression tests for scripts/index_local_docs.py review fixes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from qdrant_client.models import PointStruct


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
