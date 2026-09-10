"""Tests for small-to-big context expansion service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.runtime.services.small_to_big import (
    ExpandedChunk,
    SmallToBigMode,
    SmallToBigService,
)


def _point(point_id: str, doc_id: str, order: int, text: str) -> MagicMock:
    """Build a mock Qdrant point as returned by scroll."""
    return MagicMock(
        id=point_id,
        payload={"page_content": text, "metadata": {"doc_id": doc_id, "order": order}},
    )


def _center_order(kwargs) -> int:
    """Extract the excluded center order from the scroll filter kwargs."""
    return kwargs["scroll_filter"].must_not[0].match.value


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

    async def test_adjacent_original_hits_not_repeated_as_neighbors(self, service, mock_client):
        """Adjacent original hits must not reappear as each other's neighbors (#3441)."""
        chunks = [
            {
                "id": "p5",
                "text": "chunk five",
                "metadata": {"doc_id": "doc1", "order": 5},
                "score": 0.9,
            },
            {
                "id": "p6",
                "text": "chunk six",
                "metadata": {"doc_id": "doc1", "order": 6},
                "score": 0.8,
            },
        ]

        def scroll_side_effect(*args, **kwargs):
            center = _center_order(kwargs)
            if center == 5:
                return ([_point("p6", "doc1", 6, "chunk six")], None)
            return ([_point("p5", "doc1", 5, "chunk five")], None)

        mock_client.scroll.side_effect = scroll_side_effect

        result = await service.expand_context(chunks)

        assert [ec.original_chunk for ec in result] == chunks
        # The other hit is never re-added as a neighbor: each expansion is
        # exactly the original text, occurring only once.
        assert result[0].expanded_text == "chunk five"
        assert result[1].expanded_text == "chunk six"
        assert all(ec.neighbor_chunks == [] for ec in result)

    async def test_all_original_hits_preserved_in_stable_order(self, service, mock_client):
        """Every original hit survives in input order with metadata and score."""
        chunks = [
            {
                "id": f"p{i}",
                "text": f"hit {i}",
                "metadata": {"doc_id": f"doc{i}", "order": i},
                "score": 0.5 + i / 10,
            }
            for i in range(4)
        ]
        mock_client.scroll.return_value = ([], None)

        result = await service.expand_context(chunks)

        assert [ec.original_chunk for ec in result] == chunks
        assert [ec.original_chunk["score"] for ec in result] == [c["score"] for c in chunks]
        assert [ec.original_chunk["metadata"] for ec in result] == [c["metadata"] for c in chunks]

    async def test_added_neighbors_stay_within_expansion_budget(self, mock_client):
        """Count and token budgets cap added neighbor text, never the originals."""
        service = SmallToBigService(
            client=mock_client,
            collection_name="test_collection",
            max_expanded_chunks=5,
            max_context_tokens=50,
        )
        chunks = [
            {"id": f"c{i}", "text": f"original {i}", "metadata": {"doc_id": "doc1", "order": i}}
            for i in range(3)
        ]

        def scroll_side_effect(*args, **kwargs):
            center = _center_order(kwargs)
            neighbors = [
                # 80 chars = ~20 estimated tokens each
                _point(f"n{center}-{k}", "doc1", center + 10 + k, "N" * 80)
                for k in range(3)
            ]
            return (neighbors, None)

        mock_client.scroll.side_effect = scroll_side_effect

        result = await service.expand_context(chunks)

        assert len(result) == 3  # every original survives the budget
        added = [n for ec in result for n in ec.neighbor_chunks]
        assert len(added) == 2  # 3rd added neighbor would exceed the 50-token budget
        total_added_tokens = sum(len(n["text"]) // 4 for n in added)
        assert total_added_tokens <= 50

    async def test_zero_and_oversized_originals_do_not_drop_tail(self, mock_client):
        """Zero-length and oversized originals stay; the tail is never removed."""
        service = SmallToBigService(
            client=mock_client,
            collection_name="test_collection",
            max_expanded_chunks=10,
            max_context_tokens=50,
        )
        chunks = [
            {"id": "z", "text": "", "metadata": {"doc_id": "doc1", "order": 1}},
            {"id": "big", "text": "B" * 10_000, "metadata": {"doc_id": "doc1", "order": 2}},
            {"id": "tail", "text": "tail chunk", "metadata": {"doc_id": "doc1", "order": 3}},
        ]
        mock_client.scroll.return_value = ([], None)

        result = await service.expand_context(chunks)

        assert [ec.original_chunk["id"] for ec in result] == ["z", "big", "tail"]
        assert result[1].expanded_text == "B" * 10_000
        assert result[2].expanded_text == "tail chunk"

    async def test_max_expanded_chunks_limits_added_neighbors_not_originals(self, mock_client):
        """The count budget caps added neighbors; one result per original remains."""
        service = SmallToBigService(
            client=mock_client,
            collection_name="test_collection",
            max_expanded_chunks=2,
            max_context_tokens=8000,
        )
        chunks = [
            {"id": f"c{i}", "text": f"chunk {i}", "metadata": {"doc_id": "doc1", "order": i}}
            for i in range(5)
        ]

        def scroll_side_effect(*args, **kwargs):
            center = _center_order(kwargs)
            return ([_point(f"n{center}", "doc1", center + 10, f"neighbor {center}")], None)

        mock_client.scroll.side_effect = scroll_side_effect

        result = await service.expand_context(chunks)

        assert len(result) == 5  # one result per original hit
        assert len(result[0].neighbor_chunks) == 1
        assert len(result[1].neighbor_chunks) == 1
        assert all(len(ec.neighbor_chunks) == 0 for ec in result[2:])

    async def test_max_context_tokens_limits_added_neighbor_tokens(self, mock_client):
        """The token budget caps added neighbor tokens across the whole call."""
        service = SmallToBigService(
            client=mock_client,
            collection_name="test_collection",
            max_expanded_chunks=10,
            max_context_tokens=50,
        )
        chunks = [
            {"id": f"c{i}", "text": "A" * 100, "metadata": {"doc_id": "doc1", "order": i}}
            for i in range(5)
        ]

        def scroll_side_effect(*args, **kwargs):
            center = _center_order(kwargs)
            neighbors = [
                _point(f"n{center}a", "doc1", center + 10, "N" * 100),
                _point(f"n{center}b", "doc1", center + 11, "N" * 100),
            ]
            return (neighbors, None)

        mock_client.scroll.side_effect = scroll_side_effect

        result = await service.expand_context(chunks)

        assert len(result) == 5
        added = [n for ec in result for n in ec.neighbor_chunks]
        total_added_tokens = sum(len(n["text"]) // 4 for n in added)
        assert total_added_tokens <= 50

    async def test_expand_context_deduplicates_overlapping_neighbors(self, service, mock_client):
        """Overlapping neighbors appear once; originals are never re-added."""
        chunks = [
            {"id": "p5", "text": "chunk five", "metadata": {"doc_id": "doc1", "order": 5}},
            {"id": "p6", "text": "chunk six", "metadata": {"doc_id": "doc1", "order": 6}},
        ]

        def scroll_side_effect(*args, **kwargs):
            center = _center_order(kwargs)
            if center == 5:
                # The other original hit plus a genuinely shared neighbor.
                return (
                    [
                        _point("p6", "doc1", 6, "chunk six"),
                        _point("shared", "doc1", 7, "shared neighbor"),
                    ],
                    None,
                )
            return ([_point("shared", "doc1", 7, "shared neighbor")], None)

        mock_client.scroll.side_effect = scroll_side_effect

        result = await service.expand_context(chunks, deduplicate=True)

        added_first = [n["id"] for n in result[0].neighbor_chunks]
        added_second = [n["id"] for n in result[1].neighbor_chunks]
        assert "p6" not in added_first  # original hit not re-added as neighbor
        assert "shared" in added_first
        assert added_second == []  # shared neighbor admitted only once

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


class TestRagPipelineSmallToBig:
    """Test _expand_small_to_big integration in the RAG pipeline."""

    @pytest.mark.asyncio
    async def test_expand_small_to_big_no_inplace_mutation(self):
        """Test that _expand_small_to_big does not mutate the input dictionaries in-place."""
        from src.runtime.pipeline.rag import _expand_small_to_big
        from src.runtime.services.small_to_big import ExpandedChunk

        # Setup mocks
        mock_qdrant = MagicMock()
        mock_qdrant.client = AsyncMock()
        mock_qdrant.collection_name = "test_collection"

        mock_config = MagicMock()
        mock_config.small_to_big_mode = "on"
        mock_config.max_expanded_chunks = 5
        mock_config.max_context_tokens = 1000
        mock_config.small_to_big_window_before = 1
        mock_config.small_to_big_window_after = 1

        # Input data
        final_docs = [
            {"text": "original text 1", "metadata": {"doc_id": "doc1", "order": 1}},
            {"text": "original text 2", "metadata": {"doc_id": "doc2", "order": 2}},
        ]

        # Keep references to verify they are not mutated
        doc_1_orig = final_docs[0]
        doc_1_orig_copy = dict(doc_1_orig)
        doc_2_orig = final_docs[1]
        doc_2_orig_copy = dict(doc_2_orig)

        mock_expanded = [
            ExpandedChunk(
                original_chunk=doc_1_orig,
                expanded_text="expanded text 1",
                neighbor_chunks=[],
                total_tokens_estimate=10,
            ),
            ExpandedChunk(
                original_chunk=doc_2_orig,
                expanded_text="expanded text 2",
                neighbor_chunks=[],
                total_tokens_estimate=10,
            ),
        ]

        with patch(
            "src.runtime.services.small_to_big.SmallToBigService.expand_context",
            new_callable=AsyncMock,
        ) as mock_expand:
            mock_expand.return_value = mock_expanded

            await _expand_small_to_big(final_docs, qdrant=mock_qdrant, config=mock_config)

        # The list itself should be updated with new dictionaries
        assert len(final_docs) == 2
        assert final_docs[0]["text"] == "expanded text 1"
        assert final_docs[0]["_expanded"] is True
        assert final_docs[1]["text"] == "expanded text 2"
        assert final_docs[1]["_expanded"] is True

        # The original dictionary objects should NOT have been mutated
        assert doc_1_orig == doc_1_orig_copy
        assert "text" in doc_1_orig
        assert doc_1_orig["text"] == "original text 1"
        assert "_expanded" not in doc_1_orig

        assert doc_2_orig == doc_2_orig_copy
        assert doc_2_orig["text"] == "original text 2"
        assert "_expanded" not in doc_2_orig

        # Confirm identity has changed (new dictionary created)
        assert final_docs[0] is not doc_1_orig
        assert final_docs[1] is not doc_2_orig

    async def test_expand_small_to_big_runs_live_service(self):
        """Pipeline helper executes the live _expand_small_to_big service path (#3441)."""
        from src.runtime.pipeline.rag import _expand_small_to_big

        mock_qdrant = MagicMock()
        mock_qdrant.client = AsyncMock()
        mock_qdrant.collection_name = "test_collection"

        mock_config = MagicMock()
        mock_config.small_to_big_mode = "on"
        mock_config.max_expanded_chunks = 10
        mock_config.max_context_tokens = 8000
        mock_config.small_to_big_window_before = 1
        mock_config.small_to_big_window_after = 1

        final_docs = [
            {
                "id": "p1",
                "text": "hit one",
                "metadata": {"doc_id": "doc1", "order": 1},
                "score": 0.9,
            },
            {
                "id": "p2",
                "text": "hit two",
                "metadata": {"doc_id": "doc1", "order": 2},
                "score": 0.8,
            },
        ]

        def scroll_side_effect(*args, **kwargs):
            center = _center_order(kwargs)
            if center == 1:
                return (
                    [
                        _point("n1", "doc1", 0, "before one"),
                        _point("p2", "doc1", 2, "hit two"),
                    ],
                    None,
                )
            return (
                [
                    _point("n2", "doc1", 3, "after two"),
                    _point("p1", "doc1", 1, "hit one"),
                ],
                None,
            )

        mock_qdrant.client.scroll.side_effect = scroll_side_effect

        await _expand_small_to_big(final_docs, qdrant=mock_qdrant, config=mock_config)

        assert len(final_docs) == 2
        # Original rank order, metadata, and score are stable.
        assert final_docs[0]["id"] == "p1"
        assert final_docs[0]["metadata"] == {"doc_id": "doc1", "order": 1}
        assert final_docs[0]["score"] == 0.9
        assert final_docs[1]["id"] == "p2"
        assert final_docs[1]["metadata"] == {"doc_id": "doc1", "order": 2}
        assert final_docs[1]["score"] == 0.8
        # Expanded text keeps each hit once and only admits non-duplicate neighbors.
        assert final_docs[0]["text"] == "before one\n\nhit one"
        assert final_docs[1]["text"] == "hit two\n\nafter two"
        assert final_docs[0]["_expanded"] is True
        assert final_docs[1]["_expanded"] is True
