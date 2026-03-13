"""Unit tests for deprecated gdrive_flow helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


pytest.importorskip("fastembed", reason="fastembed not installed")

from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig, ProcessedFile


@pytest.fixture
def flow_config(tmp_path: Path) -> GDriveFlowConfig:
    return GDriveFlowConfig(sync_dir=str(tmp_path), voyage_api_key="test-key")


def test_supported_file_filters_hidden_and_temp(flow_config: GDriveFlowConfig) -> None:
    processor = GDriveFileProcessor(flow_config)

    assert processor._is_supported_file(Path("guide.pdf")) is True
    assert processor._is_supported_file(Path(".hidden.pdf")) is False
    assert processor._is_supported_file(Path("~$draft.docx")) is False
    assert processor._is_supported_file(Path("archive.zip")) is False


def test_compute_file_id_and_content_hash_are_stable(
    flow_config: GDriveFlowConfig, tmp_path: Path
) -> None:
    processor = GDriveFileProcessor(flow_config)
    doc = tmp_path / "folder" / "note.md"
    doc.parent.mkdir()
    doc.write_text("hello", encoding="utf-8")

    assert processor._compute_file_id(doc) == processor._compute_file_id(doc)
    assert processor._compute_content_hash(doc) == processor._compute_content_hash(doc)


@pytest.mark.asyncio
async def test_reconcile_deletions_removes_missing_processed_file(
    flow_config: GDriveFlowConfig,
) -> None:
    processor = GDriveFileProcessor(flow_config)
    processor.indexer = MagicMock()
    processor.indexer.delete_file_points = AsyncMock(return_value=3)
    processor._processed = {
        "kept": ProcessedFile("kept.md", "kept", "hash1", 1, datetime.now(UTC)),
        "deleted": ProcessedFile("deleted.md", "deleted", "hash2", 1, datetime.now(UTC)),
    }

    await processor._reconcile_deletions({"kept"})

    processor.indexer.delete_file_points.assert_awaited_once_with(
        "deleted", flow_config.collection_name
    )
    assert set(processor._processed) == {"kept"}


def test_get_mime_type_falls_back_to_octet_stream() -> None:
    assert GDriveFileProcessor._get_mime_type(Path("doc.md")) == "text/markdown"
    assert GDriveFileProcessor._get_mime_type(Path("blob.unknown")) == "application/octet-stream"
