"""Unit tests for src/ingestion/indexer.py."""

from unittest.mock import MagicMock, patch

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

        DocumentIndexer(mock_settings)

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
        # order, price, rooms, area, floor, floors, distance_to_sea, bathrooms
        assert len(integer_calls) == 8

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
        with patch.object(indexer, "_index_batch"):
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


class TestCreatePayloadIndexesError:
    """Test payload index creation error handling."""

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    def test_create_payload_indexes_handles_errors(
        self, mock_settings_cls, mock_qdrant, mock_bge, capsys
    ):
        """Test that payload index creation errors are caught and logged."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        # Make create_payload_index fail
        mock_client.create_payload_index.side_effect = Exception("Index creation failed")
        mock_qdrant.return_value = mock_client

        indexer = DocumentIndexer(mock_settings)
        # Should not raise, just print warning
        indexer._create_payload_indexes("test_collection")

        captured = capsys.readouterr()
        assert "Warning: Could not create payload indexes" in captured.out


class TestIndexBatch:
    """Test _index_batch method."""

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    async def test_index_batch_success(self, mock_settings_cls, mock_qdrant, mock_bge, capsys):
        """Test successful batch indexing."""
        import numpy as np

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.batch_size_embeddings = 8
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        mock_model = MagicMock()
        mock_bge.return_value = mock_model

        indexer = DocumentIndexer(mock_settings)

        # Mock embedding output
        mock_dense = np.array([0.1] * 1024)
        mock_colbert = np.array([[0.1] * 1024])
        mock_lexical = {1: 0.5, 2: 0.3}

        with patch.object(indexer, "_embed_texts") as mock_embed:
            mock_embed.return_value = [
                {
                    "dense_vecs": mock_dense,
                    "colbert_vecs": mock_colbert,
                    "lexical_weights": mock_lexical,
                }
            ]

            chunks = [
                Chunk(
                    text="Test text",
                    chunk_id=0,
                    document_name="doc.pdf",
                    article_number="1",
                    chapter="Chapter 1",
                    section="Section 1",
                    order=0,
                    extra_metadata={"city": "Sofia"},
                )
            ]

            await indexer._index_batch(chunks, "test_collection")

            # Should have called upsert
            mock_client.upsert.assert_called_once()
            assert indexer.stats.indexed_chunks == 1

        captured = capsys.readouterr()
        assert "Indexed 1 chunks" in captured.out

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    async def test_index_batch_handles_errors(
        self, mock_settings_cls, mock_qdrant, mock_bge, capsys
    ):
        """Test batch indexing error handling."""
        import numpy as np

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.batch_size_embeddings = 8
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.upsert.side_effect = Exception("Qdrant error")
        mock_qdrant.return_value = mock_client

        mock_model = MagicMock()
        mock_bge.return_value = mock_model

        indexer = DocumentIndexer(mock_settings)

        # Mock embedding output
        mock_dense = np.array([0.1] * 1024)
        mock_colbert = np.array([[0.1] * 1024])
        mock_lexical = {1: 0.5, 2: 0.3}

        with patch.object(indexer, "_embed_texts") as mock_embed:
            mock_embed.return_value = [
                {
                    "dense_vecs": mock_dense,
                    "colbert_vecs": mock_colbert,
                    "lexical_weights": mock_lexical,
                }
            ]

            chunks = [
                Chunk(
                    text="Test text",
                    chunk_id=0,
                    document_name="doc.pdf",
                    article_number="1",
                )
            ]

            await indexer._index_batch(chunks, "test_collection")

            # Should have recorded failure
            assert indexer.stats.failed_chunks == 1
            assert indexer.stats.indexed_chunks == 0

        captured = capsys.readouterr()
        assert "Failed to index batch" in captured.out


class TestEmbedTexts:
    """Test _embed_texts method."""

    @patch("src.ingestion.indexer.get_bge_m3_model")
    @patch("src.ingestion.indexer.QdrantClient")
    @patch("src.ingestion.indexer.Settings")
    async def test_embed_texts_returns_embeddings(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test _embed_texts returns properly formatted embeddings."""
        import numpy as np

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.batch_size_embeddings = 8
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([[0.1] * 1024, [0.2] * 1024]),
            "lexical_weights": [{1: 0.5, 2: 0.3}, {3: 0.4, 4: 0.2}],
            "colbert_vecs": [np.array([[0.1] * 1024]), np.array([[0.2] * 1024])],
        }
        mock_bge.return_value = mock_model

        indexer = DocumentIndexer(mock_settings)

        result = await indexer._embed_texts(["text 1", "text 2"])

        assert len(result) == 2
        assert "dense_vecs" in result[0]
        assert "lexical_weights" in result[0]
        assert "colbert_vecs" in result[0]

        # Verify model.encode was called correctly
        mock_model.encode.assert_called_once()
        call_args = mock_model.encode.call_args
        assert call_args[0][0] == ["text 1", "text 2"]
        assert call_args[1]["return_dense"] is True
        assert call_args[1]["return_sparse"] is True
        assert call_args[1]["return_colbert_vecs"] is True
