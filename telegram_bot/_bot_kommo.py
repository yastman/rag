"""Pure Kommo CRM helpers extracted from ``telegram_bot/bot.py`` (#1265).

Slice 1 PR-6 of the published bot.py decomposition plan — the final
slice that closes Slice 1.

Owns the Kommo access-token seeding helper used during bot startup to
populate the Redis-backed token store from a long-lived
``KOMMO_ACCESS_TOKEN`` env var when no OAuth refresh token is available.

Module-level imports are stdlib only. The lazy import of the canonical
``REDIS_KEY`` constant from ``src.services.kommo_tokens`` (PR #2030)
stays inside the function body, just as on dev. No aiogram / langgraph /
langchain / fastapi / redis / qdrant_client at module scope.

Owned helpers (verbatim, byte-for-byte semantics with the pre-extract
``bot.py`` definition; pinned by
``tests/contract/test_bot_kommo_extraction_contract.py``):

  - ``_seed_kommo_access_token`` — seed Redis with ``KOMMO_ACCESS_TOKEN``
    when no auth_code is configured and Redis has no existing tokens.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


async def _seed_kommo_access_token(
    *,
    redis: Any,
    access_token: str,
    subdomain: str,
) -> bool:
    """Seed Redis with access_token from env when no auth_code and Redis empty.

    Returns True if seeded, False if skipped.
    """
    from .services.kommo_tokens import REDIS_KEY

    if not access_token:
        return False
    existing = await redis.hgetall(REDIS_KEY)
    if existing:
        return False
    await redis.hset(
        REDIS_KEY,
        mapping={
            "access_token": access_token,
            "subdomain": subdomain,
        },
    )
    logger.info("Kommo: seeded Redis from KOMMO_ACCESS_TOKEN (no refresh_token)")
    return True
