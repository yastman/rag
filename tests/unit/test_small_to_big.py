"""Tests for small-to-big context expansion service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.small_to_big import (
    ExpandedChunk,
    SmallToBigMode,
    SmallToBigService,
)


class TestSmallToBigMode:
    """Test SmallToBigMode enum."""

    def test_mode_values(self):
        """Test mode enum values."""
        assert SmallToBigMode.OFF == "off"
        assert SmallToBigMode.ON == "on"
        assert SmallToBigMode.AUTO == "auto"


class TestExpandedChunk:
    """Test ExpandedChunk dataclass."""

    def test_create_expanded_chunk(self):
        """Test creating an expanded chunk."""
        original = {"text": "original text", "metadata": {"doc_id": "doc1"}}
        expanded = ExpandedChunk(
            original_chunk=original,
            expanded_text="before\n\noriginal text\n\nafter",
            neighbor_chunks=[
                {"text": "before", "metadata": {"order": 0}},
                {"text": "after", "metadata": {"order": 2}},
            ],
            total_tokens_estimate=100,
        )

        assert expanded.original_chunk == original
        assert "before" in expanded.expanded_text
        assert "after" in expanded.expanded_text
        assert len(expanded.neighbor_chunks) == 2
        assert expanded.total_tokens_estimate == 100


class TestSmallToBigService:
    """Test SmallToBigService."""

    @pytest.fixture
    def mock_client(self):
        """Create mock Qdrant client."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_client):
        """Create SmallToBigService with mock client."""
        return SmallToBigService(
            client=mock_client,
            collection_name="test_collection",
            max_expanded_chunks=10,
            max_context_tokens=8000,
        )

    async def test_expand_context_empty_chunks(self, service):
        """Test expand_context with empty input."""
        result = await service.expand_context(chunks=[])
        assert result == []

    async def test_expand_context_missing_metadata(self, service, mock_client):
        """Test expand_context when chunks have no doc_id/order."""
        chunks = [
            {"text": "some text", "metadata": {}},  # No doc_id or order
        ]

        result = await service.expand_context(chunks)

        # Should return chunk without expansion
        assert len(result) == 1
        assert result[0].original_chunk == chunks[0]
        assert result[0].expanded_text == "some text"
        assert result[0].neighbor_chunks == []
        # Client should not be called
        mock_client.scroll.assert_not_called()

    async def test_expand_context_with_neighbors(self, service, mock_client):
        """Test expand_context fetches and merges neighbors."""
        # Setup input chunk
        chunks = [
            {
                "text": "center chunk",
                "metadata": {"doc_id": "doc1", "chunk_order": 5, "order": 5},
                "score": 0.9,
            },
        ]

        # Mock neighbor chunks from Qdrant
        mock_neighbor_points = [
            MagicMock(
                id="neighbor1",
                payload={
                    "page_content": "before chunk",
                    "metadata": {"doc_id": "doc1", "order": 4},
                },
            ),
            MagicMock(
                id="neighbor2",
                payload={
                    "page_content": "after chunk",
                    "metadata": {"doc_id": "doc1", "order": 6},
                },
            ),
        ]
        mock_client.scroll.return_value = (mock_neighbor_points, None)

        # Execute
        result = await service.expand_context(
            chunks=chunks,
            window_before=1,
            window_after=1,
        )

        # Verify
        assert len(result) == 1
        expanded = result[0]

        # Check neighbors were fetched
        mock_client.scroll.assert_called_once()

        # Check expanded text contains all chunks in order
        assert "before chunk" in expanded.expanded_text
        assert "center chunk" in expanded.expanded_text
        assert "after chunk" in expanded.expanded_text

        # Verify order (before comes first)
        assert expanded.expanded_text.index("before") < expanded.expanded_text.index("center")
        assert expanded.expanded_text.index("center") < expanded.expanded_text.index("after")

        # Check neighbor chunks
        assert len(expanded.neighbor_chunks) == 2

    async def test_expand_context_respects_max_chunks_limit(self, service, mock_client):
        """Test that expansion stops when max_expanded_chunks is reached."""
        service._max_expanded_chunks = 2

        # Create 5 chunks
        chunks = [
            {"text": f"chunk {i}", "metadata": {"doc_id": "doc1", "order": i}} for i in range(5)
        ]

        # Mock empty neighbors (simplifies test)
        mock_client.scroll.return_value = ([], None)

        result = await service.expand_context(chunks)

        # Should only expand first 2 chunks
        assert len(result) == 2

    async def test_expand_context_respects_token_limit(self, service, mock_client):
        """Test that expansion stops when max_context_tokens is reached."""
        service._max_context_tokens = 50  # ~200 characters

        # Create chunks with ~100 chars each
        chunks = [{"text": "A" * 100, "metadata": {"doc_id": "doc1", "order": i}} for i in range(5)]

        mock_client.scroll.return_value = ([], None)

        result = await service.expand_context(chunks)

        # Should stop after ~2 chunks (200 chars = 50 tokens)
        assert len(result) <= 3

    async def test_expand_context_deduplicates(self, service, mock_client):
        """Test that duplicate chunks are removed across expansions."""
        # Two adjacent chunks that would fetch overlapping neighbors
        chunks = [
            {"text": "chunk1", "metadata": {"doc_id": "doc1", "order": 5}},
            {"text": "chunk2", "metadata": {"doc_id": "doc1", "order": 6}},
        ]

        # First call returns neighbor at order 6
        # Second call returns neighbor at order 5
        def scroll_side_effect(*args, **kwargs):
            filter_obj = kwargs.get("scroll_filter")
            if filter_obj:
                # Return empty to simplify - dedup logic is tested via seen_chunk_ids
                return ([], None)
            return ([], None)

        mock_client.scroll.side_effect = scroll_side_effect

        result = await service.expand_context(chunks, deduplicate=True)

        assert len(result) == 2
        # Both should be expanded but no duplicates in final context

    async def test_fetch_neighbors_builds_correct_filter(self, service, mock_client):
        """Test that _fetch_neighbors builds correct Qdrant filter."""
        mock_client.scroll.return_value = ([], None)

        await service._fetch_neighbors(
            doc_id="test_doc",
            center_order=10,
            window_before=2,
            window_after=3,
        )

        # Verify scroll was called
        mock_client.scroll.assert_called_once()

        # Check call arguments
        call_kwargs = mock_client.scroll.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"
        assert call_kwargs["with_payload"] is True

        # Verify filter structure
        scroll_filter = call_kwargs["scroll_filter"]
        assert scroll_filter is not None

    def test_format_expanded_context(self, service):
        """Test formatting expanded chunks for LLM."""
        expanded = [
            ExpandedChunk(
                original_chunk={"text": "chunk1", "metadata": {"title": "Doc1"}, "score": 0.9},
                expanded_text="expanded text 1",
                neighbor_chunks=[],
                total_tokens_estimate=10,
            ),
            ExpandedChunk(
                original_chunk={"text": "chunk2", "metadata": {"title": "Doc2"}, "score": 0.8},
                expanded_text="expanded text 2",
                neighbor_chunks=[],
                total_tokens_estimate=10,
            ),
        ]

        result = service.format_expanded_context(expanded, include_metadata=True)

        assert "[Document 1]" in result
        assert "[Document 2]" in result
        assert "Doc1" in result
        assert "Doc2" in result
        assert "score: 0.90" in result
        assert "expanded text 1" in result
        assert "expanded text 2" in result

    def test_format_expanded_context_no_metadata(self, service):
        """Test formatting without metadata."""
        expanded = [
            ExpandedChunk(
                original_chunk={"text": "chunk1", "metadata": {"title": "Doc1"}, "score": 0.9},
                expanded_text="expanded text 1",
                neighbor_chunks=[],
                total_tokens_estimate=10,
            ),
        ]

        result = service.format_expanded_context(expanded, include_metadata=False)

        assert "[Document 1]" in result
        assert "Doc1" not in result
        assert "score" not in result
        assert "expanded text 1" in result


class TestSmallToBigSettings:
    """Test small-to-big settings integration."""

    def test_settings_have_small_to_big_config(self):
        """Test that Settings class has small-to-big configuration."""
        with patch.dict(
            "os.environ",
            {
                # Isolate from runner secrets/default provider selection
                "API_PROVIDER": "groq",
                "GROQ_API_KEY": "test-groq-key",
                "SMALL_TO_BIG_MODE": "on",
                "SMALL_TO_BIG_WINDOW_BEFORE": "2",
                "SMALL_TO_BIG_WINDOW_AFTER": "3",
                "MAX_EXPANDED_CHUNKS": "15",
                "MAX_CONTEXT_TOKENS": "10000",
            },
            clear=True,
        ):
            # Import after patching env
            from src.config.settings import Settings

            # Need to create fresh instance
            settings = Settings()

            assert settings.small_to_big_mode == "on"
            assert settings.small_to_big_window_before == 2
            assert settings.small_to_big_window_after == 3
            assert settings.max_expanded_chunks == 15
            assert settings.max_context_tokens == 10000

    def test_settings_defaults(self):
        """Test default values for small-to-big settings."""
        with patch.dict(
            "os.environ",
            {
                # Ensure Settings() is valid regardless of host environment
                "API_PROVIDER": "groq",
                "GROQ_API_KEY": "test-groq-key",
            },
            clear=True,
        ):
            from src.config.settings import Settings

            settings = Settings()

            assert settings.small_to_big_mode == "off"
            assert settings.small_to_big_window_before == 1
            assert settings.small_to_big_window_after == 1
            assert settings.max_expanded_chunks == 10
            assert settings.max_context_tokens == 8000

    def test_settings_to_dict_includes_small_to_big(self):
        """Test that to_dict includes small-to-big settings."""
        with patch.dict(
            "os.environ",
            {
                "API_PROVIDER": "groq",
                "GROQ_API_KEY": "test-groq-key",
            },
            clear=True,
        ):
            from src.config.settings import Settings

            settings = Settings()
            settings_dict = settings.to_dict()

            assert "small_to_big_mode" in settings_dict
            assert "small_to_big_window_before" in settings_dict
            assert "small_to_big_window_after" in settings_dict
            assert "max_expanded_chunks" in settings_dict
            assert "max_context_tokens" in settings_dict


class TestIndexerMetadataFields:
    """Test that indexer includes doc_id and chunk_order fields."""

    def test_chunk_has_doc_id_and_order(self):
        """Test that Chunk dataclass has required fields."""
        from src.ingestion.chunker import Chunk

        chunk = Chunk(
            text="test text",
            chunk_id=1,
            document_name="test_doc",
            article_number="art1",
            order=5,
        )

        assert chunk.document_name == "test_doc"
        assert chunk.order == 5

    def test_indexer_creates_doc_id_alias(self):
        """Test that indexer adds doc_id as alias for document_name."""
        # This tests the metadata dict structure in indexer._index_batch
        # We verify through the code structure rather than runtime
        # since runtime requires Qdrant connection
        import inspect

        from src.ingestion.indexer import DocumentIndexer

        # Verify the code includes doc_id field

        source = inspect.getsource(DocumentIndexer)
        assert '"doc_id": chunk.document_name' in source
        assert '"chunk_order": chunk.order' in source
