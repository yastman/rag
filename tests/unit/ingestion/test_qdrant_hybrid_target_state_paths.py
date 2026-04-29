"""State-path tests for QdrantHybridTargetConnector."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [
    pytest.mark.requires_extras,
    pytest.mark.skipif(
        importlib.util.find_spec("cocoindex") is None,
        reason="cocoindex not installed (ingest extra)",
    ),
]


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


def test_handle_upsert_skips_unchanged_file_before_parsing(tmp_path: Path) -> None:
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    writer = MagicMock()
    docling = MagicMock()
    state_manager = MagicMock()
    state_manager.should_process_sync.return_value = False
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

    state_manager.should_process_sync.assert_called_once_with("file-1", "hash-1")
    state_manager.upsert_state_sync.assert_not_called()
    docling.chunk_file_sync.assert_not_called()
    writer.upsert_chunks_sync.assert_not_called()


def test_handle_upsert_empty_chunks_marks_indexed_zero(tmp_path: Path) -> None:
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
    )

    writer = MagicMock()
    docling = MagicMock()
    docling.chunk_file_sync.return_value = []
    state_manager = MagicMock()
    state_manager.should_process_sync.return_value = True
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

    state_manager.upsert_state_sync.assert_called_once()
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
    state_manager.should_process_sync.return_value = True
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
    state_manager.should_process_sync.return_value = True
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
