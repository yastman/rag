"""Apartments search service wrapping QdrantService for apartments collection."""

from __future__ import annotations

import logging

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

    @observe(name="apartments-scroll", capture_input=False, capture_output=False)
    async def scroll_with_filters(
        self,
        filters: dict | None = None,
        limit: int = 5,
        start_from: float | None = None,
        exclude_ids: list[str] | None = None,
    ) -> tuple[list[dict], int, float | None, list[str]]:
        """Payload-only scroll ordered by price_eur.

        Uses OrderBy.start_from for pagination (offset incompatible with order_by).
        Returns: (results, total_count, next_start_from, page_ids)
        """
        qdrant_filter = _build_apartment_filter(filters)

        # Дедупликация: исключить уже показанные ID на границе цены
        if exclude_ids:
            has_id_cond = models.HasIdCondition(has_id=exclude_ids)
            if qdrant_filter is None:
                qdrant_filter = models.Filter(must_not=[has_id_cond])
            else:
                existing_must_not = list(qdrant_filter.must_not or [])
                existing_must_not.append(has_id_cond)
                qdrant_filter.must_not = existing_must_not

        records, _ = await self._qdrant.client.scroll(
            collection_name=self._qdrant.collection_name,
            scroll_filter=qdrant_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            order_by=models.OrderBy(key="price_eur", start_from=start_from),
        )

        count_result = await self._qdrant.client.count(
            collection_name=self._qdrant.collection_name,
            count_filter=_build_apartment_filter(filters),  # без exclude_ids
            exact=True,
        )

        formatted = [{"id": str(r.id), "payload": r.payload or {}} for r in records]

        # next_start_from = цена последней записи
        next_start_from_val: float | None = None
        page_ids: list[str] = []
        if records:
            last_price = (records[-1].payload or {}).get("price_eur")
            next_start_from_val = float(last_price) if last_price is not None else None
            page_ids = [str(r.id) for r in records]

        return formatted, count_result.count, next_start_from_val, page_ids

    async def get_distinct_values(self, field: str) -> list[str]:
        """Get sorted unique non-empty values for a payload field via scroll."""
        values: set[str] = set()
        offset = None
        while True:
            records, next_offset = await self._qdrant.client.scroll(
                collection_name=self._qdrant.collection_name,
                limit=1000,
                offset=offset,
                with_payload=[field],
                with_vectors=False,
            )
            for r in records:
                val = (r.payload or {}).get(field, "")
                if val:
                    values.add(str(val))
            if next_offset is None:
                break
            offset = next_offset
        return sorted(values)

    async def get_collection_stats(self) -> dict:
        """Get unique cities, complexes, rooms, price range for example generation."""
        records, _ = await self._qdrant.client.scroll(
            collection_name=self._qdrant.collection_name,
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        cities: set[str] = set()
        complexes: set[str] = set()
        rooms_set: set[int] = set()
        prices: list[float] = []
        for p in records:
            d = p.payload or {}
            if d.get("city"):
                cities.add(d["city"])
            if d.get("complex_name"):
                complexes.add(d["complex_name"])
            if d.get("rooms"):
                rooms_set.add(int(d["rooms"]))
            if d.get("price_eur"):
                prices.append(float(d["price_eur"]))
        return {
            "cities": sorted(cities),
            "complexes": sorted(complexes),
            "rooms": sorted(rooms_set),
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
        }


def generate_search_examples(stats: dict) -> list[str]:
    """Generate 4 diverse search example strings from DB stats."""
    cities = stats.get("cities", [])
    complexes = stats.get("complexes", [])
    rooms_list = stats.get("rooms", [1, 2, 3])
    max_price = stats.get("max_price", 200000)

    room_names = {1: "Студия", 2: "Двушка", 3: "Трёшка"}
    examples: list[str] = []

    # Example 1: room type + city + price
    if cities:
        r = rooms_list[0] if rooms_list else 1
        price = round(max_price * 0.4 / 5000) * 5000
        examples.append(
            f"{room_names.get(r, 'Апартамент')} в {cities[0]} до {price:,.0f}€".replace(",", " ")
        )

    # Example 2: room type + complex
    if complexes:
        r = rooms_list[1] if len(rooms_list) > 1 else 2
        examples.append(f"{room_names.get(r, 'Двушка')} в {complexes[0]}")

    # Example 3: room type + city + price
    if len(cities) > 1:
        r = rooms_list[-1] if rooms_list else 3
        price = round(max_price * 0.65 / 5000) * 5000
        examples.append(
            f"{room_names.get(r, 'Трёшка')} в {cities[-1]} до {price:,.0f}€".replace(",", " ")
        )

    # Example 4: generic + city + price range
    if len(cities) > 1:
        price = round(max_price * 0.5 / 5000) * 5000
        examples.append(f"Апартамент в {cities[1]} от {price:,.0f}€".replace(",", " "))

    # Pad with defaults if needed
    defaults = [
        "Студия у моря до 100 000€",
        "Двушка с видом на море",
        "Трёшка с бассейном",
        "Апартамент с мебелью",
    ]
    while len(examples) < 4:
        examples.append(defaults[len(examples)])

    return examples[:4]
