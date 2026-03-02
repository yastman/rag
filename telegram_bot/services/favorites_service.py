"""CRUD service for user bookmarked properties (#628)."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any

import asyncpg


@dataclass
class Favorite:
    id: int
    property_id: str
    property_data: dict[str, Any]
    created_at: dt.datetime | None


def _parse_jsonb(val: Any) -> dict[str, Any]:
    """Deserialize JSONB value (asyncpg returns str without a registered codec)."""
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        return json.loads(val)  # type: ignore[no-any-return]
    return {}


class FavoritesService:
    """Asyncpg-backed CRUD for the user_favorites table."""

    def __init__(self, *, pool: Any) -> None:
        self._pool = pool

    async def add(
        self,
        telegram_id: int,
        property_id: str,
        property_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Insert a favorite. Returns the new row or None on duplicate."""
        try:
            row = await self._pool.fetchrow(
                """
                INSERT INTO user_favorites (telegram_id, property_id, property_data)
                VALUES ($1, $2, $3)
                RETURNING id, property_id, property_data, created_at
                """,
                telegram_id,
                property_id,
                json.dumps(property_data, ensure_ascii=False),
            )
        except asyncpg.UniqueViolationError:
            return None
        return dict(row)

    async def remove(self, telegram_id: int, property_id: str) -> bool:
        """Delete a favorite. Returns True if a row was deleted."""
        result: str = await self._pool.execute(
            "DELETE FROM user_favorites WHERE telegram_id = $1 AND property_id = $2",
            telegram_id,
            property_id,
        )
        # asyncpg returns 'DELETE N' where N is rows affected
        return result.endswith(" 1")

    async def list(self, telegram_id: int, limit: int = 50) -> list[Favorite]:
        """Return favorites for a user, newest first."""
        rows = await self._pool.fetch(
            """
            SELECT id, property_id, property_data, created_at
            FROM user_favorites
            WHERE telegram_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            telegram_id,
            limit,
        )
        return [
            Favorite(
                id=row["id"],
                property_id=row["property_id"],
                property_data=_parse_jsonb(row["property_data"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def count(self, telegram_id: int) -> int:
        """Return the total number of favorites for a user."""
        return int(
            await self._pool.fetchval(
                "SELECT COUNT(*) FROM user_favorites WHERE telegram_id = $1",
                telegram_id,
            )
        )

    async def is_favorited(self, telegram_id: int, property_id: str) -> bool:
        """Check whether a property is bookmarked by the user."""
        val = await self._pool.fetchval(
            """
            SELECT 1 FROM user_favorites
            WHERE telegram_id = $1 AND property_id = $2
            LIMIT 1
            """,
            telegram_id,
            property_id,
        )
        return val is not None
