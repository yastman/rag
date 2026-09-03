"""Catalog dialog package — public re-exports (same surface as the old catalog.py)."""

from __future__ import annotations

from telegram_bot.dialogs.catalog._controls import (
    clear_catalog_controls,
    show_catalog_controls,
)
from telegram_bot.dialogs.catalog._handlers import (
    dispatch_catalog_text_action,
    on_catalog_bookmarks,
    on_catalog_filters,
    on_catalog_home,
    on_catalog_manager,
    on_catalog_more,
    on_catalog_viewing,
)
from telegram_bot.dialogs.catalog._runtime import is_catalog_state
from telegram_bot.dialogs.catalog._search import (
    activate_catalog_state,
    load_next_catalog_page,
    run_catalog_search_and_render,
    search_catalog_from_query,
)
from telegram_bot.dialogs.catalog.dialog import (
    catalog_dialog,
    on_catalog_text_input,
    on_catalog_voice_input,
)


__all__ = [
    "activate_catalog_state",
    "catalog_dialog",
    "clear_catalog_controls",
    "dispatch_catalog_text_action",
    "is_catalog_state",
    "load_next_catalog_page",
    "on_catalog_bookmarks",
    "on_catalog_filters",
    "on_catalog_home",
    "on_catalog_manager",
    "on_catalog_more",
    "on_catalog_text_input",
    "on_catalog_viewing",
    "on_catalog_voice_input",
    "run_catalog_search_and_render",
    "search_catalog_from_query",
    "show_catalog_controls",
]
