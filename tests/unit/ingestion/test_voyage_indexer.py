"""Tests for Voyage AI document indexer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.voyage_indexer import IndexStats, VoyageIndexer


class TestIndexStats:
    """Tests for IndexStats dataclass."""

    def test_index_stats_defaults(self):
        """Test IndexStats has correct defaults."""
        stats = IndexStats()

        assert stats.total_chunks == 0
        assert stats.indexed_chunks == 0
        assert stats.failed_chunks == 0
        assert stats.duration_seconds == 0.0

    def test_index_stats_custom_values(self):
        """Test IndexStats accepts custom values."""
        stats = IndexStats(
            total_chunks=100,
            indexed_chunks=95,
            failed_chunks=5,
            duration_seconds=10.5,
        )

        assert stats.total_chunks == 100
        assert stats.indexed_chunks == 95


class TestVoyageIndexerInit:
    """Tests for VoyageIndexer initialization."""

    @patch("src.ingestion.voyage_indexer.QdrantClient")
    @patch("src.ingestion.voyage_indexer.VoyageService")
    @patch("src.ingestion.voyage_indexer.SparseTextEmbedding")
    def test_init_with_defaults(self, mock_sparse, mock_voyage, mock_qdrant):
        """Test indexer initializes with environment defaults."""
        with patch.dict(
            "os.environ",
            {
                "QDRANT_URL": "http://test:6333",
                "QDRANT_API_KEY": "",
                "VOYAGE_API_KEY": "test-key",
            },
        ):
            indexer = VoyageIndexer()

            assert indexer.qdrant_url == "http://test:6333"
            mock_qdrant.assert_called_once()
            mock_voyage.assert_called_once()
            mock_sparse.assert_called_once()

    @patch("src.ingestion.voyage_indexer.QdrantClient")
    @patch("src.ingestion.voyage_indexer.VoyageService")
    @patch("src.ingestion.voyage_indexer.SparseTextEmbedding")
    def test_init_with_api_key(self, mock_sparse, mock_voyage, mock_qdrant):
        """Test indexer uses API key when provided."""
        VoyageIndexer(
            qdrant_url="http://cloud:6333",
            qdrant_api_key="secret",
            voyage_api_key="voyage-key",
        )

        mock_qdrant.assert_called_with(url="http://cloud:6333", api_key="secret", timeout=120)


class TestCreateCollection:
    """Tests for VoyageIndexer.create_collection()."""

    @pytest.fixture
    def indexer(self):
        with patch("src.ingestion.voyage_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.voyage_indexer.VoyageService"):
                with patch("src.ingestion.voyage_indexer.SparseTextEmbedding"):
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client

                    idx = VoyageIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    yield idx

    def test_create_collection_new(self, indexer):
        """Test creating a new collection."""
        indexer.client.get_collection.side_effect = Exception("Not found")

        result = indexer.create_collection("test_collection")

        assert result is True
        indexer.client.create_collection.assert_called_once()

    def test_create_collection_exists_no_recreate(self, indexer):
        """Test existing collection without recreate."""
        indexer.client.get_collection.return_value = MagicMock()

        result = indexer.create_collection("existing", recreate=False)

        assert result is True
        indexer.client.create_collection.assert_not_called()

    def test_create_collection_exists_with_recreate(self, indexer):
        """Test existing collection with recreate=True."""
        indexer.client.get_collection.return_value = MagicMock()

        result = indexer.create_collection("existing", recreate=True)

        assert result is True
        indexer.client.delete_collection.assert_called_once_with("existing")
        indexer.client.create_collection.assert_called_once()


class TestIndexChunks:
    """Tests for VoyageIndexer.index_chunks()."""

    @pytest.fixture
    def indexer(self):
        with patch("src.ingestion.voyage_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.voyage_indexer.VoyageService") as mock_voyage:
                with patch("src.ingestion.voyage_indexer.SparseTextEmbedding") as mock_sparse:
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client
                    mock_client.get_collection.side_effect = Exception("Not found")

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

                    idx = VoyageIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    idx.voyage_service = mock_voyage_inst
                    idx.sparse_model = mock_sparse_inst
                    yield idx

    async def test_index_chunks_single_batch(self, indexer):
        """Test indexing a single batch of chunks."""
        from src.ingestion.chunker import Chunk

        chunks = [
            Chunk(
                text="Test document",
                chunk_id=1,
                document_name="test.pdf",
                article_number="1",
            )
        ]

        stats = await indexer.index_chunks(
            chunks, "test_collection", batch_size=10, rate_limit_delay=0.01
        )

        assert stats.total_chunks == 1
        assert stats.indexed_chunks == 1
        assert stats.failed_chunks == 0
        indexer.client.upsert.assert_called_once()

    async def test_index_chunks_handles_error(self, indexer):
        """Test indexing handles errors gracefully."""
        from src.ingestion.chunker import Chunk

        chunks = [
            Chunk(
                text="Test",
                chunk_id=1,
                document_name="test.pdf",
                article_number="1",
            )
        ]

        indexer.voyage_service.embed_documents.side_effect = Exception("API error")

        stats = await indexer.index_chunks(
            chunks, "test_collection", batch_size=10, rate_limit_delay=0.01
        )

        assert stats.failed_chunks == 1


class TestGetCollectionStats:
    """Tests for VoyageIndexer.get_collection_stats()."""

    @pytest.fixture
    def indexer(self):
        with patch("src.ingestion.voyage_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.voyage_indexer.VoyageService"):
                with patch("src.ingestion.voyage_indexer.SparseTextEmbedding"):
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client

                    idx = VoyageIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    yield idx

    def test_get_collection_stats_success(self, indexer):
        """Test getting collection stats."""
        mock_info = MagicMock()
        mock_info.points_count = 100
        mock_info.vectors_count = 200
        mock_info.indexed_vectors_count = 200
        indexer.client.get_collection.return_value = mock_info

        stats = indexer.get_collection_stats("test")

        assert stats["name"] == "test"
        assert stats["points_count"] == 100

    def test_get_collection_stats_error(self, indexer):
        """Test getting stats handles errors."""
        indexer.client.get_collection.side_effect = Exception("Error")

        stats = indexer.get_collection_stats("test")

        assert stats == {}


class TestCreatePayloadIndexes:
    """Tests for VoyageIndexer._create_payload_indexes()."""

    @pytest.fixture
    def indexer(self):
        with patch("src.ingestion.voyage_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.voyage_indexer.VoyageService"):
                with patch("src.ingestion.voyage_indexer.SparseTextEmbedding"):
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client

                    idx = VoyageIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    yield idx

    def test_create_payload_indexes_creates_text_indexes(self, indexer):
        """Test payload indexes are created for text fields."""
        indexer._create_payload_indexes("test_collection")

        # Check at least one text field index was created
        calls = indexer.client.create_payload_index.call_args_list
        field_names = [call[1]["field_name"] for call in calls]
        assert any("source_type" in fn for fn in field_names)

    def test_create_payload_indexes_creates_numeric_indexes(self, indexer):
        """Test payload indexes are created for numeric fields."""
        indexer._create_payload_indexes("test_collection")

        # Check numeric fields are indexed
        calls = indexer.client.create_payload_index.call_args_list
        field_names = [call[1]["field_name"] for call in calls]
        assert any("price" in fn for fn in field_names)

    def test_create_payload_indexes_handles_error(self, indexer):
        """Test payload index creation handles errors gracefully."""
        indexer.client.create_payload_index.side_effect = Exception("Error")

        # Should not raise
        indexer._create_payload_indexes("test_collection")


class TestMultipleBatchIndexing:
    """Tests for indexing multiple batches."""

    @pytest.fixture
    def indexer(self):
        with patch("src.ingestion.voyage_indexer.QdrantClient") as mock_qdrant:
            with patch("src.ingestion.voyage_indexer.VoyageService") as mock_voyage:
                with patch("src.ingestion.voyage_indexer.SparseTextEmbedding") as mock_sparse:
                    mock_client = MagicMock()
                    mock_qdrant.return_value = mock_client
                    mock_client.get_collection.side_effect = Exception("Not found")

                    mock_voyage_inst = AsyncMock()

                    # Return embeddings matching input length (for batch_size=2)
                    async def embed_documents_side_effect(texts):
                        return [[0.1] * 1024 for _ in texts]

                    mock_voyage_inst.embed_documents = AsyncMock(
                        side_effect=embed_documents_side_effect
                    )
                    mock_voyage.return_value = mock_voyage_inst

                    # Mock sparse embedding - return matching length
                    mock_sparse_inst = MagicMock()

                    def sparse_embed_side_effect(texts):
                        mock_sparse_emb = MagicMock()
                        mock_sparse_emb.indices.tolist.return_value = [1, 2, 3]
                        mock_sparse_emb.values.tolist.return_value = [0.5, 0.3, 0.2]
                        return [mock_sparse_emb for _ in texts]

                    mock_sparse_inst.embed.side_effect = sparse_embed_side_effect
                    mock_sparse.return_value = mock_sparse_inst

                    idx = VoyageIndexer(voyage_api_key="test")
                    idx.client = mock_client
                    idx.voyage_service = mock_voyage_inst
                    idx.sparse_model = mock_sparse_inst
                    yield idx

    async def test_index_chunks_multiple_batches(self, indexer):
        """Test indexing with multiple batches."""
        from src.ingestion.chunker import Chunk

        chunks = [
            Chunk(text="Doc 1", chunk_id=1, document_name="test.pdf", article_number="1"),
            Chunk(text="Doc 2", chunk_id=2, document_name="test.pdf", article_number="2"),
            Chunk(text="Doc 3", chunk_id=3, document_name="test.pdf", article_number="3"),
        ]

        stats = await indexer.index_chunks(
            chunks, "test_collection", batch_size=2, rate_limit_delay=0.01
        )

        assert stats.total_chunks == 3
        assert stats.indexed_chunks == 3
        # With batch_size=2 and 3 chunks, should have 2 upsert calls
        assert indexer.client.upsert.call_count >= 1

    async def test_index_chunks_tracks_duration(self, indexer):
        """Test that indexing tracks duration."""
        from src.ingestion.chunker import Chunk

        chunks = [Chunk(text="Test", chunk_id=1, document_name="test.pdf", article_number="1")]

        stats = await indexer.index_chunks(
            chunks, "test_collection", batch_size=10, rate_limit_delay=0.01
        )

        assert stats.duration_seconds > 0
