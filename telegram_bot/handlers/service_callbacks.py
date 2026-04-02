"""Service and CTA callback handlers — service cards, offers (#628)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def handle_service_callback(
    callback: CallbackQuery,
    i18n: Any | None = None,
) -> None:
    """Handle service menu inline button clicks (#628)."""
    from telegram_bot.keyboards.services_keyboard import (
        build_service_card_buttons,
        build_services_menu,
        parse_service_callback,
    )
    from telegram_bot.services.content_loader import get_service_card

    parsed = parse_service_callback(callback.data or "")
    if parsed is None:
        await callback.answer()
        return

    action, param = parsed

    if action == "back":
        if callback.message:
            await callback.message.delete()  # type: ignore[union-attr]
        await callback.answer()

    elif action == "menu":
        if i18n is not None:
            text = i18n.get("services-menu-text")
        else:
            text = "Выберите услугу, чтобы узнать подробнее:"
        kb = build_services_menu(i18n=i18n)
        if callback.message:
            await callback.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
        await callback.answer()

    elif action == "service" and param:
        svc = get_service_card(param)
        if svc:
            kb = build_service_card_buttons(param, i18n=i18n)
            ftl_key = f"svc-{param.replace('_', '-')}-card"
            card_text = (i18n.get(ftl_key) if i18n is not None else None) or svc.get(
                "card_text", ""
            )
            if callback.message:
                await callback.message.edit_text(card_text, reply_markup=kb)  # type: ignore[union-attr]
        await callback.answer()

    else:
        await callback.answer()


async def handle_cta_callback(
    callback: CallbackQuery,
    state: FSMContext,
    dialog_manager: Any | None = None,
    forum_bridge: Any | None = None,
) -> None:
    """Handle CTA button clicks (get_offer, manager) (#628)."""
    from telegram_bot.handlers.handoff import start_qualification
    from telegram_bot.handlers.phone_collector import start_phone_collection
    from telegram_bot.keyboards.services_keyboard import parse_service_callback

    parsed = parse_service_callback(callback.data or "")
    if parsed is None:
        await callback.answer()
        return

    action, param = parsed

    if action == "get_offer":
        await start_phone_collection(callback, state, service_key=param or "unknown")
    elif action == "manager":
        if forum_bridge is not None:
            # Forum Topics enabled — skip goal step, context already known (#730).
            await start_qualification(
                callback,
                state=state,
                dialog_manager=dialog_manager,
                goal="services",
            )
        else:
            await start_phone_collection(callback, state, service_key="manager")
    else:
        await callback.answer()


def create_service_callback_router() -> Router:
    """Create router with service callback handlers."""
    router = Router(name="service_callbacks")

    router.callback_query(F.data.startswith("svc:"))(handle_service_callback)
    router.callback_query(F.data.startswith("cta:"))(handle_cta_callback)

    return router
