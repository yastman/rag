"""Qdrant-backed conversation history service.

Stores Q&A turns as vector points for semantic search with user isolation.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from qdrant_client import AsyncQdrantClient, models


logger = logging.getLogger(__name__)

_DENSE_DIM = 1024
_DENSE_VECTOR_NAME = "dense"


class HistoryService:
    """Manages conversation history in a dedicated Qdrant collection.

    Each Q&A turn is stored as a point with dense embedding for semantic search.
    User isolation via payload filter on metadata.user_id.
    """

    def __init__(
        self,
        client: AsyncQdrantClient,
        embeddings: Any,
        collection_name: str = "conversation_history",
    ):
        self._client = client
        self._embeddings = embeddings
        self._collection_name = collection_name
        self._ensured = False

    async def ensure_collection(self) -> None:
        """Create history collection if it doesn't exist."""
        if self._ensured:
            return
        exists = await self._client.collection_exists(self._collection_name)
        if not exists:
            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config={
                    _DENSE_VECTOR_NAME: models.VectorParams(
                        size=_DENSE_DIM,
                        distance=models.Distance.COSINE,
                    )
                },
            )
            logger.info("Created history collection: %s", self._collection_name)
        self._ensured = True

    async def save_turn(
        self,
        *,
        user_id: int,
        session_id: str,
        query: str,
        response: str,
        input_type: str,
        query_embedding: list[float] | None = None,
    ) -> bool:
        """Save a Q&A turn to history.

        Returns True on success, False on failure.
        """
        try:
            if query_embedding is None:
                query_embedding = await self._embeddings.aembed_query(query)

            point = models.PointStruct(
                id=str(uuid.uuid4()),
                vector={_DENSE_VECTOR_NAME: query_embedding},
                payload={
                    "page_content": f"Q: {query}\nA: {response[:200]}",
                    "metadata": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "query": query,
                        "response": response,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "input_type": input_type,
                    },
                },
            )
            await self._client.upsert(
                collection_name=self._collection_name,
                points=[point],
            )
            return True
        except Exception:
            logger.warning("Failed to save history turn", exc_info=True)
            return False

    async def search_user_history(
        self,
        user_id: int,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search user's conversation history by semantic similarity.

        Returns list of dicts with query, response, timestamp, score.
        """
        try:
            query_embedding = await self._embeddings.aembed_query(query)

            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=query_embedding,
                using=_DENSE_VECTOR_NAME,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.user_id",
                            match=models.MatchValue(value=user_id),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
            )

            return [
                {
                    "query": (p.payload or {}).get("metadata", {}).get("query", ""),
                    "response": (p.payload or {}).get("metadata", {}).get("response", ""),
                    "timestamp": (p.payload or {}).get("metadata", {}).get("timestamp", ""),
                    "score": p.score,
                }
                for p in result.points
            ]
        except Exception:
            logger.warning("Failed to search history", exc_info=True)
            return []
