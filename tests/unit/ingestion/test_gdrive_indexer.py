"""Unit tests for gdrive_indexer helper behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


pytest.importorskip("fastembed", reason="fastembed not installed")

from src.ingestion.gdrive_indexer import GDriveIndexer


def _make_indexer() -> GDriveIndexer:
    indexer = GDriveIndexer.__new__(GDriveIndexer)
    indexer.client = MagicMock()
    indexer.DEFAULT_COLLECTION = "gdrive_documents_bge"
    return indexer


def test_generate_point_id_is_deterministic() -> None:
    indexer = _make_indexer()

    assert indexer._generate_point_id("file-1", "chunk-0") == indexer._generate_point_id(
        "file-1", "chunk-0"
    )
    assert indexer._generate_point_id("file-1", "chunk-0") != indexer._generate_point_id(
        "file-1", "chunk-1"
    )


@pytest.mark.asyncio
async def test_delete_file_points_skips_delete_when_collection_has_no_points() -> None:
    indexer = _make_indexer()
    indexer.client.count.return_value = SimpleNamespace(count=0)

    deleted = await indexer.delete_file_points("file-1")

    assert deleted == 0
    indexer.client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_file_points_deletes_existing_points() -> None:
    indexer = _make_indexer()
    indexer.client.count.return_value = SimpleNamespace(count=2)

    deleted = await indexer.delete_file_points("file-1", "custom")

    assert deleted == 2
    indexer.client.delete.assert_called_once()
    assert indexer.client.delete.call_args.kwargs["collection_name"] == "custom"
