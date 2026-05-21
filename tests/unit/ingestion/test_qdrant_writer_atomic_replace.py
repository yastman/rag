***REMOVED*** tests/unit/ingestion/test_qdrant_writer_atomic_replace.py
"""Atomic replace semantics for QdrantHybridWriter (issue ***REMOVED***1602).

The bug: ``upsert_chunks_sync`` previously deleted existing points for a
``file_id`` BEFORE generating replacement embeddings/points and upserting them.
If embedding generation, ColBERT inference, or the upsert call failed, the
collection lost the last good version of the document until the next
successful retry.

The fix: build replacement embeddings and points FIRST, upsert them with
deterministic IDs, and only then delete points that became stale (those that
belong to ``file_id`` but are not part of the new upsert batch).

These tests pin the new contract so we do not regress to the destructive
delete-first ordering.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qdrant_client.models import HasIdCondition

from src.ingestion.unified.qdrant_writer import QdrantHybridWriter


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Helpers
***REMOVED*** ---------------------------------------------------------------------------


def _make_chunk(
    *,
    text: str = "Sample chunk text",
    order: int = 0,
    extra_metadata: dict | None = None,
) -> MagicMock:
    chunk = MagicMock()
    chunk.text = text
    chunk.order = order
    chunk.extra_metadata = extra_metadata or {}
    chunk.document_name = "test.pdf"
    chunk.page_range = None
    chunk.section = None
    chunk.chunk_id = order
    return chunk


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Atomic-replace failure-recovery contract (***REMOVED***1602)
***REMOVED*** ---------------------------------------------------------------------------


class TestEmbeddingFailureLeavesOldPointsIntact:
    """If embedding/upsert fails, no destructive delete must have happened.

    Reproduces the data-loss condition called out in ***REMOVED***1602: the writer
    previously deleted by file_id filter before any embedding work, so any
    embedding error wiped the file from search even though no replacement
    was upserted.
    """

    def test_voyage_embedding_failure_does_not_call_delete(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """When Voyage embedding raises, delete must not have been called."""
        mock_qdrant_client.count.return_value = MagicMock(count=5)
        mock_voyage._client.embed.side_effect = RuntimeError("Voyage API down")
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk()
        stats = writer_voyage.upsert_chunks_sync([chunk], "file_1", "/p", {}, "col")

        assert stats.errors is not None
        assert "Voyage API down" in stats.errors[0]
        ***REMOVED*** The destructive delete must not have run before the failed embed
        mock_qdrant_client.delete.assert_not_called()
        ***REMOVED*** And no upsert happened either, so points_upserted stays 0
        assert stats.points_upserted == 0
        mock_qdrant_client.upsert.assert_not_called()

    def test_sparse_embedding_failure_does_not_call_delete(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """When BGE-M3 sparse encode raises, delete must not have been called."""
        mock_qdrant_client.count.return_value = MagicMock(count=3)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.side_effect = RuntimeError("BGE-M3 timeout")

        chunk = _make_chunk()
        stats = writer_voyage.upsert_chunks_sync([chunk], "file_1", "/p", {}, "col")

        assert stats.errors is not None
        assert "BGE-M3 timeout" in stats.errors[0]
        mock_qdrant_client.delete.assert_not_called()
        mock_qdrant_client.upsert.assert_not_called()

    def test_local_hybrid_failure_does_not_call_delete(
        self, writer_local, mock_qdrant_client, mock_bge_client
    ):
        """When local BGE-M3 hybrid encode raises, delete must not have been called."""
        mock_qdrant_client.count.return_value = MagicMock(count=7)
        mock_bge_client.encode_hybrid.side_effect = RuntimeError("hybrid encode failed")

        chunk = _make_chunk()
        stats = writer_local.upsert_chunks_sync([chunk], "file_1", "/p", {}, "col")

        assert stats.errors is not None
        assert "hybrid encode failed" in stats.errors[0]
        mock_qdrant_client.delete.assert_not_called()
        mock_qdrant_client.upsert.assert_not_called()

    def test_upsert_failure_does_not_call_delete(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """When the upsert call to Qdrant raises, delete must not have been called."""
        mock_qdrant_client.count.return_value = MagicMock(count=4)
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )
        mock_qdrant_client.upsert.side_effect = RuntimeError("Qdrant upsert failed")

        chunk = _make_chunk()
        stats = writer_voyage.upsert_chunks_sync([chunk], "file_1", "/p", {}, "col")

        assert stats.errors is not None
        assert "Qdrant upsert failed" in stats.errors[0]
        mock_qdrant_client.delete.assert_not_called()


class TestSuccessPathOrderingIsUpsertThenDelete:
    """On success, upsert must happen BEFORE the stale-id delete sweep.

    Old contract (delete-first) was the bug. New contract: replacement points
    are visible to readers throughout, then stale chunks (by id) are removed.
    """

    def test_upsert_called_before_delete_on_success(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """Calls to client.upsert must precede client.delete in time."""
        call_order: list[str] = []
        ***REMOVED*** Pretend there are stale points so a delete sweep is required after upsert
        mock_qdrant_client.count.return_value = MagicMock(count=2)
        mock_qdrant_client.scroll.return_value = (
            [
                MagicMock(id="00000000-0000-0000-0000-000000000aaa"),
                MagicMock(id="00000000-0000-0000-0000-000000000bbb"),
            ],
            None,
        )
        mock_qdrant_client.delete.side_effect = lambda **_: call_order.append("delete")
        mock_qdrant_client.upsert.side_effect = lambda **_: call_order.append("upsert")
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk()
        stats = writer_voyage.upsert_chunks_sync([chunk], "file_1", "/p", {}, "col")

        assert stats.errors is None
        ***REMOVED*** Upsert must come before any delete
        assert call_order[0] == "upsert"
        ***REMOVED*** delete may or may not be present depending on whether stale ids exist;
        ***REMOVED*** if it is present, every delete is strictly after the first upsert
        upsert_indices = [i for i, c in enumerate(call_order) if c == "upsert"]
        delete_indices = [i for i, c in enumerate(call_order) if c == "delete"]
        if delete_indices:
            assert min(delete_indices) > min(upsert_indices)


class TestStaleDeleteScopeIsRestrictedToOrphanIds:
    """Delete must target stale ids only, never blanket-delete by file_id.

    This is the structural guard against re-introducing the original bug.
    A whole-file ``Filter(must=[FieldCondition(metadata.file_id ...)])``
    delete is exactly what ***REMOVED***1602 forbids — even if it runs after upsert,
    a future refactor must not blindly drop the whole file.
    """

    def test_stale_delete_uses_id_based_selector_when_orphans_exist(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """When stale chunks exist (old ids not in the new batch), delete uses HasId."""
        mock_qdrant_client.count.return_value = MagicMock(count=3)
        ***REMOVED*** Existing stored points: 1 will be replaced (same chunk_location: order_0),
        ***REMOVED*** 2 are stale orphans that should be swept after the upsert.
        new_chunk_id = QdrantHybridWriter.generate_point_id("file_1", "order_0")
        stale_id_a = "00000000-0000-0000-0000-aaaaaaaaaaaa"
        stale_id_b = "00000000-0000-0000-0000-bbbbbbbbbbbb"
        mock_qdrant_client.scroll.return_value = (
            [
                MagicMock(id=new_chunk_id),  ***REMOVED*** will collide with the upsert
                MagicMock(id=stale_id_a),
                MagicMock(id=stale_id_b),
            ],
            None,
        )
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}]
        )

        chunk = _make_chunk(text="text 0", order=0)
        stats = writer_voyage.upsert_chunks_sync([chunk], "file_1", "/p", {}, "col")

        assert stats.errors is None
        assert stats.points_upserted == 1

        ***REMOVED*** Exactly one delete call, and it is restricted to the stale ids only
        assert mock_qdrant_client.delete.call_count == 1
        selector = mock_qdrant_client.delete.call_args.kwargs["points_selector"]
        ***REMOVED*** Selector must reference the stale ids, not the file_id filter pattern
        deleted_ids: list[str] = []
        if isinstance(selector, list):
            deleted_ids = [str(x) for x in selector]
        elif hasattr(selector, "points"):
            deleted_ids = [str(x) for x in selector.points]
        else:
            ***REMOVED*** Filter form: must be a HasIdCondition over stale ids, NOT the file_id field condition
            for cond in getattr(selector, "must", []) or []:
                if isinstance(cond, HasIdCondition):
                    deleted_ids.extend(str(x) for x in cond.has_id)
                    continue
                ***REMOVED*** Forbid the legacy whole-file metadata.file_id selector
                if hasattr(cond, "key"):
                    pytest.fail(
                        "Stale-delete must not use a metadata.file_id Filter; "
                        f"got FieldCondition on key={cond.key!r}"
                    )

        assert set(deleted_ids) == {stale_id_a, stale_id_b}
        ***REMOVED*** The new chunk id must NOT be in the delete set
        assert new_chunk_id not in deleted_ids

    def test_no_stale_delete_when_every_old_id_is_replaced(
        self, writer_voyage, mock_qdrant_client, mock_voyage, mock_bge_client
    ):
        """If every existing point is replaced by an upsert with the same id, skip delete."""
        mock_qdrant_client.count.return_value = MagicMock(count=2)
        ***REMOVED*** _make_chunk(order=N) maps to chunk_location "order_N"
        new_id_0 = QdrantHybridWriter.generate_point_id("file_1", "order_0")
        new_id_1 = QdrantHybridWriter.generate_point_id("file_1", "order_1")
        mock_qdrant_client.scroll.return_value = (
            [MagicMock(id=new_id_0), MagicMock(id=new_id_1)],
            None,
        )
        mock_voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024] * 2)
        mock_bge_client.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1], "values": [0.5]}] * 2
        )

        chunks = [_make_chunk(text=f"text {i}", order=i) for i in range(2)]
        stats = writer_voyage.upsert_chunks_sync(chunks, "file_1", "/p", {}, "col")

        assert stats.errors is None
        assert stats.points_upserted == 2
        mock_qdrant_client.delete.assert_not_called()


***REMOVED*** Reuse fixtures from the sibling behavior test module
pytest_plugins = ["tests.unit.ingestion.test_qdrant_writer_behavior"]
