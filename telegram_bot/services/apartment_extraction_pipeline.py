"""Apartment extraction pipeline: LLM first, regex fallback."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from telegram_bot.observability import observe
from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)


if TYPE_CHECKING:
    from redis.asyncio import Redis

    from telegram_bot.services.apartment_llm_extractor import ApartmentLlmExtractor

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "extraction:v1:"
_CACHE_TTL = 86400  # 24h


class ApartmentExtractionPipeline:
    """Orchestrates LLM first, regex fallback."""

    def __init__(
        self,
        regex_extractor: ApartmentFilterExtractor,
        llm_extractor: ApartmentLlmExtractor | None = None,
        redis: Redis | None = None,
    ) -> None:
        self._regex = regex_extractor
        self._llm = llm_extractor
        self._redis = redis

    @observe(name="apartment-extraction-pipeline", capture_input=False, capture_output=False)
    async def extract(self, query: str) -> ApartmentSearchFilters:
        """Main entry point: cache → LLM (primary) → regex (fallback)."""
        # 1. Check cache
        cached = await self._cache_get(query)
        if cached:
            return cached

        # 2. LLM primary
        if self._llm is not None:
            try:
                result = await self._llm.extract(query=query)
                await self._cache_set(query, result)
                return result
            except Exception:
                logger.warning("LLM extraction failed, falling back to regex", exc_info=True)

        # 3. Regex fallback
        parsed = self._regex.parse(query)
        return self._parsed_to_search_filters(parsed)

    def _parsed_to_search_filters(self, parsed: object) -> ApartmentSearchFilters:
        """Convert legacy ApartmentQueryParseResult to ApartmentSearchFilters."""
        hard = HardFilters(
            city=getattr(parsed, "city", None),
            complex_name=getattr(parsed, "complex_name", None),
            rooms=getattr(parsed, "rooms", None),
            min_price_eur=getattr(parsed, "min_price_eur", None),
            max_price_eur=getattr(parsed, "max_price_eur", None),
            min_area_m2=getattr(parsed, "min_area_m2", None),
            max_area_m2=getattr(parsed, "max_area_m2", None),
            min_floor=getattr(parsed, "min_floor", None),
            max_floor=getattr(parsed, "max_floor", None),
            view_tags=getattr(parsed, "view_tags", None) or [],
            is_furnished=getattr(parsed, "is_furnished", None),
        )
        return ApartmentSearchFilters(
            hard=hard,
            soft=SoftPreferences(),
            meta=ExtractionMeta(
                source="regex",
                confidence=getattr(parsed, "confidence", "LOW"),
                score=getattr(parsed, "score", 0),
                conflicts=getattr(parsed, "conflicts", []),
                missing_fields=getattr(parsed, "missing_fields", []),
                normalized_query=getattr(parsed, "raw_query", ""),
                semantic_remainder=getattr(parsed, "semantic_query", ""),
            ),
        )

    async def _cache_get(self, query: str) -> ApartmentSearchFilters | None:
        if not self._redis:
            return None
        key = _CACHE_PREFIX + hashlib.sha256(query.lower().encode()).hexdigest()[:16]
        try:
            data = await self._redis.get(key)
            if not data:
                return None
            return ApartmentSearchFilters.model_validate_json(data)
        except Exception:
            logger.warning("Failed to deserialize cached extraction", exc_info=True)
            return None

    async def _cache_set(self, query: str, result: ApartmentSearchFilters) -> None:
        if not self._redis:
            return
        key = _CACHE_PREFIX + hashlib.sha256(query.lower().encode()).hexdigest()[:16]
        try:
            await self._redis.set(key, result.model_dump_json(), ex=_CACHE_TTL)
        except Exception:
            logger.warning("Failed to cache extraction result", exc_info=True)
