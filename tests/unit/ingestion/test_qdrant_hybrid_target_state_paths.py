"""State-path tests for QdrantHybridTargetConnector."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.requires_extras


def _mutation(tmp_path: Path):
    from src.ingestion.unified.targets.qdrant_hybrid_target import QdrantHybridTargetValues

    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")
    return QdrantHybridTargetValues(
        abs_path=str(file_path),
        source_path="docs/doc.txt",
        file_name="doc.txt",
        mime_type="text/plain",
        file_size=5,
    )


def test_handle_delete_deletes_points_and_marks_deleted() -> None:
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    writer = MagicMock()
    state_manager = MagicMock()
    spec = QdrantHybridTargetSpec(collection_name="target_collection")

    with patch.object(QdrantHybridTargetConnector, "_get_writer", return_value=writer):
        QdrantHybridTargetConnector._handle_delete_with_state(spec, "file-1", state_manager)

    writer.delete_file_sync.assert_called_once_with("file-1", "target_collection")
    state_manager.mark_deleted_sync.assert_called_once_with("file-1")


def test_handle_upsert_skips_when_claim_returns_none(tmp_path: Path) -> None:
    """When claim_processing_sync returns None (already claimed/up-to-date), skip."""
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    writer = MagicMock()
    docling = MagicMock()
    state_manager = MagicMock()
    state_manager.claim_processing_sync.return_value = None
    mutation = _mutation(tmp_path)
    spec = QdrantHybridTargetSpec(collection_name="target_collection")

    with (
        patch.object(QdrantHybridTargetConnector, "_get_writer", return_value=writer),
        patch.object(QdrantHybridTargetConnector, "_get_docling", return_value=docling),
        patch(
            "src.ingestion.unified.targets.qdrant_hybrid_target.compute_content_hash",
            return_value="hash-1",
        ),
    ):
        QdrantHybridTargetConnector._handle_upsert_with_state(
            spec, "file-1", mutation, state_manager
        )

    state_manager.claim_processing_sync.assert_called_once_with(
        "file-1",
        content_hash="hash-1",
        embedding_model="bge-m3-api",
        pipeline_version="v3.2.1",
        source_path="docs/doc.txt",
        file_name="doc.txt",
        mime_type="text/plain",
        file_size=5,
        collection_name="target_collection",
    )
    docling.chunk_file_sync.assert_not_called()
    writer.upsert_chunks_sync.assert_not_called()


def test_handle_upsert_claim_uses_local_embedding_fingerprint(tmp_path: Path) -> None:
    """claim_processing_sync must pass bge-m3-api and the spec pipeline_version."""
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    state_manager = MagicMock()
    state_manager.claim_processing_sync.return_value = None
    mutation = _mutation(tmp_path)
    spec = QdrantHybridTargetSpec(use_local_embeddings=True, pipeline_version="v-test")

    with (
        patch.object(QdrantHybridTargetConnector, "_get_writer", return_value=MagicMock()),
        patch.object(QdrantHybridTargetConnector, "_get_docling", return_value=MagicMock()),
        patch(
            "src.ingestion.unified.targets.qdrant_hybrid_target.compute_content_hash",
            return_value="hash-1",
        ),
    ):
        QdrantHybridTargetConnector._handle_upsert_with_state(
            spec, "file-1", mutation, state_manager
        )

    state_manager.claim_processing_sync.assert_called_once_with(
        "file-1",
        content_hash="hash-1",
        embedding_model="bge-m3-api",
        pipeline_version="v-test",
        source_path="docs/doc.txt",
        file_name="doc.txt",
        mime_type="text/plain",
        file_size=5,
        collection_name="gdrive_documents_bge",
    )


def test_handle_upsert_new_file_is_processed_and_persists_source_path(tmp_path: Path) -> None:
    """BLOCKER-1/2 behavior: a brand-new file is processed (not skipped) and its
    source_path is persisted (non-NULL) after first-time ingest.

    Uses an in-process fake state store that mirrors the claim/persist contract:
    a new file_id is inserted with the metadata it was given, an existing one is
    skipped. If ``_handle_upsert_with_state`` failed to pass ``source_path`` (the
    BLOCKER-2 regression) the persisted row would have source_path=None and this
    test would fail.
    """
    from src.ingestion.unified.qdrant_writer import WriteStats
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    class _FakeStateManager:
        def __init__(self) -> None:
            self.rows: dict[str, dict] = {}

        def claim_processing_sync(
            self,
            file_id: str,
            *,
            content_hash: str | None = None,
            embedding_model: str | None = None,
            pipeline_version: str | None = None,
            source_path: str | None = None,
            file_name: str | None = None,
            mime_type: str | None = None,
            file_size: int | None = None,
            collection_name: str | None = None,
        ):
            if file_id in self.rows:
                return None  # already claimed / up-to-date
            self.rows[file_id] = {
                "file_id": file_id,
                "status": "processing",
                "source_path": source_path,
                "file_name": file_name,
                "mime_type": mime_type,
                "file_size": file_size,
                "collection_name": collection_name,
                "content_hash": content_hash,
                "retry_count": 0,
            }
            return SimpleNamespace(**self.rows[file_id])

        def mark_indexed_sync(self, file_id: str, chunk_count: int, content_hash: str) -> None:
            self.rows[file_id].update(
                status="indexed", chunk_count=chunk_count, content_hash=content_hash
            )

        def get_state_sync(self, file_id: str):
            return SimpleNamespace(**self.rows[file_id])

    writer = MagicMock()
    writer.upsert_chunks_sync.return_value = WriteStats(points_upserted=3)
    docling = MagicMock()
    docling.chunk_file_sync.return_value = [object()]
    docling.to_ingestion_chunks.return_value = [MagicMock()]
    state_manager = _FakeStateManager()
    mutation = _mutation(tmp_path)
    spec = QdrantHybridTargetSpec(collection_name="target_collection")

    with (
        patch.object(QdrantHybridTargetConnector, "_get_writer", return_value=writer),
        patch.object(QdrantHybridTargetConnector, "_get_docling", return_value=docling),
        patch(
            "src.ingestion.unified.targets.qdrant_hybrid_target.compute_content_hash",
            return_value="hash-1",
        ),
    ):
        QdrantHybridTargetConnector._handle_upsert_with_state(
            spec, "file-1", mutation, state_manager
        )

    # New file was processed (not skipped) → reached the indexed terminal state.
    assert state_manager.rows["file-1"]["status"] == "indexed"
    writer.upsert_chunks_sync.assert_called_once()
    # source_path persisted on first-time ingest (non-NULL).
    assert state_manager.rows["file-1"]["source_path"] == "docs/doc.txt"
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    writer = MagicMock()
    docling = MagicMock()
    docling.chunk_file_sync.return_value = []
    state_manager = MagicMock()
    state_manager.claim_processing_sync.return_value = MagicMock()
    mutation = _mutation(tmp_path)
    spec = QdrantHybridTargetSpec(collection_name="target_collection")

    with (
        patch.object(QdrantHybridTargetConnector, "_get_writer", return_value=writer),
        patch.object(QdrantHybridTargetConnector, "_get_docling", return_value=docling),
        patch(
            "src.ingestion.unified.targets.qdrant_hybrid_target.compute_content_hash",
            return_value="hash-1",
        ),
    ):
        QdrantHybridTargetConnector._handle_upsert_with_state(
            spec, "file-1", mutation, state_manager
        )

    state_manager.mark_indexed_sync.assert_called_once_with("file-1", 0, "hash-1")
    writer.upsert_chunks_sync.assert_not_called()


def test_handle_upsert_writer_error_marks_error(tmp_path: Path) -> None:
    from src.ingestion.unified.qdrant_writer import WriteStats
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    writer = MagicMock()
    writer.upsert_chunks_sync.return_value = WriteStats(errors=["qdrant failed"])
    docling = MagicMock()
    docling.chunk_file_sync.return_value = [object()]
    docling.to_ingestion_chunks.return_value = [MagicMock()]
    state_manager = MagicMock()
    state_manager.claim_processing_sync.return_value = MagicMock()
    state_manager.get_state_sync.return_value = SimpleNamespace(retry_count=0)
    mutation = _mutation(tmp_path)
    spec = QdrantHybridTargetSpec(collection_name="target_collection")

    with (
        patch.object(QdrantHybridTargetConnector, "_get_writer", return_value=writer),
        patch.object(QdrantHybridTargetConnector, "_get_docling", return_value=docling),
        patch(
            "src.ingestion.unified.targets.qdrant_hybrid_target.compute_content_hash",
            return_value="hash-1",
        ),
    ):
        QdrantHybridTargetConnector._handle_upsert_with_state(
            spec, "file-1", mutation, state_manager
        )

    state_manager.mark_error_sync.assert_called_once()
    state_manager.add_to_dlq_sync.assert_not_called()


def test_handle_upsert_moves_to_dlq_after_max_retries(tmp_path: Path) -> None:
    from src.ingestion.unified.qdrant_writer import WriteStats
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    writer = MagicMock()
    writer.upsert_chunks_sync.return_value = WriteStats(errors=["qdrant failed"])
    docling = MagicMock()
    docling.chunk_file_sync.return_value = [object()]
    docling.to_ingestion_chunks.return_value = [MagicMock()]
    state_manager = MagicMock()
    state_manager.claim_processing_sync.return_value = MagicMock()
    state_manager.get_state_sync.return_value = SimpleNamespace(retry_count=3)
    mutation = _mutation(tmp_path)
    spec = QdrantHybridTargetSpec(collection_name="target_collection", max_retries=3)

    with (
        patch.object(QdrantHybridTargetConnector, "_get_writer", return_value=writer),
        patch.object(QdrantHybridTargetConnector, "_get_docling", return_value=docling),
        patch(
            "src.ingestion.unified.targets.qdrant_hybrid_target.compute_content_hash",
            return_value="hash-1",
        ),
    ):
        QdrantHybridTargetConnector._handle_upsert_with_state(
            spec, "file-1", mutation, state_manager
        )

    state_manager.mark_error_sync.assert_called_once()
    state_manager.add_to_dlq_sync.assert_called_once()
    assert state_manager.add_to_dlq_sync.call_args.kwargs == {
        "file_id": "file-1",
        "error_type": "Exception",
        "error_message": "qdrant failed",
        "payload": {"source_path": "docs/doc.txt"},
    }
