"""Integration tests for Qdrant conversation history service.

Requires a running Qdrant instance (make docker-up).
"""

import contextlib
import uuid
from unittest.mock import AsyncMock

import pytest


pytest.importorskip("qdrant_client", reason="qdrant-client not installed")

from qdrant_client import AsyncQdrantClient

from telegram_bot.services.history_service import HistoryService


# Use unique collection name to avoid conflicts
TEST_COLLECTION = f"test_history_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def qdrant_client():
    """Create async Qdrant client for testing."""
    client = AsyncQdrantClient(url="http://localhost:6333")
    try:
        yield client
    finally:
        # Cleanup: delete test collection
        with contextlib.suppress(Exception):
            await client.delete_collection(TEST_COLLECTION)
        await client.close()


@pytest.fixture
def mock_embeddings():
    """Embeddings mock returning deterministic 1024d vectors."""
    emb = AsyncMock()
    emb.aembed_query = AsyncMock(return_value=[0.1] * 1024)
    return emb


@pytest.fixture
async def service(qdrant_client, mock_embeddings):
    """Create HistoryService connected to real Qdrant."""
    svc = HistoryService(
        client=qdrant_client,
        embeddings=mock_embeddings,
        collection_name=TEST_COLLECTION,
    )
    await svc.ensure_collection()
    return svc


@pytest.mark.skipif(
    not pytest.importorskip("qdrant_client", reason="qdrant not available"),
    reason="Qdrant not available",
)
class TestQdrantHistoryIntegration:
    """Integration tests requiring live Qdrant."""

    async def test_save_and_search_returns_own_data(self, service, mock_embeddings):
        """Upsert Q&A and retrieve via search with user_id filter."""
        await service.save_turn(
            user_id=100,
            session_id="test-session",
            query="цены на квартиры",
            response="Квартиры от 50к евро",
            input_type="text",
            query_embedding=[0.1] * 1024,
        )

        results = await service.search_user_history(user_id=100, query="цены", limit=5)

        assert len(results) >= 1
        assert results[0]["query"] == "цены на квартиры"
        assert results[0]["response"] == "Квартиры от 50к евро"

    async def test_cross_user_isolation(self, service, mock_embeddings):
        """User A cannot retrieve user B records."""
        # User A saves
        await service.save_turn(
            user_id=200,
            session_id="session-a",
            query="квартира пользователя А",
            response="Ответ для А",
            input_type="text",
            query_embedding=[0.2] * 1024,
        )

        # User B saves
        await service.save_turn(
            user_id=300,
            session_id="session-b",
            query="квартира пользователя Б",
            response="Ответ для Б",
            input_type="text",
            query_embedding=[0.3] * 1024,
        )

        # User A searches — should NOT see user B data
        results_a = await service.search_user_history(user_id=200, query="квартира", limit=10)
        user_ids_a = {r.get("query", "") for r in results_a}
        assert "квартира пользователя Б" not in user_ids_a

        # User B searches — should NOT see user A data
        results_b = await service.search_user_history(user_id=300, query="квартира", limit=10)
        user_ids_b = {r.get("query", "") for r in results_b}
        assert "квартира пользователя А" not in user_ids_b
