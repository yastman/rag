"""Handler functions for the filter dialog."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InaccessibleMessage
from aiogram_dialog import DialogManager, ShowMode

from telegram_bot.dialogs.filter._state import (
    _FIELD_TO_RADIO_ID,
    _callback_intent_id,
    _clear_filter_dialog_state,
    _filters_to_dialog_data,
    _start_filter_observation,
    _state_name,
    _update_filter_observation,
)
from telegram_bot.dialogs.filter_constants import FIELD_TO_FILTER_KEY, build_filters_dict
from telegram_bot.dialogs.states import CatalogSG, FilterSG
from telegram_bot.services.catalog_session import (
    CATALOG_RUNTIME_DATA_KEY,
    build_catalog_runtime,
)


logger = logging.getLogger(__name__)


def _make_radio_handler(field: str):
    """Factory: returns on_state_changed handler for Radio widget."""

    async def handler(
        callback: CallbackQuery,
        _radio: Any,
        manager: DialogManager,
        item_id: str,
    ) -> None:
        with _start_filter_observation(
            name="dialog-filter-radio-select",
            manager=manager,
            action=f"radio-{field}",
            item_id=item_id,
            callback_data=getattr(callback, "data", None),
        ) as observation:
            if item_id == "any":
                # "Любой" selected — clear this filter
                manager.dialog_data.pop(field, None)
                manager.dialog_data.pop(FIELD_TO_FILTER_KEY.get(field, field), None)
            else:
                # Store raw item_id string — coercion happens in build_filters_dict
                manager.dialog_data[field] = item_id
            await manager.switch_to(FilterSG.hub)
            _update_filter_observation(
                observation,
                manager=manager,
                action=f"radio-{field}",
                item_id=item_id,
            )

    handler.__name__ = f"on_radio_{field}"
    return handler


on_radio_city = _make_radio_handler("city")
on_radio_rooms = _make_radio_handler("rooms")
on_radio_budget = _make_radio_handler("budget")
on_radio_view = _make_radio_handler("view")
on_radio_area = _make_radio_handler("area")
on_radio_floor = _make_radio_handler("floor")
on_radio_complex = _make_radio_handler("complex")
on_radio_furnished = _make_radio_handler("furnished")
on_radio_promotion = _make_radio_handler("promotion")


async def on_filter_dialog_start(
    start_data: dict[str, Any] | None,
    manager: DialogManager,
) -> None:
    """Pre-populate dialog_data and Radio checked states from existing filters."""
    filters = (start_data or {}).get("filters") or {}
    dialog_data = _filters_to_dialog_data(filters)
    for field in _FIELD_TO_RADIO_ID:
        manager.dialog_data.pop(field, None)
    manager.dialog_data.update(dialog_data)

    # aiogram-dialog Radio stores selection in widget_data and does not support
    # clearing via set_checked(None): it serializes None to the string "None".
    with contextlib.suppress(Exception):
        widget_data = manager.current_context().widget_data
        for radio_id in _FIELD_TO_RADIO_ID.values():
            widget_data.pop(radio_id, None)

    # Sync Radio widget checked states with dialog_data
    for field, radio_id in _FIELD_TO_RADIO_ID.items():
        value = dialog_data.get(field)
        if value is None:
            continue
        with contextlib.suppress(Exception):
            radio_widget = manager.find(radio_id)
            if radio_widget is not None:
                await radio_widget.set_checked(str(value))


async def on_apply(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Apply filters and return to the catalog dialog flow."""
    from telegram_bot.dialogs.catalog import run_catalog_search_and_render

    with _start_filter_observation(
        name="dialog-filter-apply",
        manager=manager,
        action="apply",
        button_id=getattr(button, "widget_id", None),
        callback_data=getattr(callback, "data", None),
    ) as observation:
        state: FSMContext = manager.middleware_data["state"]
        dd = manager.dialog_data
        raw_filters = {k: v for k, v in dd.items() if k in FIELD_TO_FILTER_KEY}
        filters = build_filters_dict(raw_filters)
        fsm_data = await state.get_data()
        current_runtime = (
            fsm_data.get(CATALOG_RUNTIME_DATA_KEY) if isinstance(fsm_data, dict) else {}
        ) or {}

        # Fetch first page with new filters
        svc = manager.middleware_data.get("apartments_service")
        results: list = []
        total_count = 0
        next_start: float | None = None
        page_ids: list[str] | None = None
        if svc is not None:
            try:
                results, total_count, next_start, page_ids = await svc.scroll_with_filters(
                    filters=filters,
                    limit=10,
                )
            except Exception:
                logger.exception("on_apply: search failed for filters=%r", filters)
                msg = callback.message
                if msg is not None and not isinstance(msg, InaccessibleMessage):
                    await msg.answer("Не удалось выполнить поиск. Попробуйте ещё раз.")
                return

        runtime = build_catalog_runtime(
            query=current_runtime.get("query", ""),
            source=current_runtime.get("source", "catalog"),
            filters=filters,
            view_mode=current_runtime.get("view_mode", "cards"),
            results=results,
            total=total_count,
            next_offset=next_start,
            shown_item_ids=page_ids,
            bookmarks_context=bool(current_runtime.get("bookmarks_context", False)),
            origin_context=current_runtime.get("origin_context", {}),
        )
        await state.update_data(**{CATALOG_RUNTIME_DATA_KEY: runtime})

        msg = callback.message
        if msg is None or isinstance(msg, InaccessibleMessage):
            _update_filter_observation(
                observation, manager=manager, action="apply", has_message=False
            )
            return

        view_mode: str = runtime.get("view_mode", "cards")
        telegram_id = callback.from_user.id if callback.from_user else 0

        # Shared close→delete→render sequence (also used by FunnelSG).
        # Observation tracking is done after because the helper closes the dialog.
        await run_catalog_search_and_render(
            msg=msg,
            manager=manager,
            runtime=runtime,
            results=results,
            property_bot=manager.middleware_data.get("property_bot"),
            view_mode=view_mode,
            telegram_id=telegram_id,
        )
        _update_filter_observation(
            observation,
            manager=manager,
            action="apply",
            result_state=CatalogSG.empty.state if not results else CatalogSG.results.state,
            result_count=total_count,
        )


async def on_reset(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Clear all filters from dialog_data and reset Radio widgets."""
    with _start_filter_observation(
        name="dialog-filter-reset",
        manager=manager,
        action="reset",
        button_id=getattr(button, "widget_id", None),
        callback_data=getattr(callback, "data", None),
        callback_intent_id=_callback_intent_id(getattr(callback, "data", None)),
    ) as observation:
        _clear_filter_dialog_state(manager)
        state_name = _state_name(manager)
        if state_name == FilterSG.hub.state:
            await manager.update({}, show_mode=ShowMode.EDIT)
        else:
            await manager.switch_to(FilterSG.hub, show_mode=ShowMode.EDIT)
        _update_filter_observation(
            observation,
            manager=manager,
            action="reset",
            result_state=FilterSG.hub.state,
        )
