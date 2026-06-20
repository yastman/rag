"""Catalog/property handlers extracted from ``telegram_bot/bot.py``.

Split #2816: extracted ``_send_property_card``, ``_handle_search``,
``_handle_services``, ``_handle_viewing``, ``_handle_ask``,
``handle_ask_callback``, ``handle_results_callback``, ``handle_card_callback``,
``handle_cta_callback``, ``handle_service_callback`` as module-level functions.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from telegram_bot._bot_state_helpers import (
    _state_apartment_results,
    _state_control_message_id,
)
from telegram_bot.constants import STALE_RESULTS_CALLBACK_TEXT as _STALE_RESULTS_CALLBACK_TEXT
from telegram_bot.handlers.handoff import start_qualification


if TYPE_CHECKING:  # pragma: no cover
    from aiogram.fsm.context import FSMContext
    from aiogram.types import CallbackQuery, Message

    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)

# FAQ query map — mirrors PropertyBot._ASK_QUERIES
_ASK_QUERIES: dict[str, str] = {
    "ask:docs": "Какие документы нужны для покупки?",
    "ask:costs": "Сколько стоит оформление сделки?",
    "ask:vnzh": "Как получить ВНЖ в Болгарии?",
    "ask:installment": "Какие условия рассрочки?",
}


async def _send_property_card(
    bot: PropertyBot,
    message: Message,
    result: dict,
    telegram_id: int,
) -> Any:
    """Send a single property card with preview photo and action buttons (#722)."""
    from aiogram.types import FSInputFile, InputMediaPhoto

    from telegram_bot.keyboards.property_card import (
        build_card_buttons,
        format_property_card,
        get_demo_photo_paths,
    )

    p = result.get("payload", {})
    card = format_property_card(
        property_id=result["id"],
        complex_name=p.get("complex_name", ""),
        location=p.get("city", ""),
        property_type=p.get("property_type", ""),
        floor=p.get("floor", 0),
        area_m2=p.get("area_m2", 0),
        view=", ".join(p.get("view_tags", [])) or p.get("view_primary", ""),
        price_eur=p.get("price_eur", 0),
        section=p.get("section", ""),
        apartment_number=p.get("apartment_number", ""),
    )
    favorites_service = getattr(bot, "_favorites_service", None)
    is_fav = False
    if favorites_service is not None:
        is_fav = await favorites_service.is_favorited(telegram_id, result["id"])
    demo_photos = get_demo_photo_paths()
    reply_markup = build_card_buttons(
        result["id"],
        is_favorited=is_fav,
    )
    photo_message_ids: list[int] = []
    if demo_photos:
        try:
            media = [InputMediaPhoto(media=FSInputFile(path)) for path in demo_photos]
            sent_photos = await message.answer_media_group(media=media)  # type: ignore[arg-type]
            photo_message_ids = [m.message_id for m in sent_photos]
        except Exception:
            logger.warning("Failed to send photo album, falling back to text", exc_info=True)

    card_msg = await message.answer(card, reply_markup=reply_markup)
    card_msg._photo_message_ids = photo_message_ids  # type: ignore[attr-defined]
    return card_msg


async def _handle_search(
    bot: PropertyBot,
    message: Message,
    dialog_manager: Any = None,
) -> None:
    """Start property search funnel via aiogram-dialog (#628, #658)."""
    if dialog_manager is not None:
        from aiogram_dialog import StartMode

        from telegram_bot.dialogs.states import FunnelSG

        await dialog_manager.start(FunnelSG.city, mode=StartMode.RESET_STACK)
    else:
        await bot.handle_menu_action_text(message, "Подбери апартаменты")


async def _handle_services(
    bot: PropertyBot,
    message: Message,
    i18n: Any = None,
) -> None:
    """Show services inline menu (#628)."""
    from telegram_bot.keyboards.services_keyboard import build_services_menu

    if i18n is not None:
        text = i18n.get("services-menu-text")
    else:
        text = "Выберите услугу, чтобы узнать подробнее:"
    kb = build_services_menu(i18n=i18n)
    await message.answer(text, reply_markup=kb)


async def _handle_viewing(
    bot: PropertyBot,
    message: Message,
    state: FSMContext,
    dialog_manager: Any = None,
) -> None:
    """Start viewing appointment wizard via aiogram-dialog (#719)."""
    if dialog_manager is not None:
        from aiogram_dialog import StartMode

        from telegram_bot.dialogs.states import ViewingSG

        await dialog_manager.start(ViewingSG.date, mode=StartMode.RESET_STACK)
    else:
        await message.answer("📅 Для записи на осмотр используйте кнопку меню.")


async def _handle_ask(
    bot: PropertyBot,
    message: Message,
    i18n: Any = None,
) -> None:
    """Show FAQ inline menu with popular questions."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    if i18n is not None:
        prompt = i18n.get("ask-prompt")
        buttons = [
            [InlineKeyboardButton(text=i18n.get("ask-docs"), callback_data="ask:docs")],
            [InlineKeyboardButton(text=i18n.get("ask-costs"), callback_data="ask:costs")],
            [InlineKeyboardButton(text=i18n.get("ask-vnzh"), callback_data="ask:vnzh")],
            [
                InlineKeyboardButton(
                    text=i18n.get("ask-installment"),
                    callback_data="ask:installment",
                )
            ],
        ]
    else:
        prompt = "💬 Напишите вопрос — мы с радостью ответим!\n\nИли выберите популярную тему:"
        buttons = [
            [
                InlineKeyboardButton(
                    text="📋 Какие документы нужны для покупки?",
                    callback_data="ask:docs",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Сколько стоит оформление сделки?",
                    callback_data="ask:costs",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Как получить ВНЖ в Болгарии?",
                    callback_data="ask:vnzh",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Какие условия рассрочки?",
                    callback_data="ask:installment",
                )
            ],
        ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(prompt, reply_markup=kb)


async def handle_ask_callback(bot: PropertyBot, callback: CallbackQuery) -> None:
    """Handle ask:* callback — route FAQ question to RAG pipeline."""
    await callback.answer()
    query_text = _ASK_QUERIES.get(callback.data or "")
    if not query_text or callback.message is None:
        return
    await bot.handle_menu_action_text(callback.message, query_text)  # type: ignore[arg-type]


async def handle_service_callback(
    bot: PropertyBot,
    callback: CallbackQuery,
    i18n: Any = None,
) -> None:
    """Handle service menu inline button clicks (#628)."""
    from src.services.content_loader import get_service_card
    from telegram_bot.keyboards.services_keyboard import (
        build_service_card_buttons,
        build_services_menu,
        parse_service_callback,
    )

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
    bot: PropertyBot,
    callback: CallbackQuery,
    state: FSMContext,
    dialog_manager: Any = None,
) -> None:
    """Handle CTA button clicks (get_offer, manager) (#628)."""
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
        if bot._forum_bridge is not None:
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


async def handle_results_callback(
    bot: PropertyBot,
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: Any = None,
    dialog_manager: Any = None,
) -> None:
    """Handle property results callbacks (more/refine/viewing) (#654)."""
    from aiogram.types import InaccessibleMessage

    message = callback.message
    if message is not None and not isinstance(message, InaccessibleMessage):
        with contextlib.suppress(Exception):
            await message.edit_reply_markup(reply_markup=None)
        await message.answer(_STALE_RESULTS_CALLBACK_TEXT)
    await callback.answer()


async def handle_card_callback(
    bot: PropertyBot,
    callback: CallbackQuery,
    state: FSMContext,
    dialog_manager: Any = None,
) -> None:
    """Handle card action callbacks: card:viewing, card:ask (#722)."""
    from telegram_bot.handlers.phone_collector import start_phone_collection

    data = callback.data or ""
    parts = data.split(":", 2)
    if len(parts) < 3 or not callback.from_user:
        await callback.answer()
        return

    action = parts[1]  # "viewing" or "ask"
    property_id = parts[2]

    state_data = await state.get_data()
    apt_results = _state_apartment_results(state_data)
    matched = next(
        (r for r in apt_results if isinstance(r, dict) and r.get("id") == property_id),
        None,
    )
    viewing_objects: list[dict] = []
    if matched:
        p = matched.get("payload", {})
        viewing_objects.append(
            {
                "id": property_id,
                "complex_name": p.get("complex_name", ""),
                "property_type": p.get("property_type", ""),
                "area_m2": p.get("area_m2", 0),
                "price_eur": p.get("price_eur", 0),
            }
        )
    else:
        favorites_service = getattr(bot, "_favorites_service", None)
        if favorites_service is not None:
            fav_items = await favorites_service.list(telegram_id=callback.from_user.id)
            for fav in fav_items:
                if fav.property_id == property_id:
                    d = fav.property_data
                    viewing_objects.append(
                        {
                            "id": fav.property_id,
                            "complex_name": d.get("complex_name", ""),
                            "property_type": d.get("property_type", ""),
                            "area_m2": d.get("area_m2", 0),
                            "price_eur": d.get("price_eur", 0),
                        }
                    )
                    break

    if action == "viewing":
        if dialog_manager is not None:
            from aiogram_dialog import ShowMode, StartMode

            from telegram_bot.dialogs.states import ViewingSG

            control_message_id = _state_control_message_id(state_data)
            cb_bot = callback.bot
            if (
                control_message_id
                and cb_bot is not None
                and callback.message
                and callback.message.chat
            ):
                with contextlib.suppress(Exception):
                    await cb_bot.delete_message(
                        callback.message.chat.id,
                        control_message_id,
                    )

            await dialog_manager.start(
                ViewingSG.date,
                mode=StartMode.RESET_STACK,
                show_mode=ShowMode.DELETE_AND_SEND,
                data={"selected_objects": viewing_objects},
            )
        else:
            await start_phone_collection(
                callback,
                state,
                service_key="viewing",
                viewing_objects=viewing_objects or None,
            )
    elif action == "ask":
        await start_phone_collection(
            callback,
            state,
            service_key="manager_question",
            viewing_objects=viewing_objects or None,
        )
    else:
        await callback.answer()
