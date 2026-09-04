"""Favorites/bookmarks handlers extracted from ``telegram_bot/bot.py``.

Split #2816: extracted ``_handle_bookmarks``, ``handle_fav_add``,
``handle_fav_remove``, ``handle_fav_viewing``, ``handle_fav_viewing_all``,
``handle_favorite_callback`` as module-level functions.

The ``state.update_data`` call is an intentional #1232 boundary exception:
it stores bookmark-card message IDs for later UI cleanup and the
``bookmarks_context`` navigation flag; it does not drive a conversation FSM.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from telegram_bot.callback_data import FavoriteCB
from telegram_bot.observability.state_helpers import (
    _state_apartment_results,  # card_2a71ec058138: homed to observability/
)


if TYPE_CHECKING:  # pragma: no cover
    from aiogram.fsm.context import FSMContext
    from aiogram.types import CallbackQuery, Message

    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)


async def _handle_bookmarks(
    bot: PropertyBot,
    message: Message,
    state: FSMContext | None = None,
) -> None:
    """Show user's saved favorites (#628)."""
    if not message.from_user:
        return

    favorites_service = getattr(bot, "_favorites_service", None)
    if favorites_service is None:
        # Honest capability copy (#3241, evolving the #3204 wording): bookmarks
        # are an optional capability — disabled because no PostgreSQL-backed
        # favourites service was constructed, not "temporarily" anything.
        await message.answer(
            "Закладки недоступны: не подключено хранилище закладок (PostgreSQL).\n\n"
            "Запустите PostgreSQL и перезапустите бота, чтобы включить закладки."
        )
        return

    items = await favorites_service.list(telegram_id=message.from_user.id)
    if not items:
        await message.answer(
            "📌 У вас пока нет закладок.\n\nНажмите «🏠 Подбор апартаментов» чтобы найти квартиру."
        )
        return

    bookmark_message_ids: list[int] = []
    bookmark_photo_ids: dict[int, list[int]] = {}
    for fav in items:
        d = fav.property_data
        result_like = {
            "id": fav.property_id,
            "payload": {
                "complex_name": d.get("complex_name", ""),
                "city": d.get("location", ""),
                "property_type": d.get("property_type", ""),
                "floor": d.get("floor", 0),
                "area_m2": d.get("area_m2", 0),
                "view_tags": [],
                "view_primary": d.get("view", ""),
                "price_eur": d.get("price_eur", 0),
            },
        }
        sent = await bot._send_property_card(message, result_like, message.from_user.id)
        msg_id = getattr(sent, "message_id", None)
        if isinstance(msg_id, int):
            bookmark_message_ids.append(msg_id)
            photo_ids = getattr(sent, "_photo_message_ids", [])
            if photo_ids:
                bookmark_photo_ids[msg_id] = photo_ids

    if state is not None:
        await state.update_data(
            bookmarks_context=True,
            bookmark_message_ids=bookmark_message_ids,
            bookmark_photo_ids=bookmark_photo_ids,
        )


async def handle_fav_add(
    bot: PropertyBot,
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    dialog_manager: Any = None,
) -> None:
    """Handle fav:add:{property_id} — add to favorites (#628)."""
    if not callback.from_user:
        await callback.answer()
        return
    property_id = callback_data.apartment_id if callback_data is not None else ""
    if not property_id:
        await callback.answer()
        return

    favorites_service = getattr(bot, "_favorites_service", None)
    if favorites_service is None:
        await callback.answer("Закладки недоступны: PostgreSQL не подключён")
        return

    state_data = await state.get_data()
    apt_results = _state_apartment_results(state_data)
    matched = next(
        (r for r in apt_results if isinstance(r, dict) and r.get("id") == property_id),
        None,
    )
    if matched:
        payload = matched.get("payload")
        if not isinstance(payload, dict):
            property_data: dict[str, Any] = {}
        else:
            p = payload
            property_data = {
                "complex_name": p.get("complex_name", ""),
                "location": p.get("city", ""),
                "property_type": p.get("property_type", ""),
                "floor": p.get("floor", 0),
                "area_m2": p.get("area_m2", 0),
                "view": ", ".join(p.get("view_tags", [])) or p.get("view_primary", ""),
                "price_eur": p.get("price_eur", 0),
            }
    else:
        property_data = {}
    result = await favorites_service.add(
        telegram_id=callback.from_user.id,
        property_id=property_id,
        property_data=property_data,
    )
    if result:
        await callback.answer("Добавлено в закладки")
        if callback.message:
            from telegram_bot.keyboards.property_card import build_card_buttons

            with contextlib.suppress(Exception):
                await callback.message.edit_reply_markup(  # type: ignore[union-attr]
                    reply_markup=build_card_buttons(property_id, is_favorited=True)
                )
    else:
        await callback.answer("Уже в закладках")


async def handle_fav_remove(
    bot: PropertyBot,
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    dialog_manager: Any = None,
) -> None:
    """Handle fav:remove:{property_id} — remove from favorites (#628)."""
    if not callback.from_user:
        await callback.answer()
        return
    property_id = callback_data.apartment_id if callback_data is not None else ""
    if not property_id:
        await callback.answer()
        return

    favorites_service = getattr(bot, "_favorites_service", None)
    if favorites_service is None:
        await callback.answer("Закладки недоступны: PostgreSQL не подключён")
        return

    await favorites_service.remove(telegram_id=callback.from_user.id, property_id=property_id)
    state_data = await state.get_data()
    apt_results = _state_apartment_results(state_data)
    in_search_results = any(isinstance(r, dict) and r.get("id") == property_id for r in apt_results)
    raw_bookmark_ids = state_data.get("bookmark_message_ids")
    bookmark_message_ids = (
        {mid for mid in raw_bookmark_ids if isinstance(mid, int)}
        if isinstance(raw_bookmark_ids, list)
        else set()
    )
    callback_message_id = getattr(callback.message, "message_id", None)
    is_bookmark_message = (
        isinstance(callback_message_id, int) and callback_message_id in bookmark_message_ids
    )
    if in_search_results and not is_bookmark_message and callback.message:
        from telegram_bot.keyboards.property_card import build_card_buttons

        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(  # type: ignore[union-attr]
                reply_markup=build_card_buttons(property_id, is_favorited=False)
            )
        await callback.answer("Удалено из закладок")
    else:
        if callback.message:
            # Delete photo album messages linked to this card
            raw_photo_ids = state_data.get("bookmark_photo_ids", {})
            photo_ids = (
                raw_photo_ids.get(callback_message_id, [])
                if isinstance(raw_photo_ids, dict) and isinstance(callback_message_id, int)
                else []
            )
            chat_id = callback.message.chat.id
            for pid in photo_ids:
                with contextlib.suppress(Exception):
                    await callback.message.bot.delete_message(  # type: ignore[union-attr]
                        chat_id=chat_id,
                        message_id=pid,
                    )
            await callback.message.delete()  # type: ignore[union-attr]
        await callback.answer("Удалено из закладок")


async def handle_fav_viewing(
    bot: PropertyBot,
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    dialog_manager: Any = None,
) -> None:
    """Handle fav:viewing:{property_id} — book viewing for one favorite (#628)."""
    if not callback.from_user:
        await callback.answer()
        return
    property_id = callback_data.apartment_id if callback_data is not None else ""

    favorites_service = getattr(bot, "_favorites_service", None)
    if favorites_service is None:
        await callback.answer("Закладки недоступны: PostgreSQL не подключён")
        return

    fav_items = await favorites_service.list(telegram_id=callback.from_user.id)
    viewing_objs = []
    for fav in fav_items:
        if fav.property_id == property_id:
            d = fav.property_data
            viewing_objs.append(
                {
                    "id": fav.property_id,
                    "complex_name": d.get("complex_name", ""),
                    "property_type": d.get("property_type", ""),
                    "area_m2": d.get("area_m2", 0),
                    "price_eur": d.get("price_eur", 0),
                }
            )
            break
    if dialog_manager is not None:
        from aiogram_dialog import ShowMode, StartMode

        from telegram_bot.dialogs.states import ViewingSG

        await dialog_manager.start(
            ViewingSG.date,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
            data={"selected_objects": viewing_objs},
        )
    else:
        from telegram_bot.handlers.phone_collector import start_phone_collection

        await start_phone_collection(
            callback, state, service_key="viewing", viewing_objects=viewing_objs or None
        )


async def handle_fav_viewing_all(
    bot: PropertyBot,
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    dialog_manager: Any = None,
) -> None:
    """Handle fav:viewing_all — book viewing for all favorites (#628)."""
    if not callback.from_user:
        await callback.answer()
        return

    favorites_service = getattr(bot, "_favorites_service", None)
    if favorites_service is None:
        await callback.answer("Закладки недоступны: PostgreSQL не подключён")
        return

    fav_items = await favorites_service.list(telegram_id=callback.from_user.id)
    viewing_objs = []
    for fav in fav_items:
        d = fav.property_data
        viewing_objs.append(
            {
                "id": fav.property_id,
                "complex_name": d.get("complex_name", ""),
                "property_type": d.get("property_type", ""),
                "area_m2": d.get("area_m2", 0),
                "price_eur": d.get("price_eur", 0),
            }
        )
    if dialog_manager is not None:
        from aiogram_dialog import ShowMode, StartMode

        from telegram_bot.dialogs.states import ViewingSG

        await dialog_manager.start(
            ViewingSG.date,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
            data={"selected_objects": viewing_objs},
        )
    else:
        from telegram_bot.handlers.phone_collector import start_phone_collection

        await start_phone_collection(
            callback, state, service_key="viewing", viewing_objects=viewing_objs or None
        )


async def handle_favorite_callback(
    bot: PropertyBot,
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    dialog_manager: Any = None,
) -> None:
    """Backward-compat dispatcher for fav: callbacks (#628)."""
    if callback_data is None:
        data = callback.data or ""
        parts = data.split(":", 2)
        if len(parts) < 2 or not callback.from_user:
            await callback.answer()
            return
        action = parts[1]
        apt_id = parts[2] if len(parts) > 2 else ""
        callback_data = FavoriteCB(action=action, apartment_id=apt_id)

    if callback_data.action == "add":
        await handle_fav_add(bot, callback, state, callback_data, dialog_manager)
    elif callback_data.action == "remove":
        await handle_fav_remove(bot, callback, state, callback_data, dialog_manager)
    elif callback_data.action == "viewing":
        await handle_fav_viewing(bot, callback, state, callback_data, dialog_manager)
    elif callback_data.action == "viewing_all":
        await handle_fav_viewing_all(bot, callback, state, callback_data, dialog_manager)
    else:
        await callback.answer()
