"""Unit tests for HistoryService (Qdrant-backed conversation history)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


pytest.importorskip("qdrant_client", reason="qdrant-client not installed")


from telegram_bot.services.history_service import HistoryService


@pytest.fixture
def mock_client():
    """Create mock AsyncQdrantClient."""
    return AsyncMock()


@pytest.fixture
def mock_embeddings():
    """Create mock embeddings with aembed_query."""
    emb = AsyncMock()
    emb.aembed_query = AsyncMock(return_value=[0.1] * 1024)
    return emb


@pytest.fixture
def service(mock_client, mock_embeddings):
    """Create HistoryService with mocked deps."""
    return HistoryService(
        client=mock_client,
        embeddings=mock_embeddings,
        collection_name="test_history",
    )


class TestEnsureCollection:
    """Test ensure_collection creates collection if absent."""

    async def test_creates_collection_when_missing(self, service, mock_client):
        """ensure_collection creates collection if it doesn't exist."""
        mock_client.collection_exists = AsyncMock(return_value=False)
        mock_client.create_collection = AsyncMock()

        await service.ensure_collection()

        mock_client.collection_exists.assert_awaited_once_with("test_history")
        mock_client.create_collection.assert_awaited_once()
        # Verify vector config
        call_kwargs = mock_client.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_history"

    async def test_skips_if_collection_exists(self, service, mock_client):
        """ensure_collection skips creation if collection already exists."""
        mock_client.collection_exists = AsyncMock(return_value=True)

        await service.ensure_collection()

        mock_client.create_collection.assert_not_called()

    async def test_idempotent_after_first_call(self, service, mock_client):
        """ensure_collection only checks once."""
        mock_client.collection_exists = AsyncMock(return_value=True)

        await service.ensure_collection()
        await service.ensure_collection()

        # Only called once due to _ensured flag
        assert mock_client.collection_exists.await_count == 1


class TestSaveTurn:
    """Test save_turn upserts a point."""

    async def test_upserts_point_with_correct_payload(self, service, mock_client, mock_embeddings):
        """save_turn upserts one point with expected payload schema."""
        mock_client.upsert = AsyncMock()

        await service.save_turn(
            user_id=12345,
            session_id="chat-abc-20260213",
            query="цены на квартиры",
            response="Вот информация о ценах...",
            input_type="text",
            query_embedding=[0.5] * 1024,
        )

        mock_client.upsert.assert_awaited_once()
        call_kwargs = mock_client.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_history"
        points = call_kwargs["points"]
        assert len(points) == 1
        point = points[0]
        payload = point.payload
        assert payload["metadata"]["user_id"] == 12345
        assert payload["metadata"]["query"] == "цены на квартиры"
        assert payload["metadata"]["response"] == "Вот информация о ценах..."
        assert payload["metadata"]["input_type"] == "text"
        assert payload["metadata"]["session_id"] == "chat-abc-20260213"
        assert "timestamp" in payload["metadata"]
        assert "page_content" in payload

    async def test_uses_provided_embedding(self, service, mock_client, mock_embeddings):
        """save_turn uses provided query_embedding, no extra embed call."""
        mock_client.upsert = AsyncMock()
        embedding = [0.5] * 1024

        await service.save_turn(
            user_id=1,
            session_id="s",
            query="q",
            response="r",
            input_type="text",
            query_embedding=embedding,
        )

        # Should NOT call embeddings since we provided embedding
        mock_embeddings.aembed_query.assert_not_called()
        point = mock_client.upsert.call_args.kwargs["points"][0]
        assert point.vector["dense"] == embedding

    async def test_embeds_query_when_no_embedding_provided(
        self, service, mock_client, mock_embeddings
    ):
        """save_turn embeds query when query_embedding is None."""
        mock_client.upsert = AsyncMock()

        await service.save_turn(
            user_id=1,
            session_id="s",
            query="test query",
            response="r",
            input_type="text",
            query_embedding=None,
        )

        mock_embeddings.aembed_query.assert_awaited_once_with("test query")

    async def test_graceful_on_qdrant_error(self, service, mock_client):
        """save_turn does not raise on Qdrant exceptions."""
        mock_client.upsert = AsyncMock(side_effect=RuntimeError("connection lost"))

        # Should not raise
        await service.save_turn(
            user_id=1,
            session_id="s",
            query="q",
            response="r",
            input_type="text",
            query_embedding=[0.1] * 1024,
        )


class TestSearchUserHistory:
    """Test search_user_history with user_id filter."""

    async def test_searches_with_user_filter(self, service, mock_client, mock_embeddings):
        """search_user_history builds filter by metadata.user_id."""
        mock_point = MagicMock()
        mock_point.id = str(uuid.uuid4())
        mock_point.score = 0.95
        mock_point.payload = {
            "page_content": "Q: цены A: ...",
            "metadata": {
                "user_id": 12345,
                "query": "цены",
                "response": "Ответ",
                "timestamp": "2026-02-13T10:00:00",
            },
        }
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        mock_client.query_points = AsyncMock(return_value=mock_result)

        results = await service.search_user_history(
            user_id=12345, query="цены на квартиры", limit=5
        )

        mock_client.query_points.assert_awaited_once()
        call_kwargs = mock_client.query_points.call_args.kwargs
        # Verify user_id filter
        qf = call_kwargs["query_filter"]
        assert any(c.key == "metadata.user_id" for c in qf.must)
        assert len(results) == 1
        assert results[0]["query"] == "цены"
        assert results[0]["response"] == "Ответ"

    async def test_returns_empty_on_no_results(self, service, mock_client, mock_embeddings):
        """search_user_history returns empty list when no matches."""
        mock_result = MagicMock()
        mock_result.points = []
        mock_client.query_points = AsyncMock(return_value=mock_result)

        results = await service.search_user_history(user_id=99999, query="test", limit=5)

        assert results == []

    async def test_graceful_on_qdrant_error(self, service, mock_client, mock_embeddings):
        """search_user_history returns empty list on Qdrant exceptions."""
        mock_client.query_points = AsyncMock(side_effect=RuntimeError("timeout"))

        results = await service.search_user_history(user_id=1, query="test", limit=5)

        assert results == []
