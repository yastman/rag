"""Unit tests for src/ingestion/indexer.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.chunker import Chunk
from src.ingestion.indexer import DocumentIndexer, IndexStats


class TestIndexStats:
    """Test IndexStats dataclass."""

    def test_index_stats_defaults(self):
        """Test IndexStats default values."""
        stats = IndexStats()

        assert stats.total_chunks == 0
        assert stats.indexed_chunks == 0
        assert stats.failed_chunks == 0
        assert stats.total_tokens == 0
        assert stats.total_cost == 0.0
        assert stats.duration_seconds == 0.0

    def test_index_stats_custom_values(self):
        """Test IndexStats with custom values."""
        stats = IndexStats(
            total_chunks=100,
            indexed_chunks=95,
            failed_chunks=5,
            duration_seconds=30.5,
        )

        assert stats.total_chunks == 100
        assert stats.indexed_chunks == 95
        assert stats.failed_chunks == 5
        assert stats.duration_seconds == 30.5


class TestDocumentIndexerInit:
    """Test DocumentIndexer initialization."""

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_init_creates_client(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that initialization creates Qdrant client."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        indexer = DocumentIndexer(mock_settings)

        mock_qdrant.assert_called_once_with(
            "http://localhost:6333",
            api_key="test-key",
            timeout=120,
        )

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_init_loads_embedding_model(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that initialization loads BGE-M3 model."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        DocumentIndexer(mock_settings)

        mock_bge.assert_called_once_with(use_fp16=True)


class TestCreateCollection:
    """Test collection creation."""

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_create_collection_new(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test creating a new collection."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("Not found")
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        result = indexer.create_collection("test_collection")

        assert result is True
        mock_client.create_collection.assert_called_once()

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_create_collection_exists_no_recreate(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test existing collection without recreate flag."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.get_collection.return_value = MagicMock()  # Collection exists
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        result = indexer.create_collection("test_collection", recreate=False)

        assert result is True
        mock_client.create_collection.assert_not_called()
        mock_client.delete_collection.assert_not_called()

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_create_collection_exists_with_recreate(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test existing collection with recreate flag."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.get_collection.return_value = MagicMock()  # Collection exists
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        result = indexer.create_collection("test_collection", recreate=True)

        assert result is True
        mock_client.delete_collection.assert_called_once_with("test_collection")
        mock_client.create_collection.assert_called_once()


class TestCreatePayloadIndexes:
    """Test payload index creation."""

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_creates_keyword_indexes(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that keyword indexes are created."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        indexer._create_payload_indexes("test_collection")

        # Should create keyword indexes for text fields
        keyword_calls = [
            call
            for call in mock_client.create_payload_index.call_args_list
            if call[1].get("field_schema") == "keyword"
        ]
        assert len(keyword_calls) >= 4  # article_number, document_name, city, source_type

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_creates_integer_indexes(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that integer indexes are created for numeric fields."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        indexer._create_payload_indexes("test_collection")

        # Should create integer indexes for numeric fields
        integer_calls = [
            call
            for call in mock_client.create_payload_index.call_args_list
            if call[1].get("field_schema") == "integer"
        ]
        # price, rooms, area, floor, floors, distance_to_sea, bathrooms
        assert len(integer_calls) == 7

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_creates_bool_indexes(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that boolean indexes are created."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        indexer._create_payload_indexes("test_collection")

        # Should create bool indexes for furnished, year_round
        bool_calls = [
            call
            for call in mock_client.create_payload_index.call_args_list
            if call[1].get("field_schema") == "bool"
        ]
        assert len(bool_calls) == 2


class TestIndexChunks:
    """Test chunk indexing."""

    @pytest.mark.asyncio
    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    async def test_index_chunks_returns_stats(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that index_chunks returns IndexStats."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.batch_size_documents = 16
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("Not found")
        mock_qdrant.return_value = mock_client

        mock_model = MagicMock()
        mock_bge.return_value = mock_model

        indexer = DocumentIndexer(mock_settings)

        # Mock _index_batch to avoid actual embedding
        with patch.object(indexer, "_index_batch") as mock_index_batch:
            chunks = [
                Chunk(text="Text 1", chunk_id=0, document_name="doc.pdf", article_number="1"),
                Chunk(text="Text 2", chunk_id=1, document_name="doc.pdf", article_number="2"),
            ]

            stats = await indexer.index_chunks(chunks, "test_collection")

            assert isinstance(stats, IndexStats)
            assert stats.total_chunks == 2


class TestGetCollectionStats:
    """Test collection statistics retrieval."""

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_get_collection_stats_success(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test successful stats retrieval."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_info = MagicMock()
        mock_info.points_count = 100
        mock_info.vectors_count = 300  # 3 vectors per point
        mock_info.indexed_vectors_count = 300

        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_info
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        stats = indexer.get_collection_stats("test_collection")

        assert stats["name"] == "test_collection"
        assert stats["points_count"] == 100
        assert stats["vectors_count"] == 300

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_get_collection_stats_error(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test stats retrieval on error returns empty dict."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("Not found")
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        stats = indexer.get_collection_stats("nonexistent")

        assert stats == {}
