"""Append-only store for apartment search events (asyncpg)."""

from __future__ import annotations

import json
import json as _json
import logging
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


class SearchEventStore:
    """Tracks apartment_search filter usage for CRM enrichment."""

    def __init__(self, *, pool: Any) -> None:
        self._pool = pool

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


def _format_price_filter(p: Any) -> str | None:
    """Format a price_eur filter value to a human-readable string."""
    if not isinstance(p, dict):
        return f"€{p:,.0f}"
    lo, hi = p.get("gte"), p.get("lte")
    if lo is not None and hi is not None:
        return f"€{lo:,.0f}–€{hi:,.0f}"
    if hi is not None:
        return f"до €{hi:,.0f}"
    if lo is not None:
        return f"от €{lo:,.0f}"
    return None


def _format_area_filter(a: Any) -> str | None:
    """Format an area_m2 filter value to a human-readable string."""
    if not isinstance(a, dict):
        return None
    lo, hi = a.get("gte"), a.get("lte")
    if lo is not None and hi is not None:
        return f"{lo}–{hi} м²"
    if hi is not None:
        return f"до {hi} м²"
    if lo is not None:
        return f"от {lo} м²"
    return None


def _format_floor_filter(f: Any) -> str | None:
    """Format a floor filter value to a human-readable string."""
    if not isinstance(f, dict):
        return None
    lo, hi = f.get("gte"), f.get("lte")
    if lo is not None and hi is not None and lo == hi:
        return f"{lo} эт."
    if lo is not None and hi is not None:
        return f"{lo}–{hi} эт."
    if hi is not None:
        return f"до {hi} эт."
    if lo is not None:
        return f"от {lo} эт."
    return None


def _format_filters(filters: dict[str, Any] | str | None) -> str:
    """Format filters dict to human-readable string."""
    if not filters:
        return ""
    data: dict[str, Any] = _json.loads(filters) if isinstance(filters, str) else filters

    parts: list[str] = []
    if "rooms" in data:
        parts.append(f"{data['rooms']} комн.")
    if "price_eur" in data:
        s = _format_price_filter(data["price_eur"])
        if s:
            parts.append(s)
    if "area_m2" in data:
        s = _format_area_filter(data["area_m2"])
        if s:
            parts.append(s)
    if "complex_name" in data:
        parts.append(f"комплекс: {data['complex_name']}")
    if "view_tags" in data:
        parts.append(f"вид: {', '.join(data['view_tags'])}")
    if "is_furnished" in data:
        parts.append("мебель: да" if data["is_furnished"] else "мебель: нет")
    if "floor" in data:
        s = _format_floor_filter(data["floor"])
        if s:
            parts.append(s)
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
