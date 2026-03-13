"""Unit tests for src/ingestion/gdrive_indexer.py."""

from __future__ import annotations

import uuid
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from src.ingestion.gdrive_indexer import (
        NAMESPACE_GDRIVE,
        GDriveIndexer,
        IndexStats,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def indexer() -> GDriveIndexer:
    with (
        patch("src.ingestion.gdrive_indexer.QdrantClient"),
        patch("src.ingestion.gdrive_indexer.VoyageService"),
        patch("src.ingestion.gdrive_indexer.SparseTextEmbedding"),
    ):
        idx = GDriveIndexer(qdrant_url="http://localhost:6333", voyage_api_key="test-key")
        # Replace lazily-created mocks with explicit ones
        idx.client = MagicMock()
        idx.voyage_service = AsyncMock()
        idx.sparse_model = MagicMock()
    return idx


# ---------------------------------------------------------------------------
# IndexStats
# ---------------------------------------------------------------------------


class TestIndexStats:
    def test_default_values(self) -> None:
        stats = IndexStats()
        assert stats.total_chunks == 0
        assert stats.indexed_chunks == 0
        assert stats.deleted_points == 0
        assert stats.failed_chunks == 0
        assert stats.errors == []

    def test_errors_list_independent(self) -> None:
        s1 = IndexStats()
        s2 = IndexStats()
        s1.errors.append("err")
        assert s2.errors == []


# ---------------------------------------------------------------------------
# _generate_point_id
# ---------------------------------------------------------------------------


class TestGeneratePointId:
    def test_returns_uuid_string(self, indexer: GDriveIndexer) -> None:
        point_id = indexer._generate_point_id("file123", "chunk_0")
        uuid.UUID(point_id)  # raises if invalid

    def test_deterministic(self, indexer: GDriveIndexer) -> None:
        id1 = indexer._generate_point_id("file123", "chunk_0")
        id2 = indexer._generate_point_id("file123", "chunk_0")
        assert id1 == id2

    def test_different_chunk_different_id(self, indexer: GDriveIndexer) -> None:
        id1 = indexer._generate_point_id("file123", "chunk_0")
        id2 = indexer._generate_point_id("file123", "chunk_1")
        assert id1 != id2

    def test_different_file_different_id(self, indexer: GDriveIndexer) -> None:
        id1 = indexer._generate_point_id("fileA", "chunk_0")
        id2 = indexer._generate_point_id("fileB", "chunk_0")
        assert id1 != id2

    def test_uses_namespace_gdrive(self, indexer: GDriveIndexer) -> None:
        point_id = indexer._generate_point_id("file", "chunk")
        expected = str(uuid.uuid5(NAMESPACE_GDRIVE, "file::chunk"))
        assert point_id == expected


# ---------------------------------------------------------------------------
# delete_file_points
# ---------------------------------------------------------------------------


class TestDeleteFilePoints:
    async def test_returns_zero_when_no_points(self, indexer: GDriveIndexer) -> None:
        count_result = MagicMock()
        count_result.count = 0
        indexer.client.count.return_value = count_result

        result = await indexer.delete_file_points("file123")
        assert result == 0
        indexer.client.delete.assert_not_called()

    async def test_deletes_when_points_exist(self, indexer: GDriveIndexer) -> None:
        count_result = MagicMock()
        count_result.count = 5
        indexer.client.count.return_value = count_result

        result = await indexer.delete_file_points("file123", "my_collection")
        assert result == 5
        indexer.client.delete.assert_called_once()

    async def test_uses_default_collection(self, indexer: GDriveIndexer) -> None:
        count_result = MagicMock()
        count_result.count = 0
        indexer.client.count.return_value = count_result

        await indexer.delete_file_points("file123")
        call_kwargs = indexer.client.count.call_args[1]
        assert call_kwargs["collection_name"] == GDriveIndexer.DEFAULT_COLLECTION


# ---------------------------------------------------------------------------
# index_file_chunks
# ---------------------------------------------------------------------------


class TestIndexFileChunks:
    def _make_chunk(self, text: str = "test text") -> MagicMock:
        chunk = MagicMock()
        chunk.text = text
        chunk.document_name = "test.pdf"
        chunk.chunk_id = "c1"
        chunk.section = None
        chunk.page_range = None
        chunk.extra_metadata = {}
        return chunk

    async def test_empty_chunks_returns_zero_indexed(self, indexer: GDriveIndexer) -> None:
        stats = await indexer.index_file_chunks(chunks=[], file_id="f1")
        assert stats.indexed_chunks == 0
        assert stats.total_chunks == 0

    async def test_indexes_chunks_successfully(self, indexer: GDriveIndexer) -> None:
        # Mock delete
        count_result = MagicMock()
        count_result.count = 0
        indexer.client.count.return_value = count_result

        # Mock embeddings
        indexer.voyage_service.embed_documents = AsyncMock(return_value=[[0.1] * 1024])
        sparse_emb = MagicMock()
        sparse_emb.indices = MagicMock()
        sparse_emb.indices.tolist.return_value = [1, 2, 3]
        sparse_emb.values = MagicMock()
        sparse_emb.values.tolist.return_value = [0.1, 0.2, 0.3]
        indexer.sparse_model.embed.return_value = iter([sparse_emb])

        chunks = [self._make_chunk("hello world")]
        stats = await indexer.index_file_chunks(chunks=chunks, file_id="f1")

        assert stats.indexed_chunks == 1
        assert stats.total_chunks == 1
        indexer.client.upsert.assert_called_once()

    async def test_handles_exception_and_records_error(self, indexer: GDriveIndexer) -> None:
        count_result = MagicMock()
        count_result.count = 0
        indexer.client.count.return_value = count_result

        indexer.voyage_service.embed_documents = AsyncMock(side_effect=RuntimeError("API down"))

        chunks = [self._make_chunk()]
        stats = await indexer.index_file_chunks(chunks=chunks, file_id="f1")

        assert stats.failed_chunks == 1
        assert len(stats.errors) == 1
        assert "API down" in stats.errors[0]
