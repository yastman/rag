"""Re-export shim for content loaders — canonical home is in ``src/`` (#1948 slice 3).

The actual implementation now lives in
``src/services/content_loader.py``. This module preserves the historical
import surface so existing bot internals (``telegram_bot/dialogs/*``,
``telegram_bot/handlers/*``, ``telegram_bot/keyboards/*``) and unit tests
that ``patch("telegram_bot.services.content_loader.load_services_config")``
keep working unchanged.

New code under ``mini_app/`` and ``src/`` should import directly from
``src.services.content_loader`` (the layering ratchet enforces this).
"""

from __future__ import annotations

from src.services.content_loader import (
    get_entry_point_config,
    get_phone_config,
    get_promotions,
    get_service_card,
    load_mini_app_config,
    load_services_config,
)


__all__ = [
    "get_entry_point_config",
    "get_phone_config",
    "get_promotions",
    "get_service_card",
    "load_mini_app_config",
    "load_services_config",
]
