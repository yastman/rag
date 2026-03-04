"""Services inline keyboard and CTA buttons (#628)."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.callback_data import CtaManagerCB, CtaOfferCB, ServiceCB
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
                    callback_data=ServiceCB(value=key).pack(),
                )
            ]
        )
    back_text = (i18n.get("svc-back") if i18n is not None else None) or "Назад"  # type: ignore[union-attr]
    rows.append(
        [InlineKeyboardButton(text=f"← {back_text}", callback_data=ServiceCB(value="back").pack())]
    )
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
                    callback_data=CtaOfferCB(action="get_offer", service_key=service_key).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"👤 {manager_text}",
                    callback_data=CtaManagerCB(action="manager").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"← {back_text}",
                    callback_data=ServiceCB(value="menu").pack(),
                )
            ],
        ]
    )


def parse_service_callback(data: str) -> tuple[str, str | None] | None:
    """Parse service/CTA callback data.

    Returns (action, param) or None.
    """
    if data.startswith(_SVC_PREFIX):
        try:
            service_cb = ServiceCB.unpack(data)
        except Exception:
            service_cb = None
        if service_cb is not None:
            if service_cb.value == "back":
                return ("back", None)
            if service_cb.value == "menu":
                return ("menu", None)
            return ("service", service_cb.value)
        value = data[len(_SVC_PREFIX) :]
        if value == "back":
            return ("back", None)
        if value == "menu":
            return ("menu", None)
        return ("service", value)

    if data.startswith(_CTA_PREFIX):
        try:
            cta_offer = CtaOfferCB.unpack(data)
        except Exception:
            cta_offer = None
        if cta_offer is not None and cta_offer.action == "get_offer":
            return ("get_offer", cta_offer.service_key)
        try:
            cta_manager = CtaManagerCB.unpack(data)
        except Exception:
            cta_manager = None
        if cta_manager is not None:
            return (cta_manager.action, None)
        parts = data[len(_CTA_PREFIX) :].split(":", 1)
        action = parts[0]
        param = parts[1] if len(parts) > 1 else None
        return (action, param)

    return None
