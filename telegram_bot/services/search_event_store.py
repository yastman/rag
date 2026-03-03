"""Append-only store for apartment search events (asyncpg)."""

from __future__ import annotations

import json
import json as _json
import logging
from datetime import datetime
from typing import Any

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


class SearchEventStore:
    """Tracks apartment_search filter usage for CRM enrichment."""

    def __init__(self, *, pool: Any) -> None:
        self._pool = pool

    @observe(name="search-event-append")
    async def append(
        self,
        user_id: int,
        session_id: str,
        query: str,
        filters: dict[str, Any] | None = None,
        results_count: int = 0,
    ) -> None:
        """Append a search event (fire-and-forget safe)."""
        await self._pool.execute(
            """
            INSERT INTO search_events
                (user_id, session_id, event_type, query, filters, results_count)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            """,
            user_id,
            session_id,
            "apartment_search",
            query,
            json.dumps(filters) if filters else None,
            results_count,
        )

    @observe(name="search-event-get-user")
    async def get_user_events(
        self,
        user_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent search events for a user, newest first."""
        rows = await self._pool.fetch(
            """
            SELECT event_type, query, filters, results_count, created_at
            FROM search_events
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        return [dict(r) for r in rows]


_FILTER_LABELS: dict[str, str] = {
    "rooms": "комн.",
    "complex_name": "комплекс",
    "is_furnished": "мебель",
}


def _format_filters(filters: dict[str, Any] | str | None) -> str:
    """Format filters dict to human-readable string."""
    if not filters:
        return ""
    if isinstance(filters, str):
        filters = _json.loads(filters)

    parts: list[str] = []
    if "rooms" in filters:
        parts.append(f"{filters['rooms']} комн.")
    if "price_eur" in filters:
        p = filters["price_eur"]
        if isinstance(p, dict):
            lo = p.get("gte")
            hi = p.get("lte")
            if lo and hi:
                parts.append(f"€{lo:,.0f}–€{hi:,.0f}")
            elif hi:
                parts.append(f"до €{hi:,.0f}")
            elif lo:
                parts.append(f"от €{lo:,.0f}")
        else:
            parts.append(f"€{p:,.0f}")
    if "area_m2" in filters:
        a = filters["area_m2"]
        if isinstance(a, dict):
            lo = a.get("gte")
            hi = a.get("lte")
            if lo and hi:
                parts.append(f"{lo}–{hi} м²")
            elif hi:
                parts.append(f"до {hi} м²")
            elif lo:
                parts.append(f"от {lo} м²")
    if "complex_name" in filters:
        parts.append(f"комплекс: {filters['complex_name']}")
    if "view_tags" in filters:
        parts.append(f"вид: {', '.join(filters['view_tags'])}")
    if "is_furnished" in filters:
        parts.append("мебель: да" if filters["is_furnished"] else "мебель: нет")
    if "floor" in filters:
        f = filters["floor"]
        if isinstance(f, dict):
            lo = f.get("gte")
            hi = f.get("lte")
            if lo and hi and lo == hi:
                parts.append(f"{lo} эт.")
            elif lo and hi:
                parts.append(f"{lo}–{hi} эт.")
            elif hi:
                parts.append(f"до {hi} эт.")
            elif lo:
                parts.append(f"от {lo} эт.")
    return ", ".join(parts)


def format_search_summary(events: list[dict[str, Any]]) -> str:
    """Format search events list into CRM note text.

    Args:
        events: List of dicts from SearchEventStore.get_user_events().

    Returns:
        Formatted string for CRM note, or empty string if no events.
    """
    if not events:
        return ""

    count = len(events)
    lines = [
        f"🔍 История поиска ({count} запрос"
        f"{'а' if 2 <= count <= 4 else 'ов' if count >= 5 else ''})",
        "",
    ]

    for i, ev in enumerate(reversed(events), 1):  # oldest first
        query = ev.get("query", "")
        created = ev.get("created_at")
        ts = ""
        if isinstance(created, datetime):
            ts = created.strftime("%d.%m, %H:%M")
        elif isinstance(created, str):
            ts = created[:16]

        results_count = ev.get("results_count", 0)
        filters_str = _format_filters(ev.get("filters"))

        line = f'{i}. "{query}"'
        if ts:
            line += f" ({ts})"
        lines.append(line)
        if filters_str:
            lines.append(f"   Фильтры: {filters_str}")
        lines.append(f"   Найдено: {results_count} объектов")

    return "\n".join(lines)
