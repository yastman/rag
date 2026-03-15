"""Compatibility shim for the canonical Kommo token store.

Canonical implementation lives in :mod:`telegram_bot.services.kommo_tokens`.
This module keeps backward-compatible import path and serialized refresh behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any

from telegram_bot.observability import observe
from telegram_bot.services.kommo_tokens import KommoTokenStore as _CanonicalKommoTokenStore


class KommoTokenStore(_CanonicalKommoTokenStore):
    """Backward-compatible adapter over canonical Kommo token store.

    Keeps legacy constructor defaults used by older tests/imports while delegating
    token lifecycle/storage logic to the canonical implementation.
    """

    def __init__(
        self,
        *,
        redis: Any,
        subdomain: str,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
    ):
        super().__init__(
            redis=redis,
            client_id=client_id,
            client_secret=client_secret,
            subdomain=subdomain,
            redirect_uri=redirect_uri,
        )
        self._refresh_lock = asyncio.Lock()

    @observe(name="kommo-token-refresh", capture_input=False, capture_output=False)
    async def force_refresh(self) -> str:
        """Serialize refresh calls to avoid concurrent refresh-token races."""
        async with self._refresh_lock:
            return await super().force_refresh()
