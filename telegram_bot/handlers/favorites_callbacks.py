"""Favorite callback handlers — fav:add/remove/viewing/viewing_all (#628)."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.callback_data import FavoriteCB


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_STALE_RESULTS_CALLBACK_TEXT = "Это устаревшая кнопка. Используйте актуальное меню ниже."


def _state_apartment_results(state_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract apartment results from state data, checking catalog_runtime first."""
    if not isinstance(state_data, dict):
        return []
    catalog_runtime = state_data.get("catalog_runtime")
    if catalog_runtime and isinstance(catalog_runtime, dict):
        results = catalog_runtime.get("results")
        if isinstance(results, list):
            return results
    results = state_data.get("apartment_results")
    if isinstance(results, list):
        return results
    return []


async def handle_fav_add(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    favorites_service: Any | None = None,
) -> None:
    """Handle fav:add:{property_id} — add to favorites (#628)."""
    if not callback.from_user:
        await callback.answer()
        return
    property_id = callback_data.apartment_id if callback_data is not None else ""
    if not property_id:
        await callback.answer()
        return

    if favorites_service is None:
        await callback.answer("Закладки недоступны")
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
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    favorites_service: Any | None = None,
) -> None:
    """Handle fav:remove:{property_id} — remove from favorites (#628)."""
    if not callback.from_user:
        await callback.answer()
        return
    property_id = callback_data.apartment_id if callback_data is not None else ""
    if not property_id:
        await callback.answer()
        return

    if favorites_service is None:
        await callback.answer("Закладки недоступны")
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
        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(
                reply_markup=build_card_buttons_for_results(property_id, is_favorited=False)
            )
    elif is_bookmark_message and callback.message:
        with contextlib.suppress(Exception):
            await callback.message.delete()
    await callback.answer("Удалено из закладок")


def build_card_buttons_for_results(property_id: str, is_favorited: bool) -> Any:
    """Build card buttons for search results (used when favorites state changes)."""
    from telegram_bot.keyboards.property_card import build_card_buttons

    return build_card_buttons(property_id, is_favorited=is_favorited)


async def handle_fav_viewing(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    favorites_service: Any | None = None,
) -> None:
    """Handle fav:viewing:{property_id} — request viewing for favorited property."""
    if not callback.from_user:
        await callback.answer()
        return
    property_id = callback_data.apartment_id if callback_data is not None else ""
    if not property_id:
        await callback.answer()
        return

    from telegram_bot.handlers.phone_collector import start_phone_collection

    viewing_objects: list[dict[str, Any]] = []

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

    await start_phone_collection(
        callback,
        state,
        service_key="viewing",
        viewing_objects=viewing_objects,
    )


async def handle_fav_viewing_all(
    callback: CallbackQuery,
    state: FSMContext,
    favorites_service: Any | None = None,
) -> None:
    """Handle fav:viewing_all — request viewing for all favorited properties."""
    if not callback.from_user:
        await callback.answer()
        return

    from telegram_bot.handlers.phone_collector import start_phone_collection

    viewing_objects: list[dict[str, Any]] = []

    if favorites_service is not None:
        fav_items = await favorites_service.list(telegram_id=callback.from_user.id)
        for fav in fav_items:
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

    await start_phone_collection(
        callback,
        state,
        service_key="viewing",
        viewing_objects=viewing_objects,
    )


async def handle_favorite_callback(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FavoriteCB | None = None,
    favorites_service: Any | None = None,
) -> None:
    """Main entry point for fav:* callbacks — delegates to specific handlers (#628)."""
    data = callback.data or ""

    # Parse callback data for legacy string-based calls
    if callback_data is not None and hasattr(callback_data, "action"):
        action = callback_data.action
        property_id = getattr(callback_data, "apartment_id", None) or ""
    else:
        parts = data.split(":", 2)
        if len(parts) < 2:
            await callback.answer()
            return
        action = parts[1]
        property_id = parts[2] if len(parts) > 2 else ""

    # Dispatch to specific handlers
    if action == "add":
        # Build FavoriteCB-like object for handle_fav_add
        class _FakeFavoriteCB:
            def __init__(self, apt_id):
                self.apartment_id = apt_id

        await handle_fav_add(
            callback,
            state,
            callback_data=_FakeFavoriteCB(property_id) if property_id else None,
            favorites_service=favorites_service,
        )
    elif action == "remove":

        class _FakeFavoriteCB:
            def __init__(self, apt_id):
                self.apartment_id = apt_id

        await handle_fav_remove(
            callback,
            state,
            callback_data=_FakeFavoriteCB(property_id) if property_id else None,
            favorites_service=favorites_service,
        )
    elif action == "viewing":

        class _FakeFavoriteCB:
            def __init__(self, apt_id):
                self.apartment_id = apt_id

        await handle_fav_viewing(
            callback,
            state,
            callback_data=_FakeFavoriteCB(property_id) if property_id else None,
            favorites_service=favorites_service,
        )
    elif action == "viewing_all":
        await handle_fav_viewing_all(callback, state, favorites_service=favorites_service)
    else:
        await callback.answer()


def create_favorites_router() -> Router:
    """Create router with favorites callback handlers."""
    router = Router(name="favorites")

    router.callback_query(F.data.startswith("fav:"))(handle_favorite_callback)

    return router
