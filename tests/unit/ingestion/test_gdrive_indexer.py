"""Tests for Google Drive hybrid indexer.

DEPRECATED: src.ingestion.gdrive_indexer is superseded by unified pipeline.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.chunker import Chunk


pytestmark = pytest.mark.legacy_api


class TestGDriveIndexerPointId:
    """Test deterministic point ID generation."""

    def test_generate_point_id_is_deterministic(self):
        """Point ID should be deterministic based on file_id + chunk_location."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        indexer = GDriveIndexer.__new__(GDriveIndexer)

        id1 = indexer._generate_point_id("file123", "chunk_0")
        id2 = indexer._generate_point_id("file123", "chunk_0")
        id3 = indexer._generate_point_id("file123", "chunk_1")

        assert id1 == id2  # Same inputs = same ID
        assert id1 != id3  # Different chunk = different ID

    def test_generate_point_id_is_valid_uuid(self):
        """Point ID should be a valid UUID string."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        indexer = GDriveIndexer.__new__(GDriveIndexer)

        point_id = indexer._generate_point_id("file123", "chunk_0")

        # Should not raise
        parsed = uuid.UUID(point_id)
        assert str(parsed) == point_id

    def test_generate_point_id_different_files(self):
        """Different file_ids should produce different point IDs."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        indexer = GDriveIndexer.__new__(GDriveIndexer)

        id1 = indexer._generate_point_id("file_a", "chunk_0")
        id2 = indexer._generate_point_id("file_b", "chunk_0")

        assert id1 != id2


class TestGDriveIndexerInit:
    """Test GDriveIndexer initialization."""

    @patch("src.ingestion.gdrive_indexer.QdrantClient")
    @patch("src.ingestion.gdrive_indexer.VoyageService")
    @patch("src.ingestion.gdrive_indexer.SparseTextEmbedding")
    def test_init_with_defaults(self, mock_sparse, mock_voyage, mock_qdrant):
        """Test indexer initializes with environment defaults."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        with patch.dict(
            "os.environ",
            {
                "QDRANT_URL": "http://test:6333",
                "VOYAGE_API_KEY": "test-key",
            },
        ):
            indexer = GDriveIndexer()

            assert indexer.qdrant_url == "http://test:6333"
            mock_qdrant.assert_called_once()
            mock_voyage.assert_called_once()
            mock_sparse.assert_called_once()

    @patch("src.ingestion.gdrive_indexer.QdrantClient")
    @patch("src.ingestion.gdrive_indexer.VoyageService")
    @patch("src.ingestion.gdrive_indexer.SparseTextEmbedding")
    def test_init_with_api_key(self, mock_sparse, mock_voyage, mock_qdrant):
        """Test indexer uses API key when provided."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        GDriveIndexer(
            qdrant_url="http://cloud:6333",
            qdrant_api_key="secret",
            voyage_api_key="voyage-key",
        )

        mock_qdrant.assert_called_with(url="http://cloud:6333", api_key="secret", timeout=120)


class TestGDriveIndexerDeleteFilePoints:
    """Test delete by file_id functionality."""

    @pytest.fixture
    def indexer(self):
        """Create indexer with mocked dependencies."""
        with patch("src.ingestion.gdrive_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.gdrive_indexer.VoyageService"):
                with patch("src.ingestion.gdrive_indexer.SparseTextEmbedding"):
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client

                    from src.ingestion.gdrive_indexer import GDriveIndexer

                    idx = GDriveIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    yield idx

    async def test_delete_file_points_calls_qdrant_delete(self, indexer):
        """Delete should call Qdrant delete with proper filter."""
        # Mock count to return existing points
        mock_count = MagicMock()
        mock_count.count = 5
        indexer.client.count.return_value = mock_count

        deleted = await indexer.delete_file_points("file_123", "test_collection")

        assert deleted == 5
        indexer.client.delete.assert_called_once()

    async def test_delete_file_points_no_points(self, indexer):
        """Delete should skip when no points exist."""
        mock_count = MagicMock()
        mock_count.count = 0
        indexer.client.count.return_value = mock_count

        deleted = await indexer.delete_file_points("file_123", "test_collection")

        assert deleted == 0
        indexer.client.delete.assert_not_called()


class TestGDriveIndexerIndexFileChunks:
    """Test index_file_chunks with replace semantics."""

    @pytest.fixture
    def indexer(self):
        """Create indexer with mocked dependencies."""
        with patch("src.ingestion.gdrive_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.gdrive_indexer.VoyageService") as mock_voyage:
                with patch("src.ingestion.gdrive_indexer.SparseTextEmbedding") as mock_sparse:
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client

                    # Mock count for delete
                    mock_count = MagicMock()
                    mock_count.count = 0
                    mock_client.count.return_value = mock_count

                    # Mock voyage embeddings
                    mock_voyage_inst = AsyncMock()
                    mock_voyage_inst.embed_documents = AsyncMock(return_value=[[0.1] * 1024])
                    mock_voyage.return_value = mock_voyage_inst

                    # Mock sparse embedding
                    mock_sparse_inst = MagicMock()
                    mock_sparse_emb = MagicMock()
                    mock_sparse_emb.indices.tolist.return_value = [1, 2, 3]
                    mock_sparse_emb.values.tolist.return_value = [0.5, 0.3, 0.2]
                    mock_sparse_inst.embed.return_value = [mock_sparse_emb]
                    mock_sparse.return_value = mock_sparse_inst

                    from src.ingestion.gdrive_indexer import GDriveIndexer

                    idx = GDriveIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    idx.voyage_service = mock_voyage_inst
                    idx.sparse_model = mock_sparse_inst
                    yield idx

    async def test_index_file_chunks_single_chunk(self, indexer):
        """Test indexing a single chunk."""
        chunks = [
            Chunk(
                text="test chunk content",
                chunk_id=0,
                document_name="test.pdf",
                article_number="",
                extra_metadata={"file_id": "gdrive_file_123"},
            )
        ]

        stats = await indexer.index_file_chunks(
            chunks=chunks,
            file_id="gdrive_file_123",
            collection_name="test_collection",
        )

        assert stats.total_chunks == 1
        assert stats.indexed_chunks == 1
        assert stats.failed_chunks == 0
        indexer.client.upsert.assert_called_once()

    async def test_delete_called_before_upsert(self, indexer):
        """Indexer should delete existing points before upserting new ones."""
        # Mock count to show existing points
        mock_count = MagicMock()
        mock_count.count = 3
        indexer.client.count.return_value = mock_count

        chunks = [
            Chunk(
                text="test chunk",
                chunk_id=0,
                document_name="test.pdf",
                article_number="",
                extra_metadata={"file_id": "gdrive_file_123"},
            )
        ]

        await indexer.index_file_chunks(
            chunks=chunks,
            file_id="gdrive_file_123",
            collection_name="test_collection",
        )

        # Verify delete was called before upsert
        calls = indexer.client.method_calls
        call_names = [c[0] for c in calls]

        # Find indices of delete and upsert
        delete_idx = None
        upsert_idx = None
        for i, name in enumerate(call_names):
            if "delete" in name.lower():
                delete_idx = i
            if "upsert" in name.lower():
                upsert_idx = i

        assert delete_idx is not None, "delete was not called"
        assert upsert_idx is not None, "upsert was not called"
        assert delete_idx < upsert_idx, "delete should be called before upsert"

    async def test_index_empty_chunks_returns_warning(self, indexer):
        """Indexing empty chunks should return early with warning."""
        stats = await indexer.index_file_chunks(
            chunks=[],
            file_id="gdrive_file_123",
            collection_name="test_collection",
        )

        assert stats.total_chunks == 0
        assert stats.indexed_chunks == 0
        indexer.client.upsert.assert_not_called()

    async def test_index_handles_embedding_error(self, indexer):
        """Indexing should handle embedding errors gracefully."""
        indexer.voyage_service.embed_documents.side_effect = Exception("API error")

        chunks = [
            Chunk(
                text="test chunk",
                chunk_id=0,
                document_name="test.pdf",
                article_number="",
            )
        ]

        stats = await indexer.index_file_chunks(
            chunks=chunks,
            file_id="gdrive_file_123",
            collection_name="test_collection",
        )

        assert stats.failed_chunks == 1
        assert len(stats.errors) == 1
        assert "API error" in stats.errors[0]


class TestIndexStats:
    """Test IndexStats dataclass."""

    def test_index_stats_defaults(self):
        """Test IndexStats has correct defaults."""
        from src.ingestion.gdrive_indexer import IndexStats

        stats = IndexStats()

        assert stats.total_chunks == 0
        assert stats.indexed_chunks == 0
        assert stats.deleted_points == 0
        assert stats.failed_chunks == 0
        assert stats.duration_seconds == 0.0
        assert stats.errors == []

    def test_index_stats_custom_values(self):
        """Test IndexStats accepts custom values."""
        from src.ingestion.gdrive_indexer import IndexStats

        stats = IndexStats(
            total_chunks=100,
            indexed_chunks=95,
            deleted_points=10,
            failed_chunks=5,
            duration_seconds=10.5,
            errors=["error1"],
        )

        assert stats.total_chunks == 100
        assert stats.indexed_chunks == 95
        assert stats.deleted_points == 10
