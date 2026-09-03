"""Apartments search service wrapping QdrantService for apartments collection."""

from __future__ import annotations

import logging
from typing import cast
from uuid import UUID

from qdrant_client import models

from src.runtime.domain_defaults import DEMO_CITY_PROMPT_FORMS
from src.runtime.services.qdrant import QdrantService


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

    async def search(
        self,
        dense_vector: list[float],
        sparse_vector: dict | None = None,
        colbert_query: list[list[float]] | None = None,
        filters: dict | None = None,
        top_k: int = 10,
        rrf_k: int = 60,
    ) -> list[dict]:
        """Hybrid search on apartments collection with apartment-specific filters."""
        results, _ = await self.search_with_filters(
            dense_vector=dense_vector,
            colbert_query=colbert_query,
            sparse_vector=sparse_vector,
            filters=filters,
            top_k=top_k,
            rrf_k=rrf_k,
        )
        return results  # type: ignore[no-any-return]

    async def search_with_filters(
        self,
        dense_vector: list[float],
        colbert_query: list[list[float]] | None,
        sparse_vector: dict | None,
        filters: dict | None,
        top_k: int = 10,
        rrf_k: int = 60,
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

        rrf_query = models.RrfQuery(rrf=models.Rrf(k=rrf_k))

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
            exclude_ids_typed: list[int | str | UUID] = list(exclude_ids)
            has_id_cond = models.HasIdCondition(has_id=exclude_ids_typed)
            if qdrant_filter is None:
                qdrant_filter = models.Filter(must_not=[has_id_cond])
            else:
                existing_must_not = list(qdrant_filter.must_not or [])
                existing_must_not.append(has_id_cond)
                qdrant_filter.must_not = cast(list[models.Condition], existing_must_not)

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

    async def count_with_filters(self, filters: dict | None = None) -> int:
        """Count apartments matching payload filters (no vector search)."""
        qdrant_filter = _build_apartment_filter(filters)
        result = await self._qdrant.client.count(
            collection_name=self._qdrant.collection_name,
            count_filter=qdrant_filter,
            exact=True,
        )
        return result.count

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
        """Get cities, complexes, rooms, prices, and *provable combinations*.

        Scans the whole collection (not a 100-point page) and, besides flat
        unique values, returns per-city and per-complex (rooms, count, price)
        combinations so example generation can advertise only dimensions that
        actually co-occur in stored listings (#3203).
        """
        cities: set[str] = set()
        complexes: set[str] = set()
        rooms_set: set[int] = set()
        prices: list[float] = []
        city_room_stats: dict[str, dict[int, dict]] = {}
        complex_room_counts: dict[str, dict[int, int]] = {}
        city_prices: dict[str, list[float]] = {}

        offset = None
        while True:
            records, offset = await self._qdrant.client.scroll(
                collection_name=self._qdrant.collection_name,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in records:
                d = p.payload or {}
                city = d.get("city")
                complex_name = d.get("complex_name")
                price = d.get("price_eur")
                if city:
                    cities.add(city)
                if complex_name:
                    complexes.add(complex_name)
                if d.get("rooms"):
                    rooms = int(d["rooms"])
                    rooms_set.add(rooms)
                    if city:
                        stats_entry = city_room_stats.setdefault(city, {}).setdefault(
                            rooms, {"count": 0, "max_price": 0.0}
                        )
                        stats_entry["count"] += 1
                        if price:
                            stats_entry["max_price"] = max(
                                stats_entry["max_price"], float(price)
                            )
                    if complex_name:
                        room_counts = complex_room_counts.setdefault(complex_name, {})
                        room_counts[rooms] = room_counts.get(rooms, 0) + 1
                if price and city:
                    prices.append(float(price))
                    city_prices.setdefault(city, []).append(float(price))
            if offset is None:
                break

        return {
            "cities": sorted(cities),
            "complexes": sorted(complexes),
            "rooms": sorted(rooms_set),
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
            "city_combos": {
                city: [
                    {"rooms": rooms, **combo}
                    for rooms, combo in sorted(city_room_stats.get(city, {}).items())
                ]
                for city in sorted(cities)
            },
            "complex_combos": {
                complex_name: [
                    {"rooms": rooms, "count": count}
                    for rooms, count in sorted(complex_room_counts.get(complex_name, {}).items())
                ]
                for complex_name in sorted(complexes)
            },
            "city_prices": {city: sorted(vals) for city, vals in city_prices.items()},
        }


def _room_label(rooms: int) -> str:
    """Visible room label whose wording extracts back to the same rooms value.

    The production regex extractor (apartment_filter_extractor) maps
    "студия"→1, "двушка"→3, "трёшка"→4 (total rooms = bedrooms + living room)
    and "N спальн..."→N+1. Labels here always round-trip through it (#3203).
    """
    if rooms == 1:
        return "Студия"
    if rooms == 3:
        return "Двушка"
    if rooms == 4:
        return "Трёшка"
    if rooms == 2:
        return "Апартамент с 1 спальней"
    return f"Апартамент с {rooms - 1} спальнями"


def _ceil_to(value: float, step: int) -> int:
    return int(-(-value // step) * step)


def _floor_to(value: float, step: int) -> int:
    return int(value // step * step)


def _city_phrase(city: str) -> str:
    """Grammatical 'в …' form for visible examples (falls back to 'в {city}')."""
    return DEMO_CITY_PROMPT_FORMS.get(city, f"в {city}")


# Prefer advertising combinations that return at least this many listings.
_EXAMPLE_MIN_COHERENT = 3

# Claim-free fallback examples: they advertise no city/complex/price dimension
# and therefore cannot promise a combination that is absent from the data.
_EXAMPLE_PADS = [
    "Показать все апартаменты",
    "Апартаменты у моря",
    "Апартаменты с бассейном",
    "Апартаменты с мебелью",
]


def generate_search_examples(stats: dict) -> list[str]:
    """Generate up to 4 diverse search examples advertising only existing data.

    Every example is built from a stored (city | complex) × rooms × price
    combination, so clicking it cannot yield zero results by construction
    (#3203). Falls back to flat stats and then to claim-free pads.
    """
    cities: list[str] = stats.get("cities", [])
    complexes: list[str] = stats.get("complexes", [])
    city_combos: dict = stats.get("city_combos", {})
    complex_combos: dict = stats.get("complex_combos", {})
    city_prices: dict = stats.get("city_prices", {})

    examples: list[str] = []
    used_cities: set[str] = set()

    def combo_price(combo: dict) -> str:
        return f"{_ceil_to(float(combo['max_price']), 5000):,}".replace(",", " ")

    # Example: rooms + city + "до" price (ceiling = combo max → combo count hits).
    for city in cities:
        combo = next(
            (c for c in city_combos.get(city, []) if c["count"] >= _EXAMPLE_MIN_COHERENT),
            None,
        )
        if combo is None:
            continue
        examples.append(
            f"{_room_label(int(combo['rooms']))} {_city_phrase(city)} до {combo_price(combo)}€"
        )
        used_cities.add(city)
        break

    # Example: rooms + complex (only combos that really exist in the complex).
    for complex_name in complexes:
        combo = next(
            (c for c in complex_combos.get(complex_name, []) if c["count"] >= _EXAMPLE_MIN_COHERENT),
            None,
        )
        if combo is None:
            continue
        examples.append(f"{_room_label(int(combo['rooms']))} в {complex_name}")
        break

    # Example: rooms + city + "до" price from another city.
    for city in cities:
        if city in used_cities:
            continue
        combo = next(
            (c for c in city_combos.get(city, []) if c["count"] >= _EXAMPLE_MIN_COHERENT),
            None,
        )
        if combo is None:
            continue
        examples.append(
            f"{_room_label(int(combo['rooms']))} {_city_phrase(city)} до {combo_price(combo)}€"
        )
        used_cities.add(city)
        break

    # Example: generic + city + "от" price (third-lowest price → ≥3 matches).
    for city in cities:
        if city in used_cities:
            continue
        prices = city_prices.get(city, [])
        if len(prices) < _EXAMPLE_MIN_COHERENT:
            continue
        price = _floor_to(prices[_EXAMPLE_MIN_COHERENT - 1], 5000)
        formatted = f"{price:,}".replace(",", " ")
        examples.append(f"Апартамент {_city_phrase(city)} от {formatted}€")
        used_cities.add(city)
        break

    # Flat-stats fallback (legacy shape): single-dimension claims only.
    for city in cities:
        if len(examples) >= 4:
            break
        if city not in used_cities:
            examples.append(f"Апартамент {_city_phrase(city)}")
            used_cities.add(city)
    for complex_name in complexes:
        if len(examples) >= 4:
            break
        examples.append(f"Апартамент в {complex_name}")

    # Pad with claim-free examples if the collection has little or no data.
    unique: list[str] = list(dict.fromkeys(examples))
    pad_idx = 0
    while len(unique) < 4 and pad_idx < 2 * len(_EXAMPLE_PADS):
        pad = _EXAMPLE_PADS[pad_idx % len(_EXAMPLE_PADS)]
        if pad not in unique:
            unique.append(pad)
        pad_idx += 1
    return unique[:4]
