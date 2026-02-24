"""Services inline keyboard and CTA buttons (#628)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.services.content_loader import load_services_config


_SVC_PREFIX = "svc:"
_CTA_PREFIX = "cta:"


def build_services_menu() -> InlineKeyboardMarkup:
    """Build inline keyboard with service list."""
    config = load_services_config()
    services = config.get("services", {})

    rows = []
    for svc in services.values():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{svc['emoji']} {svc['title']}",
                    callback_data=svc["callback_id"],
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"{_SVC_PREFIX}back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_service_card_buttons(service_key: str) -> InlineKeyboardMarkup:
    """Build CTA buttons for a service card."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Получить предложение",
                    callback_data=f"{_CTA_PREFIX}get_offer:{service_key}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Связаться с менеджером",
                    callback_data=f"{_CTA_PREFIX}manager",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад к услугам",
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
