"""Services inline keyboard and CTA buttons (***REMOVED***628).

Keyboards are constructed with :class:`aiogram.utils.keyboard.InlineKeyboardBuilder`
to follow the SDK convention enforced by issue ***REMOVED***1238.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from telegram_bot.services.content_loader import load_services_config


_SVC_PREFIX = "svc:"
_CTA_PREFIX = "cta:"


def build_services_menu(i18n: Any = None) -> InlineKeyboardMarkup:
    """Build inline keyboard with service list (one button per row + back button)."""
    config = load_services_config()
    services = config.get("services", {})

    builder = InlineKeyboardBuilder()
    for key, svc in services.items():
        ftl_key = f"svc-{key.replace('_', '-')}-title"
        title = (i18n.get(ftl_key) if i18n is not None else None) or svc["title"]  ***REMOVED*** type: ignore[union-attr]
        builder.button(
            text=f"{svc['emoji']} {title}",
            callback_data=svc["callback_id"],
        )
    back_text = (i18n.get("svc-back") if i18n is not None else None) or "Назад"  ***REMOVED*** type: ignore[union-attr]
    builder.button(text=f"← {back_text}", callback_data=f"{_SVC_PREFIX}back")
    builder.adjust(1)
    return builder.as_markup()


def build_service_card_buttons(service_key: str, i18n: Any = None) -> InlineKeyboardMarkup:
    """Build CTA buttons for a service card (3 rows × 1 button)."""
    get_offer_text = (i18n.get("svc-get-offer") if i18n is not None else None) or "Оставить заявку"  ***REMOVED*** type: ignore[union-attr]
    manager_text = (
        i18n.get("svc-contact-manager") if i18n is not None else None
    ) or "Связаться с менеджером"  ***REMOVED*** type: ignore[union-attr]
    back_text = (
        i18n.get("svc-back-to-services") if i18n is not None else None
    ) or "Назад к услугам"  ***REMOVED*** type: ignore[union-attr]

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"📩 {get_offer_text}",
        callback_data=f"{_CTA_PREFIX}get_offer:{service_key}",
    )
    builder.button(
        text=f"👤 {manager_text}",
        callback_data=f"{_CTA_PREFIX}manager:{service_key}",
    )
    builder.button(
        text=f"← {back_text}",
        callback_data=f"{_SVC_PREFIX}menu",
    )
    builder.adjust(1)
    return builder.as_markup()


def parse_service_callback(data: str) -> tuple[str, str | None] | None:
    """Parse service/CTA callback data.

    Returns (action, param) or None.
    """
    if data.startswith(_SVC_PREFIX):
        value = data[len(_SVC_PREFIX) :]
        if value == "back":
            return ("back", None)
        if value == "menu":
            return ("menu", None)
        return ("service", value)

    if data.startswith(_CTA_PREFIX):
        parts = data[len(_CTA_PREFIX) :].split(":", 1)
        action = parts[0]
        param = parts[1] if len(parts) > 1 else None
        return (action, param)

    return None
