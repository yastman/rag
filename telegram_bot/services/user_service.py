"""User CRUD service (asyncpg)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from telegram_bot.models.user import User


if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

# Locale detection from Telegram language_code
_LOCALE_MAP = {
    "ru": "ru",
    "uk": "uk",
    "en": "en",
    "be": "ru",  # Belarusian → Russian fallback
}
_DEFAULT_LOCALE = "ru"
_SUPPORTED_LOCALES = frozenset({"ru", "en", "uk"})


def detect_locale(language_code: str | None) -> str:
    """Detect locale from Telegram API language_code."""
    if not language_code:
        return _DEFAULT_LOCALE
    # Try exact match, then 2-char prefix
    code = language_code.lower().strip()
    return _LOCALE_MAP.get(code, _LOCALE_MAP.get(code[:2], _DEFAULT_LOCALE))


class UserService:
    """CRUD operations for users table (asyncpg)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_or_create(
        self,
        *,
        telegram_id: int,
        first_name: str | None = None,
        language_code: str | None = None,
    ) -> User:
        """Get existing user or create new one."""
        row = await self._pool.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id,
        )
        if row is not None:
            return self._row_to_user(row)

        locale = detect_locale(language_code)
        row = await self._pool.fetchrow(
            """INSERT INTO users (telegram_id, locale, first_name, telegram_language_code)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (telegram_id) DO UPDATE SET updated_at = NOW()
               RETURNING *""",
            telegram_id,
            locale,
            first_name,
            language_code,
        )
        return self._row_to_user(row)

    async def get_role(self, *, telegram_id: int) -> str:
        """Get user role. Returns 'client' for unknown users."""
        role = await self._pool.fetchval(
            "SELECT role FROM users WHERE telegram_id = $1",
            telegram_id,
        )
        return role or "client"

    async def get_locale(self, *, telegram_id: int) -> str:
        """Get user locale. Returns 'ru' for unknown users."""
        locale = await self._pool.fetchval(
            "SELECT locale FROM users WHERE telegram_id = $1",
            telegram_id,
        )
        return locale or _DEFAULT_LOCALE

    async def set_locale(self, *, telegram_id: int, locale: str) -> None:
        """Update user locale."""
        if locale not in _SUPPORTED_LOCALES:
            msg = f"Unsupported locale: {locale}"
            raise ValueError(msg)
        await self._pool.execute(
            """INSERT INTO users (telegram_id, locale)
               VALUES ($1, $2)
               ON CONFLICT (telegram_id)
               DO UPDATE SET locale = EXCLUDED.locale, updated_at = NOW()""",
            telegram_id,
            locale,
        )

    @staticmethod
    def _row_to_user(row: Any) -> User:
        """Convert asyncpg Row to User dataclass."""
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            locale=row["locale"],
            role=row["role"],
            first_name=row["first_name"],
            telegram_language_code=row.get("telegram_language_code"),
            notifications_enabled=row["notifications_enabled"],
        )
