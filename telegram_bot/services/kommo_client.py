"""Re-export shim for KommoClient — canonical home is in ``src/`` (#1948 slice 4).

The actual implementation now lives in ``src/services/kommo_client.py``. This
module preserves the historical import surface so existing bot internals
(``telegram_bot/agents/crm_tools.py``, ``telegram_bot/dialogs/crm_*``,
``telegram_bot/handlers/crm_callbacks.py``) and tests that ``from
telegram_bot.services.kommo_client import KommoClient`` keep working
unchanged.

New code under ``mini_app/`` and ``src/`` should import directly from
``src.services.kommo_client``.
"""

from __future__ import annotations

from src.services.kommo_client import (
    KommoClient,
    KommoOAuthAuth,
)


__all__ = [
    "KommoClient",
    "KommoOAuthAuth",
]
