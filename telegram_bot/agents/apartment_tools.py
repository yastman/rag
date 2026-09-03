"""Apartment search tool for agent SDK."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram_bot.agents.context import BotContext, get_bot_context
from telegram_bot.agents.tooling import RunnableConfig, tool
from telegram_bot.services.apartment.apartment_formatter import format_apartment_text


if TYPE_CHECKING:
    from telegram_bot.services.apartment.apartment_extraction_pipeline import (
        ApartmentExtractionPipeline,
    )


logger = logging.getLogger(__name__)


def _has_any_filter(
    rooms: int | None,
    min_price_eur: float | None,
    max_price_eur: float | None,
    min_area_m2: float | None,
    max_area_m2: float | None,
    min_floor: int | None,
    max_floor: int | None,
    complex_name: str | None,
    view: str | None,
    is_furnished: bool | None,
) -> bool:
    """Return True if any explicit filter argument is set."""
    return any(
        v is not None
        for v in [
            rooms,
            min_price_eur,
            max_price_eur,
            min_area_m2,
            max_area_m2,
            min_floor,
            max_floor,
            complex_name,
            view,
            is_furnished,
        ]
    )


async def _apply_pipeline_extraction(
    pipeline: ApartmentExtractionPipeline,
    query: str,
    rooms: int | None,
    min_price_eur: float | None,
    max_price_eur: float | None,
    min_area_m2: float | None,
    max_area_m2: float | None,
    min_floor: int | None,
    max_floor: int | None,
    complex_name: str | None,
    view: str | None,
    is_furnished: bool | None,
) -> tuple[
    str,
    int | None,
    float | None,
    float | None,
    float | None,
    float | None,
    int | None,
    int | None,
    str | None,
    str | None,
    bool | None,
]:
    """Extract structured filters from free-text query via pipeline.

    Returns updated (query, rooms, min_price_eur, max_price_eur, min_area_m2,
    max_area_m2, min_floor, max_floor, complex_name, view, is_furnished).
    On failure, returns original values unchanged.
    """
    try:
        extraction = await pipeline.extract(query)
        h = extraction.hard
        rooms = rooms if rooms is not None else h.rooms
        min_price_eur = min_price_eur if min_price_eur is not None else h.min_price_eur
        max_price_eur = max_price_eur if max_price_eur is not None else h.max_price_eur
        min_area_m2 = min_area_m2 if min_area_m2 is not None else h.min_area_m2
        max_area_m2 = max_area_m2 if max_area_m2 is not None else h.max_area_m2
        min_floor = min_floor if min_floor is not None else h.min_floor
        max_floor = max_floor if max_floor is not None else h.max_floor
        complex_name = complex_name if complex_name is not None else h.complex_name
        is_furnished = is_furnished if is_furnished is not None else h.is_furnished
        if not view and h.view_tags:
            view = h.view_tags[0]
        if extraction.meta.semantic_remainder:
            query = extraction.meta.semantic_remainder
    except Exception:
        logger.debug("Pipeline extraction in apartment_search failed", exc_info=True)
    return (
        query,
        rooms,
        min_price_eur,
        max_price_eur,
        min_area_m2,
        max_area_m2,
        min_floor,
        max_floor,
        complex_name,
        view,
        is_furnished,
    )


def _build_range_filter(lo: float | None, hi: float | None) -> dict:
    """Build a {gte, lte} range sub-filter omitting None bounds."""
    f: dict = {}
    if lo is not None:
        f["gte"] = lo
    if hi is not None:
        f["lte"] = hi
    return f


def _build_apartment_filters(
    rooms: int | None,
    min_price_eur: float | None,
    max_price_eur: float | None,
    min_area_m2: float | None,
    max_area_m2: float | None,
    min_floor: int | None,
    max_floor: int | None,
    complex_name: str | None,
    view: str | None,
    is_furnished: bool | None,
) -> dict:
    """Assemble the Qdrant filters dict from individual filter arguments."""
    filters: dict = {}
    if rooms is not None:
        filters["rooms"] = rooms
    if min_price_eur is not None or max_price_eur is not None:
        filters["price_eur"] = _build_range_filter(min_price_eur, max_price_eur)
    if min_area_m2 is not None or max_area_m2 is not None:
        filters["area_m2"] = _build_range_filter(min_area_m2, max_area_m2)
    if min_floor is not None or max_floor is not None:
        filters["floor"] = _build_range_filter(min_floor, max_floor)
    if complex_name is not None:
        filters["complex_name"] = complex_name
    if view is not None:
        filters["view_tags"] = [view]
    if is_furnished is not None:
        filters["is_furnished"] = is_furnished
    return filters


async def _run_search_and_log(
    ctx: BotContext,
    query: str,
    filters: dict,
) -> str:
    """Embed query, search apartments, log the event, and return formatted text."""
    dense, sparse, colbert = await ctx.embeddings.aembed_hybrid_with_colbert(query)
    await ctx.cache.store_embedding(query, dense)
    await ctx.cache.store_sparse_embedding(query, sparse)

    service = ctx.apartments_service
    if service is None:
        # Unreachable via apartment_search, which guards before calling; the
        # raised error lands in the caller's except and preserves the
        # observable error message.
        raise RuntimeError("ApartmentsService is not configured")

    results, total = await service.search_with_filters(
        dense_vector=dense,
        colbert_query=colbert or None,
        sparse_vector=sparse,
        filters=filters or None,
        top_k=20,
    )

    response = format_apartment_text(results)

    store = ctx.search_event_store
    if store:
        try:
            await store.append(
                user_id=ctx.telegram_user_id,
                session_id=ctx.session_id,
                query=query,
                filters=filters or None,
                results_count=total,
            )
        except Exception:
            logger.warning("Failed to log search event", exc_info=True)

    return response


@tool
async def apartment_search(
    query: str,
    config: RunnableConfig,
    rooms: int | None = None,
    min_price_eur: float | None = None,
    max_price_eur: float | None = None,
    min_area_m2: float | None = None,
    max_area_m2: float | None = None,
    min_floor: int | None = None,
    max_floor: int | None = None,
    complex_name: str | None = None,
    view: str | None = None,
    is_furnished: bool | None = None,
) -> str:
    """Search available apartments in Fort Beach complexes.

    Use for ALL apartment/property listing queries. Supports structured filters
    and free-text semantic search.

    Args:
        query: Free-text search query (e.g. "уютная двушка у моря").
        rooms: Number of rooms (1=studio, 2=1-bedroom, 3=2-bedroom, 4=3-bedroom).
        min_price_eur: Minimum price in EUR.
        max_price_eur: Maximum price in EUR.
        min_area_m2: Minimum area in m².
        max_area_m2: Maximum area in m².
        min_floor: Minimum floor (0=ground).
        max_floor: Maximum floor.
        complex_name: Complex name (e.g. "Premier Fort Beach").
        view: View type (sea, pool, garden, forest, panorama).
        is_furnished: Whether apartment is furnished.
    """
    ctx = get_bot_context(None, config)
    if not ctx or not ctx.apartments_service:
        return "Сервис поиска апартаментов недоступен."

    # Pipeline fallback: extract filters from query text when none provided explicitly
    if not _has_any_filter(
        rooms,
        min_price_eur,
        max_price_eur,
        min_area_m2,
        max_area_m2,
        min_floor,
        max_floor,
        complex_name,
        view,
        is_furnished,
    ):
        pipeline = getattr(ctx, "apartment_pipeline", None)
        if pipeline is not None:
            (
                query,
                rooms,
                min_price_eur,
                max_price_eur,
                min_area_m2,
                max_area_m2,
                min_floor,
                max_floor,
                complex_name,
                view,
                is_furnished,
            ) = await _apply_pipeline_extraction(
                pipeline,
                query,
                rooms,
                min_price_eur,
                max_price_eur,
                min_area_m2,
                max_area_m2,
                min_floor,
                max_floor,
                complex_name,
                view,
                is_furnished,
            )

    filters = _build_apartment_filters(
        rooms,
        min_price_eur,
        max_price_eur,
        min_area_m2,
        max_area_m2,
        min_floor,
        max_floor,
        complex_name,
        view,
        is_furnished,
    )

    try:
        return await _run_search_and_log(ctx, query, filters)
    except Exception:
        logger.exception("Apartment search failed")
        return "Ошибка при поиске апартаментов. Попробуйте позже."
