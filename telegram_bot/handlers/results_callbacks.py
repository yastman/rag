"""Results and card callback handlers — pagination, viewing requests (#654, #722)."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InaccessibleMessage

from telegram_bot.callback_data import ResultsCB


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


def _state_control_message_id(state_data: dict[str, Any]) -> int | None:
    """Extract control message ID from state data."""
    if not isinstance(state_data, dict):
        return None
    catalog_runtime = state_data.get("catalog_runtime")
    if catalog_runtime and isinstance(catalog_runtime, dict):
        control_message_id = catalog_runtime.get("control_message_id")
        if isinstance(control_message_id, int):
            return control_message_id
    return None


async def handle_results_callback(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: ResultsCB | None = None,
) -> None:
    """Handle property results callbacks (more/refine/viewing) (#654)."""
    message = callback.message
    if message is not None and not isinstance(message, InaccessibleMessage):
        with contextlib.suppress(Exception):
            await message.edit_reply_markup(reply_markup=None)
        await message.answer(_STALE_RESULTS_CALLBACK_TEXT)
    await callback.answer()


async def handle_card_callback(
    callback: CallbackQuery,
    state: FSMContext,
    dialog_manager: Any | None = None,
    favorites_service: Any | None = None,
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
            bot = callback.bot
            if (
                control_message_id
                and bot is not None
                and callback.message
                and callback.message.chat
            ):
                with contextlib.suppress(Exception):
                    await bot.delete_message(
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
                viewing_objects=viewing_objects,
            )
    elif action == "ask":
        from telegram_bot.handlers.phone_collector import start_phone_collection

        if dialog_manager is not None:
            from aiogram_dialog import StartMode

            from telegram_bot.dialogs.states import ViewingSG

            await dialog_manager.start(ViewingSG.date, mode=StartMode.RESET_STACK)
        else:
            await start_phone_collection(
                callback,
                state,
                service_key="question",
                viewing_objects=viewing_objects,
            )
    else:
        await callback.answer()


def create_results_callback_router() -> Router:
    """Create router with results and card callback handlers."""
    router = Router(name="results_callbacks")

    router.callback_query(ResultsCB.filter())(handle_results_callback)
    router.callback_query(F.data.startswith("card:"))(handle_card_callback)

    return router
