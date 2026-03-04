# tests/unit/ingestion/test_qdrant_writer_behavior.py
"""Behavior tests for QdrantHybridWriter sync methods.

Tests the actual business logic:
- delete_file_sync: filter structure, count before delete, skip delete when empty
- upsert_chunks_sync: payload contract, vector construction, delete before upsert,
  Voyage batching, sparse edge cases, colbert presence/absence, error handling
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.models import Filter, PointStruct, SparseVector

from src.ingestion.unified.qdrant_writer import QdrantHybridWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    *,
    text: str = "Sample chunk text",
    order: int = 0,
    extra_metadata: dict | None = None,
) -> MagicMock:
    """Return a minimal chunk object compatible with QdrantHybridWriter."""
    chunk = MagicMock()
    chunk.text = text
    chunk.order = order
    chunk.extra_metadata = extra_metadata or {}
    chunk.document_name = "test.pdf"
    chunk.page_range = None
    chunk.section = None
    chunk.chunk_id = order
    return chunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_qdrant_client():
    """Mock sync QdrantClient."""
    client = MagicMock()
    client.count.return_value = MagicMock(count=0)
    client.delete = MagicMock()
    client.upsert = MagicMock()
    return client


@pytest.fixture
def mock_bge_client():
    """Mock BGEM3SyncClient for sparse/dense/colbert embeddings."""
    client = MagicMock()
    client.encode_sparse.return_value = MagicMock(
        weights=[{"indices": [1, 2], "values": [0.5, 0.3]}]
    )
    client.encode_colbert.return_value = MagicMock(colbert_vecs=[[[0.1] * 128] * 5])
    client.encode_dense.return_value = MagicMock(vectors=[[0.2] * 1024])
    return client


@pytest.fixture
def mock_voyage():
    """Mock VoyageService client (Voyage API path)."""
    voyage = MagicMock()
    voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
    voyage._model_docs = "voyage-4-large"
    return voyage


@pytest.fixture
def writer_voyage(mock_qdrant_client, mock_bge_client, mock_voyage):
    """QdrantHybridWriter using Voyage for dense embeddings."""
    with (
        patch(
            "src.ingestion.unified.qdrant_writer.QdrantClient",
            return_value=mock_qdrant_client,
        ),
        patch(
            "telegram_bot.services.bge_m3_client.BGEM3SyncClient",
            return_value=mock_bge_client,
        ),
        patch(
            "src.ingestion.unified.qdrant_writer.VoyageService",
            return_value=mock_voyage,
        ),
    ):
        w = QdrantHybridWriter(
            qdrant_url="http://localhost:6333",
            voyage_api_key="test_key",
            use_local_embeddings=False,
        )
    # After construction, inject mocks so tests can set side_effects
    w.client = mock_qdrant_client
    w._bge_client = mock_bge_client
    w.voyage = mock_voyage
    yield w


@pytest.fixture
def writer_local(mock_qdrant_client, mock_bge_client):
    """QdrantHybridWriter using local BGE-M3 for all embeddings."""
    with (
        patch(
            "src.ingestion.unified.qdrant_writer.QdrantClient",
            return_value=mock_qdrant_client,
        ),
        patch(
            "telegram_bot.services.bge_m3_client.BGEM3SyncClient",
            return_value=mock_bge_client,
        ),
    ):
        w = QdrantHybridWriter(
            qdrant_url="http://localhost:6333",
            use_local_embeddings=True,
        )
    w.client = mock_qdrant_client
    w._bge_client = mock_bge_client
    yield w


# ---------------------------------------------------------------------------
# delete_file_sync
# ---------------------------------------------------------------------------


class TestDeleteFileSyncBehavior:
    """Verify delete_file_sync filter structure and count-before-delete logic."""

    def test_returns_zero_when_no_points_exist(self, writer_voyage, mock_qdrant_client):
        """Returns 0 and does not call delete when count is 0."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)

        result = writer_voyage.delete_file_sync("file_1", "my_collection")

        assert result == 0
        mock_qdrant_client.delete.assert_not_called()

    def test_returns_count_and_deletes_when_points_exist(self, writer_voyage, mock_qdrant_client):
        """Returns count and calls delete when points exist."""
        mock_qdrant_client.count.return_value = MagicMock(count=5)

        result = writer_voyage.delete_file_sync("file_1", "my_collection")

        assert result == 5
        mock_qdrant_client.delete.assert_called_once()

    def test_count_uses_metadata_file_id_filter(self, writer_voyage, mock_qdrant_client):
        """count() is called with metadata.file_id filter (not flat file_id)."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)

        writer_voyage.delete_file_sync("my_file_id", "col")

        count_kwargs = mock_qdrant_client.count.call_args.kwargs
        filt = count_kwargs["count_filter"]
        assert isinstance(filt, Filter)
        condition = filt.must[0]
        assert condition.key == "metadata.file_id"
        assert condition.match.value == "my_file_id"

    def test_delete_uses_same_filter_as_count(self, writer_voyage, mock_qdrant_client):
        """delete() uses the same metadata.file_id filter as count()."""
        mock_qdrant_client.count.return_value = MagicMock(count=3)

        writer_voyage.delete_file_sync("target_file", "col")

        delete_kwargs = mock_qdrant_client.delete.call_args.kwargs
        filt = delete_kwargs["points_selector"]
        assert isinstance(filt, Filter)
        condition = filt.must[0]
        assert condition.key == "metadata.file_id"
        assert condition.match.value == "target_file"

    def test_delete_uses_correct_collection_name(self, writer_voyage, mock_qdrant_client):
        """delete() passes the correct collection_name."""
        mock_qdrant_client.count.return_value = MagicMock(count=2)

        writer_voyage.delete_file_sync("fid", "target_collection")

        delete_kwargs = mock_qdrant_client.delete.call_args.kwargs
        assert delete_kwargs["collection_name"] == "target_collection"


# ---------------------------------------------------------------------------
# upsert_chunks_sync — payload contract and vector structure
# ---------------------------------------------------------------------------


class TestUpsertChunksSyncBehavior:
    """Verify upsert_chunks_sync builds correct PointStruct objects."""

    def test_empty_chunks_returns_zero_stats(self, writer_voyage):
        """Empty chunk list skips all embedding and upsert work."""
        stats = writer_voyage.upsert_chunks_sync([], "file_1", "/path/file.pdf", {}, "col")

        assert stats.points_upserted == 0
        assert stats.points_deleted == 0
        assert stats.errors is None

    def test_upsert_called_with_correct_collection(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """upsert() receives the collection_name passed to upsert_chunks_sync."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk()
        writer_voyage.upsert_chunks_sync([chunk], "file_1", "/p", {}, "my_collection")

        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert upsert_kwargs["collection_name"] == "my_collection"

    def test_builds_point_with_dense_and_sparse_vectors(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """Each PointStruct has 'dense' and 'bm42' vector keys."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1, 2], "values": [0.5, 0.3]}]
        )

        chunk = _make_chunk(text="Hello world", order=0)
        writer_voyage.upsert_chunks_sync([chunk], "file_1", "/path/file.pdf", {}, "col")

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        assert len(points) == 1
        assert isinstance(points[0], PointStruct)
        assert "dense" in points[0].vector
        assert "bm42" in points[0].vector

    def test_payload_contains_page_content(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """Payload must include page_content with the chunk text."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk(text="Actual chunk text", order=2)
        writer_voyage.upsert_chunks_sync([chunk], "fid", "/path/doc.pdf", {}, "col")

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        assert points[0].payload["page_content"] == "Actual chunk text"

    def test_payload_metadata_has_required_fields(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """Payload metadata must include file_id, source, order (contract)."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk(text="Text", order=3)
        writer_voyage.upsert_chunks_sync(
            [chunk], "file_001", "/path/test.pdf", {"file_name": "test.pdf"}, "col"
        )

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        meta = points[0].payload["metadata"]
        assert meta["file_id"] == "file_001"
        assert "source" in meta
        assert "order" in meta

    def test_payload_has_flat_file_id_for_fast_delete(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """Top-level payload must include flat 'file_id' field for fast delete queries."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk()
        writer_voyage.upsert_chunks_sync([chunk], "flat_fid", "/p", {}, "col")

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        assert points[0].payload["file_id"] == "flat_fid"

    def test_delete_called_before_upsert_replace_semantics(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """delete_file_sync must run before upsert (replace semantics)."""
        call_order: list[str] = []
        mock_qdrant_client.count.return_value = MagicMock(count=2)
        mock_qdrant_client.delete.side_effect = lambda **_: call_order.append("delete")
        mock_qdrant_client.upsert.side_effect = lambda **_: call_order.append("upsert")
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk()
        writer_voyage.upsert_chunks_sync([chunk], "file_1", "/p", {}, "col")

        assert call_order == ["delete", "upsert"]

    def test_stats_points_upserted_matches_chunk_count(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """WriteStats.points_upserted equals the number of chunks."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        n = 3
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024] * n)
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}] * n
        )

        chunks = [_make_chunk(text=f"text {i}", order=i) for i in range(n)]
        stats = writer_voyage.upsert_chunks_sync(chunks, "fid", "/p", {}, "col")

        assert stats.points_upserted == n
        assert stats.errors is None


# ---------------------------------------------------------------------------
# upsert_chunks_sync — colbert vector behavior
# ---------------------------------------------------------------------------


class TestColbertVectorBehavior:
    """Verify colbert inclusion/exclusion based on embedding mode."""

    def test_colbert_absent_in_voyage_mode(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """When use_local_embeddings=False, 'colbert' key must NOT appear in vector."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk()
        writer_voyage.upsert_chunks_sync([chunk], "f", "/p", {}, "col")

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        assert "colbert" not in points[0].vector

    def test_colbert_present_in_local_embeddings_mode(
        self, writer_local, mock_qdrant_client, mock_bge_client
    ):
        """When use_local_embeddings=True, 'colbert' key must appear in vector."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_bge_client.encode_dense.return_value = MagicMock(vectors=[[0.2] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )
        mock_bge_client.encode_colbert.return_value = MagicMock(colbert_vecs=[[[0.3] * 128] * 5])

        chunk = _make_chunk()
        writer_local.upsert_chunks_sync([chunk], "f", "/p", {}, "col")

        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        assert "colbert" in points[0].vector


# ---------------------------------------------------------------------------
# upsert_chunks_sync — edge cases
# ---------------------------------------------------------------------------


class TestUpsertChunksSyncEdgeCases:
    """Verify edge cases: empty sparse indices, batching, error handling."""

    def test_sparse_with_empty_indices_creates_valid_sparse_vector(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """SparseVector with empty indices/values must not raise an error."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [], "values": []}]
        )

        chunk = _make_chunk()
        stats = writer_voyage.upsert_chunks_sync([chunk], "f", "/p", {}, "col")

        assert stats.errors is None
        points = mock_qdrant_client.upsert.call_args.kwargs["points"]
        sparse_vec = points[0].vector["bm42"]
        assert isinstance(sparse_vec, SparseVector)
        assert sparse_vec.indices == []
        assert sparse_vec.values == []

    def test_voyage_embed_batched_for_large_chunk_list(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """Voyage API calls are batched at VOYAGE_BATCH_SIZE chunks per call."""
        batch_size = QdrantHybridWriter.VOYAGE_BATCH_SIZE
        num_chunks = batch_size + 10  # forces 2 batches

        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.side_effect = [
            MagicMock(embeddings=[[0.1] * 1024] * batch_size),
            MagicMock(embeddings=[[0.2] * 1024] * 10),
        ]
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}] * num_chunks
        )

        chunks = [_make_chunk(text=f"text {i}", order=i) for i in range(num_chunks)]
        stats = writer_voyage.upsert_chunks_sync(chunks, "f", "/p", {}, "col")

        assert mock_voyage._client.embed.call_count == 2
        assert stats.points_upserted == num_chunks

    def test_qdrant_exception_captured_in_error_stats(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """If upsert raises, WriteStats.errors contains the message; points_upserted=0."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_qdrant_client.upsert.side_effect = RuntimeError("Qdrant timeout")
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk()
        stats = writer_voyage.upsert_chunks_sync([chunk], "f", "/p", {}, "col")

        assert stats.errors is not None
        assert "Qdrant timeout" in stats.errors[0]
        assert stats.points_upserted == 0

    def test_oversized_payload_skipped_with_error(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """Payload exceeding QDRANT_MAX_PAYLOAD_BYTES is skipped, not sent to Qdrant."""
        mock_qdrant_client.count.return_value = MagicMock(count=0)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        # Create chunk with oversized text (~40MB)
        huge_text = "x" * (35 * 1024 * 1024)
        chunk = _make_chunk(text=huge_text)
        stats = writer_voyage.upsert_chunks_sync([chunk], "f", "/big.pdf", {}, "col")

        assert stats.errors is not None
        assert "exceeds" in stats.errors[0]
        assert stats.points_upserted == 0
        mock_qdrant_client.upsert.assert_not_called()
