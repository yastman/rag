"""Bot capability boundary — dependency-light state contracts (#3324).

UI, dialogs and middlewares import capability predicates only from here.
This module must stay install-light: the core/no-service lanes import it and
it must never pull optional third-party dependencies (asyncpg, …). The owning
construction path (lifecycle ``setup_postgres``) enables the bookmarks
capability only after a validated database connection and disables it on
every degraded path and teardown (#3241).
"""

from __future__ import annotations

from typing import Any


_FAVORITES_ATTR = "_favorites_service"


def bookmarks_ready(bot: Any) -> bool:
    """Return True when bookmarks may be advertised to users (#3241).

    Bookmarks require PostgreSQL, so the capability exists only after
    ``lifecycle.setup_postgres`` validated the database and enabled the
    favourites service on the bot. Duck-typed: ``None`` or any object
    without a favourites service reads as not ready (fail closed), so UI
    builders can safely pass bots or stubs they happened to receive.
    """
    return getattr(bot, _FAVORITES_ATTR, None) is not None


def set_bookmarks_ready(bot: Any, *, service: Any | None) -> None:
    """Enable or disable the bookmarks capability explicitly.

    Lifecycle-owned: pass the constructed favourites service to enable the
    capability after a validated PostgreSQL connection, or ``None`` to
    disable it on degraded paths and teardown. Passing ``None`` keeps the
    capability fail-closed for every UI surface.
    """
    setattr(bot, _FAVORITES_ATTR, service)
