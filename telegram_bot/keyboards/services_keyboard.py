"""Services inline keyboard and CTA buttons (#628)."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.services.content_loader import load_services_config


_SVC_PREFIX = "svc:"
_CTA_PREFIX = "cta:"


def build_services_menu(i18n: Any = None) -> InlineKeyboardMarkup:
    """Build inline keyboard with service list."""
    config = load_services_config()
    services = config.get("services", {})

    rows = []
    for key, svc in services.items():
        ftl_key = f"svc-{key.replace('_', '-')}-title"
        title = (i18n.get(ftl_key) if i18n is not None else None) or svc["title"]  # type: ignore[union-attr]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{svc['emoji']} {title}",
                    callback_data=svc["callback_id"],
                )
            ]
        )
    back_text = (i18n.get("svc-back") if i18n is not None else None) or "Назад"  # type: ignore[union-attr]
    rows.append([InlineKeyboardButton(text=f"← {back_text}", callback_data=f"{_SVC_PREFIX}back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_service_card_buttons(service_key: str, i18n: Any = None) -> InlineKeyboardMarkup:
    """Build CTA buttons for a service card."""
    get_offer_text = (
        i18n.get("svc-get-offer") if i18n is not None else None
    ) or "Получить предложение"  # type: ignore[union-attr]
    manager_text = (
        i18n.get("svc-contact-manager") if i18n is not None else None
    ) or "Связаться с менеджером"  # type: ignore[union-attr]
    back_text = (
        i18n.get("svc-back-to-services") if i18n is not None else None
    ) or "Назад к услугам"  # type: ignore[union-attr]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📩 {get_offer_text}",
                    callback_data=f"{_CTA_PREFIX}get_offer:{service_key}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"👤 {manager_text}",
                    callback_data=f"{_CTA_PREFIX}manager",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"← {back_text}",
                    callback_data=f"{_SVC_PREFIX}menu",
                )
            ],
        ]
    )


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
