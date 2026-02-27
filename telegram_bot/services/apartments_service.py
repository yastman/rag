"""Apartments search service wrapping QdrantService for apartments collection."""

from __future__ import annotations

import logging
import uuid

from qdrant_client import models

from telegram_bot.observability import get_client, observe
from telegram_bot.services.qdrant import QdrantService


logger = logging.getLogger(__name__)

_ESCALATION_MIN_SPREAD = 0.002


def _build_apartment_filter(filters: dict | None) -> models.Filter | None:
    """Build Qdrant filter for apartments (top-level fields, no metadata. prefix).

    Supports:
    - Exact match: {"rooms": 2, "complex_name": "Premier Fort Beach"}
    - Range: {"price_eur": {"gte": 100000, "lte": 200000}}
    - MatchAny: {"view_tags": ["sea", "pool"]}
    """
    if not filters:
        return None

    conditions: list[models.Condition] = []

    for key, value in filters.items():
        if isinstance(value, list):
            # MatchAny for tags
            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchAny(any=value),
                )
            )
        elif isinstance(value, bool):
            # Explicit bool check BEFORE dict/int — isinstance(True, int) is True in Python
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
        elif isinstance(value, dict):
            range_params = {op: value[op] for op in ("lt", "lte", "gt", "gte") if op in value}
            if range_params:
                conditions.append(
                    models.FieldCondition(key=key, range=models.Range(**range_params))
                )
        else:
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))

    return models.Filter(must=conditions) if conditions else None


def check_escalation(
    *,
    returned_count: int,
    top_k: int,
    score_spread: float,
    confidence: str,
) -> str | None:
    """Check if fast path result needs agent escalation.

    Returns: escalation reason string, or None if no escalation needed.
    """
    reasons = []
    if returned_count == 0:
        reasons.append("no_results")
    if returned_count >= top_k and score_spread < _ESCALATION_MIN_SPREAD and confidence != "HIGH":
        reasons.append("ambiguous_topk")
    if confidence == "LOW":
        reasons.append("low_confidence")
    return "; ".join(reasons) if reasons else None


class ApartmentsService:
    """Apartment search via existing QdrantService."""

    def __init__(self, qdrant: QdrantService) -> None:
        self._qdrant = qdrant

    @observe(name="apartments-hybrid-search", capture_input=False, capture_output=False)
    async def search(
        self,
        dense_vector: list[float],
        sparse_vector: dict | None = None,
        colbert_query: list[list[float]] | None = None,
        filters: dict | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Hybrid search on apartments collection with apartment-specific filters."""
        lf = get_client()
        lf.update_current_span(input={"filters": filters, "top_k": top_k})
        results, _ = await self.search_with_filters(
            dense_vector=dense_vector,
            colbert_query=colbert_query,
            sparse_vector=sparse_vector,
            filters=filters,
            top_k=top_k,
        )
        return results

    @observe(name="apartments-filtered-search")
    async def search_with_filters(
        self,
        dense_vector: list[float],
        colbert_query: list[list[float]] | None,
        sparse_vector: dict | None,
        filters: dict | None,
        top_k: int = 10,
    ) -> tuple[list[dict], int]:
        """Search with apartment-specific filter (no metadata. prefix).

        Returns: (results, returned_count)
        """
        qdrant_filter = _build_apartment_filter(filters)

        # Build sparse vector
        sparse_v = None
        if sparse_vector and sparse_vector.get("indices"):
            sparse_v = models.SparseVector(
                indices=sparse_vector["indices"],
                values=sparse_vector["values"],
            )

        # Build prefetch (dense + sparse → RRF)
        prefetch = []
        prefetch.append(
            models.Prefetch(
                query=dense_vector,
                using="dense",
                limit=100,
            )
        )
        if sparse_v:
            prefetch.append(
                models.Prefetch(
                    query=sparse_v,
                    using="bm42",
                    limit=100,
                )
            )

        rrf_query = models.FusionQuery(fusion=models.Fusion.RRF)

        if colbert_query:
            # 3-stage: dense+sparse → RRF → ColBERT rescore
            rrf_prefetch = models.Prefetch(
                prefetch=prefetch,
                query=rrf_query,
                limit=top_k * 3,
            )
            result = await self._qdrant.client.query_points(
                collection_name=self._qdrant.collection_name,
                prefetch=[rrf_prefetch],
                query=colbert_query,
                using="colbert",
                query_filter=qdrant_filter,
                limit=top_k,
                with_payload=True,
            )
        else:
            result = await self._qdrant.client.query_points(
                collection_name=self._qdrant.collection_name,
                prefetch=prefetch,
                query=rrf_query,
                query_filter=qdrant_filter,
                limit=top_k,
                with_payload=True,
            )

        # Format results
        formatted = []
        for pt in result.points:
            payload = pt.payload or {}
            formatted.append(
                {
                    "score": pt.score,
                    "payload": payload,
                    "id": str(pt.id),
                }
            )

        return formatted, len(result.points)

    async def scroll_with_filters(
        self,
        filters: dict | None = None,
        limit: int = 5,
        offset: str | uuid.UUID | None = None,
    ) -> tuple[list[dict], int, str | uuid.UUID | None]:
        """Payload-only scroll (no vectors), ordered by price_eur.

        Returns: (results, total_count, next_offset)
        """
        qdrant_filter = _build_apartment_filter(filters)

        records, next_offset = await self._qdrant.client.scroll(
            collection_name=self._qdrant.collection_name,
            scroll_filter=qdrant_filter,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            order_by=models.OrderBy(key="price_eur"),
        )

        count_result = await self._qdrant.client.count(
            collection_name=self._qdrant.collection_name,
            count_filter=qdrant_filter,
            exact=True,
        )

        formatted = [
            {
                "id": str(r.id),
                "payload": r.payload or {},
            }
            for r in records
        ]

        return formatted, count_result.count, next_offset
