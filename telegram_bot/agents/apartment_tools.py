"""Apartment search tool for agent SDK."""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import get_client, observe
from telegram_bot.services.apartment_formatter import format_apartment_text


logger = logging.getLogger(__name__)


@tool
@observe(name="tool-apartment-search", capture_input=False, capture_output=False)
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
    ctx = (config.get("configurable") or {}).get("bot_context")
    if not ctx or not ctx.apartments_service:
        return "Сервис поиска апартаментов недоступен."

    lf = get_client()
    lf.update_current_span(input={"query": query[:100], "rooms": rooms, "max_price": max_price_eur})

    # Pipeline fallback: extract filters from query text when none provided explicitly
    _has_explicit_filters = any(
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
    pipeline = getattr(ctx, "apartment_pipeline", None)
    if not _has_explicit_filters and pipeline is not None:
        try:
            extraction = await pipeline.extract(query)
            rooms = rooms if rooms is not None else extraction.hard.rooms
            min_price_eur = (
                min_price_eur if min_price_eur is not None else extraction.hard.min_price_eur
            )
            max_price_eur = (
                max_price_eur if max_price_eur is not None else extraction.hard.max_price_eur
            )
            min_area_m2 = min_area_m2 if min_area_m2 is not None else extraction.hard.min_area_m2
            max_area_m2 = max_area_m2 if max_area_m2 is not None else extraction.hard.max_area_m2
            min_floor = min_floor if min_floor is not None else extraction.hard.min_floor
            max_floor = max_floor if max_floor is not None else extraction.hard.max_floor
            complex_name = (
                complex_name if complex_name is not None else extraction.hard.complex_name
            )
            is_furnished = (
                is_furnished if is_furnished is not None else extraction.hard.is_furnished
            )
            if not view and extraction.hard.view_tags:
                view = extraction.hard.view_tags[0]
            if extraction.meta.semantic_remainder:
                query = extraction.meta.semantic_remainder
        except Exception:
            logger.debug("Pipeline extraction in apartment_search failed", exc_info=True)

    # Build filters dict
    filters: dict = {}
    if rooms is not None:
        filters["rooms"] = rooms
    if min_price_eur is not None or max_price_eur is not None:
        price_f: dict = {}
        if min_price_eur is not None:
            price_f["gte"] = min_price_eur
        if max_price_eur is not None:
            price_f["lte"] = max_price_eur
        filters["price_eur"] = price_f
    if min_area_m2 is not None or max_area_m2 is not None:
        area_f: dict = {}
        if min_area_m2 is not None:
            area_f["gte"] = min_area_m2
        if max_area_m2 is not None:
            area_f["lte"] = max_area_m2
        filters["area_m2"] = area_f
    if min_floor is not None or max_floor is not None:
        floor_f: dict = {}
        if min_floor is not None:
            floor_f["gte"] = min_floor
        if max_floor is not None:
            floor_f["lte"] = max_floor
        filters["floor"] = floor_f
    if complex_name is not None:
        filters["complex_name"] = complex_name
    if view is not None:
        filters["view_tags"] = [view]
    if is_furnished is not None:
        filters["is_furnished"] = is_furnished

    try:
        # Embed query
        dense, sparse, colbert = await ctx.embeddings.aembed_hybrid_with_colbert(query)
        await ctx.cache.store_embedding(query, dense)
        await ctx.cache.store_sparse_embedding(query, sparse)

        results, total = await ctx.apartments_service.search_with_filters(
            dense_vector=dense,
            colbert_query=colbert or None,
            sparse_vector=sparse,
            filters=filters or None,
            top_k=20,
        )

        response = format_apartment_text(results)
        lf.update_current_span(output={"results_count": total})

        # Log search filters for CRM enrichment
        store = getattr(ctx, "search_event_store", None)
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

    except Exception:
        logger.exception("Apartment search failed")
        return "Ошибка при поиске апартаментов. Попробуйте позже."
