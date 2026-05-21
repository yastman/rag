# tests/unit/ingestion/test_qdrant_writer_build_then_delete.py
"""TDD tests for build-then-delete ordering in upsert_chunks_sync (#1602).

Verifies that:
1. upsert calls precede delete calls in method_calls order
2. Embedding failure does NOT trigger delete_file_sync
3. Upsert failure does NOT trigger delete_file_sync
4. Happy path: stale points ARE deleted AFTER successful upsert
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from qdrant_client.models import PointStruct, SparseVector

from src.ingestion.unified.qdrant_writer import QdrantHybridWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    *,
    text: str = "hello world",
    order: int = 0,
) -> MagicMock:
    chunk = MagicMock()
    chunk.text = text
    chunk.order = order
    chunk.extra_metadata = {}
    chunk.document_name = "doc.pdf"
    chunk.page_range = None
    chunk.section = None
    chunk.chunk_id = order
    return chunk


def _make_hybrid_result(n: int = 1) -> MagicMock:
    """Return a mock HybridResult with *n* vectors."""
    result = MagicMock()
    result.dense_vecs = [[0.1] * 1024 for _ in range(n)]
    result.lexical_weights = [{"indices": [0, 1], "values": [0.5, 0.5]}] * n
    result.colbert_vecs = []
    return result


def _build_writer() -> QdrantHybridWriter:
    """Build a QdrantHybridWriter with all heavy deps mocked."""
    with (
        patch("src.ingestion.unified.qdrant_writer.QdrantClient"),
        patch("telegram_bot.services.bge_m3_client.BGEM3SyncClient"),
    ):
        writer = QdrantHybridWriter.__new__(QdrantHybridWriter)

    writer.use_local_embeddings = True
    writer.voyage = None

    # Sync Qdrant client mock
    writer.client = MagicMock()
    writer.client.count.return_value = MagicMock(count=3)  # 3 old points exist
    writer.client.delete = MagicMock()
    writer.client.upsert = MagicMock()

    # BGE-M3 client mock
    writer._bge_client = MagicMock()
    writer._bge_client.encode_hybrid.return_value = _make_hybrid_result(1)

    return writer


# ---------------------------------------------------------------------------
# Test 1: upsert precedes delete in method_calls
# ---------------------------------------------------------------------------


def test_upsert_chunks_sync_does_not_delete_before_upsert():
    """After fix: first significant call on client must be upsert, not delete.

    This test verifies the build-then-delete ordering: we should see an
    upsert call before any delete call.
    """
    writer = _build_writer()
    chunks = [_make_chunk()]

    writer.upsert_chunks_sync(
        chunks=chunks,
        file_id="file-abc",
        source_path="test/doc.pdf",
        file_metadata={"language": "en"},
        collection_name="test_col",
    )

    # Collect call names on writer.client in order
    call_names = [c[0] for c in writer.client.method_calls]

    upsert_positions = [i for i, name in enumerate(call_names) if name == "upsert"]
    delete_positions = [i for i, name in enumerate(call_names) if name == "delete"]

    assert upsert_positions, "Expected at least one client.upsert() call"
    # Either no delete at all (if IDs are identical), or delete comes AFTER first upsert
    if delete_positions:
        first_upsert = min(upsert_positions)
        first_delete = min(delete_positions)
        assert first_upsert < first_delete, (
            f"delete (pos {first_delete}) must come AFTER upsert (pos {first_upsert}), "
            "but delete happened first — data-loss risk (#1602)"
        )


# ---------------------------------------------------------------------------
# Test 2: embed failure → delete_file_sync NOT called
# ---------------------------------------------------------------------------


def test_upsert_chunks_sync_preserves_old_points_on_embed_failure():
    """If embedding raises, delete_file_sync must NOT be called."""
    writer = _build_writer()
    writer._bge_client.encode_hybrid.side_effect = RuntimeError("BGE-M3 timeout")

    chunks = [_make_chunk()]

    with patch.object(writer, "delete_file_sync", wraps=writer.delete_file_sync) as mock_del:
        stats = writer.upsert_chunks_sync(
            chunks=chunks,
            file_id="file-abc",
            source_path="test/doc.pdf",
            file_metadata={"language": "en"},
            collection_name="test_col",
        )

    mock_del.assert_not_called(), (
        "delete_file_sync must NOT be called when embedding fails — "
        "last-good points would be lost (#1602)"
    )
    assert stats.errors, "Expected errors to be populated on embed failure"


# ---------------------------------------------------------------------------
# Test 3: upsert failure → delete_file_sync NOT called
# ---------------------------------------------------------------------------


def test_upsert_chunks_sync_preserves_old_points_on_upsert_failure():
    """If _upsert_points_in_batches raises, delete_file_sync must NOT be called."""
    writer = _build_writer()

    chunks = [_make_chunk()]

    with (
        patch.object(
            writer,
            "_upsert_points_in_batches",
            side_effect=RuntimeError("Qdrant upsert error"),
        ),
        patch.object(writer, "delete_file_sync", wraps=writer.delete_file_sync) as mock_del,
    ):
        stats = writer.upsert_chunks_sync(
            chunks=chunks,
            file_id="file-abc",
            source_path="test/doc.pdf",
            file_metadata={"language": "en"},
            collection_name="test_col",
        )

    mock_del.assert_not_called(), (
        "delete_file_sync must NOT be called when upsert fails — "
        "last-good points would be lost (#1602)"
    )
    assert stats.errors, "Expected errors to be populated on upsert failure"


# ---------------------------------------------------------------------------
# Test 4: happy path — stale points deleted AFTER successful upsert
# ---------------------------------------------------------------------------


def test_upsert_chunks_sync_deletes_stale_points_after_successful_upsert():
    """Happy path: after successful upsert, stale old points are deleted.

    The delete must happen AFTER upsert, and must target only stale points
    (either via filter or point ID exclusion).
    """
    writer = _build_writer()

    chunks = [_make_chunk(text="chunk 0", order=0)]

    # Track call order on client
    call_order: list[str] = []
    original_upsert = writer.client.upsert
    original_delete = writer.client.delete

    def tracking_upsert(**kwargs):
        call_order.append("upsert")
        return original_upsert(**kwargs)

    def tracking_delete(**kwargs):
        call_order.append("delete")
        return original_delete(**kwargs)

    writer.client.upsert = tracking_upsert
    writer.client.delete = tracking_delete

    stats = writer.upsert_chunks_sync(
        chunks=chunks,
        file_id="file-abc",
        source_path="test/doc.pdf",
        file_metadata={"language": "en"},
        collection_name="test_col",
    )

    assert stats.errors is None or stats.errors == [], (
        f"Expected no errors in happy path, got: {stats.errors}"
    )
    assert stats.points_upserted > 0, "Expected points to be upserted"

    # Delete must have been called (stale cleanup)
    assert "delete" in call_order, (
        "Expected client.delete() to be called for stale point cleanup"
    )

    # And upsert must precede delete
    upsert_idx = call_order.index("upsert")
    delete_idx = call_order.index("delete")
    assert upsert_idx < delete_idx, (
        f"upsert (pos {upsert_idx}) must precede delete (pos {delete_idx})"
    )

    # points_deleted should be populated
    assert stats.points_deleted >= 0, "stats.points_deleted should be non-negative"
