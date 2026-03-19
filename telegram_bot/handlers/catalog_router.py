"""Legacy catalog router compatibility module.

The active client catalog flow is dialog-owned via ``telegram_bot.dialogs.catalog``.
This router stays unregistered and contains no legacy browsing handlers.
"""

from __future__ import annotations

from aiogram import Router


catalog_router = Router(name="catalog_compat")
