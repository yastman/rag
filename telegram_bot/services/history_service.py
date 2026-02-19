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
        deal_id: int | None = None,
        scope: str = "all",
    ) -> list[dict[str, Any]]:
        """Search user's conversation history by semantic similarity.

        Returns list of dicts with query, response, timestamp, score.
        """
        try:
            query_embedding = await self._embeddings.aembed_query(query)

            must_conditions: list[models.Condition] = [
                models.FieldCondition(
                    key="metadata.user_id",
                    match=models.MatchValue(value=user_id),
                )
            ]
            if scope == "deal" and deal_id is not None:
                must_conditions.append(
                    models.FieldCondition(
                        key="metadata.deal_id",
                        match=models.MatchValue(value=deal_id),
                    )
                )

            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=query_embedding,
                using=_DENSE_VECTOR_NAME,
                query_filter=models.Filter(must=must_conditions),
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

    async def delete_user_history(self, user_id: int) -> bool:
        """Delete all history points for a given user (e.g. on /clear).

        Returns True on success, False on failure.
        """
        try:
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="metadata.user_id",
                                match=models.MatchValue(value=user_id),
                            )
                        ]
                    )
                ),
            )
            logger.info("Deleted Qdrant history for user_id=%s", user_id)
            return True
        except Exception:
            logger.warning("Failed to delete Qdrant history for user_id=%s", user_id, exc_info=True)
            return False

    async def get_session_turns(
        self,
        user_id: int,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get session Q&A turns ordered by timestamp ascending."""
        if limit <= 0:
            return []

        try:
            all_points: list[Any] = []
            offset: Any = None
            remaining = min(limit, 500)  # hard cap to keep summary bounded

            while remaining > 0:
                page_limit = min(remaining, 100)
                points, next_offset = await self._client.scroll(
                    collection_name=self._collection_name,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="metadata.user_id",
                                match=models.MatchValue(value=user_id),
                            ),
                            models.FieldCondition(
                                key="metadata.session_id",
                                match=models.MatchValue(value=session_id),
                            ),
                        ]
                    ),
                    limit=page_limit,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not points:
                    break
                all_points.extend(points)
                remaining -= len(points)
                if next_offset is None:
                    break
                offset = next_offset

            turns: list[dict[str, Any]] = []
            for p in all_points:
                payload = p.payload if isinstance(p.payload, dict) else {}
                meta = payload.get("metadata", {})
                if not isinstance(meta, dict):
                    continue

                query = meta.get("query", "")
                response = meta.get("response", "")
                query = query if isinstance(query, str) else str(query or "")
                response = response if isinstance(response, str) else str(response or "")
                if not query and not response:
                    continue

                timestamp = meta.get("timestamp", "")
                timestamp = timestamp if isinstance(timestamp, str) else str(timestamp or "")

                input_type = meta.get("input_type", "text")
                input_type = input_type if isinstance(input_type, str) else "text"

                turns.append(
                    {
                        "query": query,
                        "response": response,
                        "timestamp": timestamp,
                        "input_type": input_type,
                    }
                )

            turns.sort(key=lambda t: t["timestamp"])
            return turns
        except Exception:
            logger.warning(
                "Failed to get session turns: user_id=%s session_id=%s",
                user_id,
                session_id,
                exc_info=True,
            )
            return []
