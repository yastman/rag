# tests/characterization/ingestion/test_ingest_characterization.py
"""Characterization tests for CocoIndex ingestion pipeline.

These tests lock the *current* observable behaviour of the ingestion
subsystem — they do NOT prescribe ideal design.  If a test breaks after a
refactor, update it to match the new behaviour rather than fixing code to
satisfy a stale expectation.

Covered areas:
  1. Chunk / point-ID generation (deterministic, stable across re-runs)
  2. Upsert path (atomic-replace: upsert first, delete stale after)
  3. Delete path (filter shape, count-before-delete guard)
  4. DLQ state (add_to_dlq, get_dlq_count)
  5. Retry / backoff behaviour (should_process gating, retry_count increment)
  6. _should_reprocess helper (pure logic, no DB)
  7. File identity (manifest: new / rename / copy detection)
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.unified.manifest import FileManifest, compute_content_hash_from_bytes
from src.ingestion.unified.qdrant_writer import NAMESPACE_GDRIVE, QdrantHybridWriter
from src.ingestion.unified.state_manager import FileState, UnifiedStateManager, _should_reprocess


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _chunk(
    text: str = "hello world",
    order: int = 0,
    extra_metadata: dict | None = None,
) -> MagicMock:
    c = MagicMock()
    c.text = text
    c.order = order
    c.extra_metadata = extra_metadata or {}
    c.document_name = "doc.pdf"
    c.page_range = None
    c.section = None
    c.chunk_id = order
    return c


def _state_row(
    *,
    file_id: str = "fid1",
    status: str = "indexed",
    content_hash: str | None = "abc123",
    retry_count: int = 0,
    retry_after: datetime | None = None,
    embedding_model: str = "bge-m3-api",
    pipeline_version: str = "v3.2.1",
) -> dict[str, Any]:
    return {
        "file_id": file_id,
        "source_path": None,
        "file_name": None,
        "mime_type": None,
        "file_size": None,
        "modified_time": None,
        "content_hash": content_hash,
        "parser_version": None,
        "chunker_version": None,
        "embedding_model": embedding_model,
        "chunk_count": 3,
        "collection_name": None,
        "pipeline_version": pipeline_version,
        "indexed_at": None,
        "status": status,
        "error_message": None,
        "retry_count": retry_count,
        "retry_after": retry_after,
    }


# ---------------------------------------------------------------------------
# 1. Chunk / point-ID generation
# ---------------------------------------------------------------------------


class TestChunkIdGeneration:
    """generate_point_id produces deterministic UUIDs from file_id + location."""

    def test_same_inputs_produce_same_id(self) -> None:
        id1 = QdrantHybridWriter.generate_point_id("fid1", "chunk_0")
        id2 = QdrantHybridWriter.generate_point_id("fid1", "chunk_0")
        assert id1 == id2

    def test_different_locations_produce_different_ids(self) -> None:
        id1 = QdrantHybridWriter.generate_point_id("fid1", "chunk_0")
        id2 = QdrantHybridWriter.generate_point_id("fid1", "chunk_1")
        assert id1 != id2

    def test_different_file_ids_produce_different_ids(self) -> None:
        id1 = QdrantHybridWriter.generate_point_id("fid1", "chunk_0")
        id2 = QdrantHybridWriter.generate_point_id("fid2", "chunk_0")
        assert id1 != id2

    def test_id_is_valid_uuid_string(self) -> None:
        point_id = QdrantHybridWriter.generate_point_id("fid1", "chunk_0")
        parsed = uuid.UUID(point_id)
        assert str(parsed) == point_id

    def test_id_uses_namespace_gdrive_uuid5(self) -> None:
        file_id, location = "fid1", "chunk_0"
        combined = f"{file_id}::{location}"
        expected = str(uuid.uuid5(NAMESPACE_GDRIVE, combined))
        assert QdrantHybridWriter.generate_point_id(file_id, location) == expected

    def test_get_chunk_location_fallback(self) -> None:
        chunk = _chunk(order=2)
        loc = QdrantHybridWriter.get_chunk_location(chunk, 2)
        # Current behaviour: falls through to order_N when extra_metadata is empty
        # and no docling page info is present.
        assert "2" in loc

    def test_get_chunk_location_docling_page_offset(self) -> None:
        chunk = _chunk(extra_metadata={"docling_meta": {"page": 3, "offset": 5}})
        loc = QdrantHybridWriter.get_chunk_location(chunk, 0)
        assert loc == "page_3_offset_5"

    def test_get_chunk_location_seq_no(self) -> None:
        chunk = _chunk(extra_metadata={"chunk_order": 7})
        loc = QdrantHybridWriter.get_chunk_location(chunk, 0)
        assert loc == "seq_7"


# ---------------------------------------------------------------------------
# 2. Upsert path (atomic-replace semantics)
# ---------------------------------------------------------------------------


class TestUpsertPath:
    """upsert_chunks_sync: upsert first, then sweep stale orphans."""

    @pytest.fixture
    def mock_qdrant(self) -> MagicMock:
        client = MagicMock()
        client.count.return_value = MagicMock(count=0)
        client.upsert = MagicMock()
        client.delete = MagicMock()
        client.scroll.return_value = ([], None)
        return client

    @pytest.fixture
    def mock_bge(self) -> MagicMock:
        from src.services.bge_m3_client import HybridResult

        client = MagicMock()

        def _hybrid(texts: list[str]) -> HybridResult:
            n = len(texts)
            return HybridResult(
                dense_vecs=[[0.1] * 1024] * n,
                lexical_weights=[{"indices": [1], "values": [0.5]}] * n,
                colbert_vecs=[[[0.01] * 128] * 3] * n,
            )

        client.encode_hybrid.side_effect = _hybrid
        return client

    @pytest.fixture
    def writer(self, mock_qdrant: MagicMock, mock_bge: MagicMock) -> QdrantHybridWriter:
        with (
            patch("src.ingestion.unified.qdrant_writer.QdrantClient", return_value=mock_qdrant),
            patch("src.services.bge_m3_client.BGEM3SyncClient", return_value=mock_bge),
        ):
            w = QdrantHybridWriter(qdrant_url="http://localhost:6333")
        w.client = mock_qdrant
        w._bge_client = mock_bge
        return w

    def test_upsert_called_before_delete(
        self, writer: QdrantHybridWriter, mock_qdrant: MagicMock
    ) -> None:
        """Upsert must complete before any stale-sweep delete (atomic-replace contract)."""
        call_order: list[str] = []
        mock_qdrant.upsert.side_effect = lambda **_kw: call_order.append("upsert")
        mock_qdrant.delete.side_effect = lambda **_kw: call_order.append("delete")

        writer.upsert_chunks_sync(
            [_chunk()],
            file_id="fid1",
            source_path="docs/file.pdf",
            file_metadata={},
            collection_name="test_col",
        )

        assert call_order[0] == "upsert"

    def test_upsert_returns_stats_with_upserted_count(
        self, writer: QdrantHybridWriter, mock_qdrant: MagicMock
    ) -> None:
        stats = writer.upsert_chunks_sync(
            [_chunk(), _chunk(text="second", order=1)],
            file_id="fid1",
            source_path="docs/file.pdf",
            file_metadata={},
            collection_name="test_col",
        )
        assert stats.points_upserted == 2
        assert stats.errors is None

    def test_empty_chunks_skips_embedding_and_upsert(
        self, writer: QdrantHybridWriter, mock_qdrant: MagicMock, mock_bge: MagicMock
    ) -> None:
        stats = writer.upsert_chunks_sync(
            [],
            file_id="fid1",
            source_path="docs/file.pdf",
            file_metadata={},
            collection_name="test_col",
        )
        mock_bge.encode_hybrid.assert_not_called()
        mock_qdrant.upsert.assert_not_called()
        assert stats.points_upserted == 0

    def test_upsert_error_captured_in_stats(
        self, writer: QdrantHybridWriter, mock_bge: MagicMock
    ) -> None:
        mock_bge.encode_hybrid.side_effect = RuntimeError("bge down")
        stats = writer.upsert_chunks_sync(
            [_chunk()],
            file_id="fid1",
            source_path="docs/file.pdf",
            file_metadata={},
            collection_name="test_col",
        )
        assert stats.errors is not None
        assert len(stats.errors) == 1

    def test_stale_sweep_deletes_orphan_ids(
        self, writer: QdrantHybridWriter, mock_qdrant: MagicMock
    ) -> None:
        """After upsert, stale orphan points for the same file_id are deleted."""
        stale_id = str(uuid.uuid4())
        # scroll returns one stale point not in the new batch
        mock_qdrant.scroll.return_value = ([MagicMock(id=stale_id)], None)

        stats = writer.upsert_chunks_sync(
            [_chunk()],
            file_id="fid1",
            source_path="docs/file.pdf",
            file_metadata={},
            collection_name="test_col",
        )
        # delete called at least once (stale sweep)
        mock_qdrant.delete.assert_called()
        assert stats.points_deleted == 1


# ---------------------------------------------------------------------------
# 3. Delete path
# ---------------------------------------------------------------------------


class TestDeletePath:
    """delete_file_sync: count first, only delete if count > 0."""

    @pytest.fixture
    def mock_qdrant(self) -> MagicMock:
        client = MagicMock()
        client.count.return_value = MagicMock(count=0)
        client.delete = MagicMock()
        return client

    @pytest.fixture
    def writer(self, mock_qdrant: MagicMock) -> QdrantHybridWriter:
        with (
            patch("src.ingestion.unified.qdrant_writer.QdrantClient", return_value=mock_qdrant),
            patch("src.services.bge_m3_client.BGEM3SyncClient", return_value=MagicMock()),
        ):
            w = QdrantHybridWriter(qdrant_url="http://localhost:6333")
        w.client = mock_qdrant
        return w

    def test_delete_skipped_when_count_is_zero(
        self, writer: QdrantHybridWriter, mock_qdrant: MagicMock
    ) -> None:
        mock_qdrant.count.return_value = MagicMock(count=0)
        result = writer.delete_file_sync("fid1", "test_col")
        mock_qdrant.delete.assert_not_called()
        assert result == 0

    def test_delete_called_when_points_exist(
        self, writer: QdrantHybridWriter, mock_qdrant: MagicMock
    ) -> None:
        mock_qdrant.count.return_value = MagicMock(count=3)
        result = writer.delete_file_sync("fid1", "test_col")
        mock_qdrant.delete.assert_called_once()
        assert result == 3

    def test_delete_filter_uses_metadata_file_id(
        self, writer: QdrantHybridWriter, mock_qdrant: MagicMock
    ) -> None:
        mock_qdrant.count.return_value = MagicMock(count=1)
        writer.delete_file_sync("fid_target", "test_col")
        # Count filter must reference metadata.file_id with the correct file_id
        count_call = mock_qdrant.count.call_args
        count_filter = (
            count_call.kwargs.get("count_filter") or count_call.args[0] if count_call.args else None
        )
        if count_filter is None and count_call:
            count_filter = count_call[1].get("count_filter")
        # Verify the filter condition key
        from qdrant_client.models import FieldCondition

        assert count_filter is not None
        must_conditions = count_filter.must
        assert any(
            isinstance(c, FieldCondition) and c.key == "metadata.file_id" for c in must_conditions
        )


# ---------------------------------------------------------------------------
# 4. DLQ state
# ---------------------------------------------------------------------------


class TestDlqState:
    """add_to_dlq and get_dlq_count characterize DLQ row insertion contract."""

    @pytest.fixture
    def mock_pool(self) -> AsyncMock:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=None)
        pool.fetch = AsyncMock(return_value=[])
        pool.close = AsyncMock()
        return pool

    @pytest.fixture
    def manager(self, mock_pool: AsyncMock) -> UnifiedStateManager:
        return UnifiedStateManager(pool=mock_pool)

    @pytest.mark.asyncio
    async def test_add_to_dlq_inserts_row(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        mock_pool.fetchrow.return_value = {"id": 42}
        dlq_id = await manager.add_to_dlq(
            file_id="fid1",
            error_type="parse_error",
            error_message="something went wrong",
        )
        mock_pool.fetchrow.assert_called_once()
        assert dlq_id == 42

    @pytest.mark.asyncio
    async def test_add_to_dlq_truncates_long_message(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        mock_pool.fetchrow.return_value = {"id": 1}
        long_msg = "x" * 5000
        await manager.add_to_dlq("fid1", "error", long_msg)
        call_args = mock_pool.fetchrow.call_args
        # Third positional arg to fetchrow is the error_message
        passed_msg = call_args.args[3] if len(call_args.args) > 3 else call_args[0][3]
        assert len(passed_msg) <= 2000

    @pytest.mark.asyncio
    async def test_get_dlq_count_returns_zero_when_empty(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        mock_pool.fetchrow.return_value = {"count": 0}
        count = await manager.get_dlq_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_dlq_count_returns_value(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        mock_pool.fetchrow.return_value = {"count": 7}
        count = await manager.get_dlq_count()
        assert count == 7

    @pytest.mark.asyncio
    async def test_should_process_returns_false_after_three_retries(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """File with retry_count >= 3 is in DLQ; should_process returns False."""
        # asyncpg.Record is dict-like; from_row calls dict(row) then filters fields
        mock_pool.fetchrow.return_value = _state_row(status="error", retry_count=3)
        result = await manager.should_process("fid1", "newhash")
        assert result is False


# ---------------------------------------------------------------------------
# 5. Retry / backoff behaviour
# ---------------------------------------------------------------------------


class TestRetryBehaviour:
    """_should_reprocess and should_process gating characterization."""

    def test_should_reprocess_true_for_none_state(self) -> None:
        assert _should_reprocess(None, "hash1", None, None) is True

    def test_should_reprocess_false_for_matching_indexed(self) -> None:
        state = FileState(
            file_id="f1",
            status="indexed",
            content_hash="hash1",
            embedding_model="bge-m3-api",
            pipeline_version="v3.2.1",
        )
        assert _should_reprocess(state, "hash1", "bge-m3-api", "v3.2.1") is False

    def test_should_reprocess_true_for_changed_hash(self) -> None:
        state = FileState(
            file_id="f1",
            status="indexed",
            content_hash="hash1",
            embedding_model="bge-m3-api",
            pipeline_version="v3.2.1",
        )
        assert _should_reprocess(state, "hash2", "bge-m3-api", "v3.2.1") is True

    def test_should_reprocess_true_for_non_indexed_status(self) -> None:
        for status in ("pending", "processing", "error", "deleted"):
            state = FileState(file_id="f1", status=status, content_hash="hash1")
            assert _should_reprocess(state, "hash1", None, None) is True

    def test_should_reprocess_true_for_model_mismatch(self) -> None:
        state = FileState(
            file_id="f1",
            status="indexed",
            content_hash="hash1",
            embedding_model="old-model",
            pipeline_version="v3.2.1",
        )
        assert _should_reprocess(state, "hash1", "bge-m3-api", "v3.2.1") is True

    def test_should_reprocess_true_for_pipeline_version_mismatch(self) -> None:
        state = FileState(
            file_id="f1",
            status="indexed",
            content_hash="hash1",
            embedding_model="bge-m3-api",
            pipeline_version="v2.0.0",
        )
        assert _should_reprocess(state, "hash1", "bge-m3-api", "v3.2.1") is True

    def test_should_reprocess_legacy_none_model_ignores_mismatch(self) -> None:
        """Legacy callers pass None for model/version; only hash is compared."""
        state = FileState(
            file_id="f1",
            status="indexed",
            content_hash="hash1",
            embedding_model="old-model",
            pipeline_version="v1.0.0",
        )
        # Passing None for model/version preserves hash-only backward compat
        assert _should_reprocess(state, "hash1", None, None) is False

    @pytest.fixture
    def mock_pool(self) -> AsyncMock:
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=None)
        pool.fetch = AsyncMock(return_value=[])
        pool.execute = AsyncMock()
        pool.close = AsyncMock()
        return pool

    @pytest.fixture
    def manager(self, mock_pool: AsyncMock) -> UnifiedStateManager:
        return UnifiedStateManager(pool=mock_pool)

    @pytest.mark.asyncio
    async def test_should_process_true_for_new_file(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        mock_pool.fetchrow.return_value = None
        result = await manager.should_process("new_fid", "hash1")
        assert result is True

    @pytest.mark.asyncio
    async def test_should_process_false_during_backoff(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        future_retry = datetime.now(UTC) + timedelta(hours=1)
        mock_pool.fetchrow.return_value = _state_row(
            status="error", retry_count=1, retry_after=future_retry
        )
        result = await manager.should_process("fid1", "hash1")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_process_true_after_backoff_expires(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        past_retry = datetime.now(UTC) - timedelta(hours=1)
        mock_pool.fetchrow.return_value = _state_row(
            status="error", retry_count=1, retry_after=past_retry
        )
        result = await manager.should_process("fid1", "hash1")
        assert result is True

    @pytest.mark.asyncio
    async def test_mark_error_increments_retry_count(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        await manager.mark_error("fid1", "something failed")
        mock_pool.execute.assert_called_once()
        sql = mock_pool.execute.call_args.args[0]
        assert "retry_count" in sql
        assert "retry_after" in sql

    @pytest.mark.asyncio
    async def test_mark_error_truncates_error_message(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        await manager.mark_error("fid1", "e" * 5000)
        call_args = mock_pool.execute.call_args.args
        # Second positional arg to execute is the error message
        error_arg = call_args[2]
        assert len(error_arg) <= 1000


# ---------------------------------------------------------------------------
# 6. File identity — manifest (chunk ID stability across rename/copy)
# ---------------------------------------------------------------------------


class TestFileIdentityManifest:
    """FileManifest characterizes stable file identity under rename and copy."""

    def test_new_file_gets_fresh_id(self, tmp_path: Path) -> None:
        manifest = FileManifest(tmp_path)
        fid = manifest.get_or_create_id("doc.pdf", "hash_a")
        assert isinstance(fid, str)
        assert len(fid) == 16

    def test_same_path_and_hash_returns_same_id(self, tmp_path: Path) -> None:
        manifest = FileManifest(tmp_path)
        id1 = manifest.get_or_create_id("doc.pdf", "hash_a")
        id2 = manifest.get_or_create_id("doc.pdf", "hash_a")
        assert id1 == id2

    def test_rename_reuses_id_when_original_path_gone(self, tmp_path: Path) -> None:
        manifest = FileManifest(tmp_path)
        original_id = manifest.get_or_create_id("old/doc.pdf", "hash_a")
        manifest.remove("old/doc.pdf")
        renamed_id = manifest.get_or_create_id("new/doc.pdf", "hash_a")
        assert renamed_id == original_id

    def test_copy_gets_new_id_when_original_still_active(self, tmp_path: Path) -> None:
        manifest = FileManifest(tmp_path)
        original_id = manifest.get_or_create_id("folder_a/doc.pdf", "hash_a")
        copy_id = manifest.get_or_create_id("folder_b/doc.pdf", "hash_a")
        assert copy_id != original_id

    def test_manifest_persists_across_reload(self, tmp_path: Path) -> None:
        m1 = FileManifest(tmp_path)
        fid = m1.get_or_create_id("doc.pdf", "hash_a")
        m2 = FileManifest(tmp_path)
        assert m2.get_or_create_id("doc.pdf", "hash_a") == fid

    def test_compute_content_hash_is_deterministic(self) -> None:
        content = b"hello ingestion"
        h1 = compute_content_hash_from_bytes(content)
        h2 = compute_content_hash_from_bytes(content)
        assert h1 == h2
        assert h1 == hashlib.sha256(content).hexdigest()[:16]

    def test_compute_content_hash_different_for_different_content(self) -> None:
        assert compute_content_hash_from_bytes(b"a") != compute_content_hash_from_bytes(b"b")


# ---------------------------------------------------------------------------
# 7. cocoindex removed — module no longer exists
# ---------------------------------------------------------------------------


class TestCocoindexFlowRemoved:
    """Characterize that cocoindex_flow has been removed (#2834)."""

    def test_cocoindex_flow_module_is_gone(self) -> None:
        """cocoindex_flow.py has been deleted; importing it must raise ModuleNotFoundError."""
        import importlib.util

        spec = importlib.util.find_spec("src.ingestion.cocoindex_flow")
        assert spec is None, "src.ingestion.cocoindex_flow should not exist after #2834 removal"

    def test_flow_module_run_once_exists(self) -> None:
        """run_once is still available in the unified flow module."""
        from src.ingestion.unified.flow import run_once

        assert callable(run_once)

    def test_flow_module_run_watch_exists(self) -> None:
        """run_watch is still available in the unified flow module."""
        from src.ingestion.unified.flow import run_watch

        assert callable(run_watch)
