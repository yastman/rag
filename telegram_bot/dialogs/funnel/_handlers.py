"""Funnel dialog — on_click and message handlers."""

from __future__ import annotations

import logging

from aiogram.types import CallbackQuery, InaccessibleMessage
from aiogram_dialog import DialogManager
from aiogram_dialog.widgets.kbd import Button, ManagedMultiselect, Select

from telegram_bot.dialogs.states import FunnelSG

from ._constants import _SCROLL_PAGE_SIZE, _build_funnel_filters


logger = logging.getLogger(__name__)


async def on_city_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save city selection and advance to property type."""
    manager.dialog_data["city"] = item_id
    if manager.dialog_data.pop("_return_to_summary", False):
        await manager.switch_to(FunnelSG.summary)
    else:
        await manager.switch_to(FunnelSG.property_type)


async def on_property_type_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save property type and advance to budget."""
    manager.dialog_data["property_type"] = item_id
    if manager.dialog_data.pop("_return_to_summary", False):
        await manager.switch_to(FunnelSG.summary)
    else:
        await manager.switch_to(FunnelSG.budget)


async def on_budget_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save budget and advance to preferences."""
    manager.dialog_data["budget"] = item_id
    if manager.dialog_data.pop("_return_to_summary", False):
        await manager.switch_to(FunnelSG.summary)
    else:
        await manager.switch_to(FunnelSG.preferences)


async def on_pref_done(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Proceed to summary from preferences menu."""
    await manager.switch_to(FunnelSG.summary)


async def on_pref_category_selected(
    callback: CallbackQuery,
    _widget: ManagedMultiselect,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Route to the appropriate sub-option window."""
    _PREF_STATE_MAP = {
        "floor": FunnelSG.pref_floor,
        "view": FunnelSG.pref_view,
        "area": FunnelSG.pref_area,
        "furnished": FunnelSG.pref_furnished,
        "promotion": FunnelSG.pref_promotion,
        "complex": FunnelSG.pref_complex,
        "section": FunnelSG.pref_section,
    }
    target = _PREF_STATE_MAP.get(item_id)
    if target:
        await manager.switch_to(target)


async def on_pref_floor_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save floor preference and return to preferences menu."""
    manager.dialog_data["floor"] = item_id
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_view_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save view preference and return to preferences menu."""
    manager.dialog_data["view"] = item_id
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_furnished_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save furnished preference and return to preferences menu."""
    manager.dialog_data["is_furnished"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_promotion_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save promotion preference and return to preferences menu."""
    manager.dialog_data["is_promotion"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_area_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save area preference and return to preferences menu."""
    manager.dialog_data["area"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_complex_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save complex preference and return to preferences menu."""
    manager.dialog_data["complex"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_section_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save section preference and return to preferences menu."""
    manager.dialog_data["section"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_summary_search(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Search, send results as ordinary messages, then hand off to CatalogSG."""
    from telegram_bot.dialogs.catalog import run_catalog_search_and_render
    from telegram_bot.services.apartment.catalog_session import (
        CATALOG_RUNTIME_DATA_KEY,
        build_catalog_runtime,
    )

    data = manager.dialog_data
    data.pop("scroll_start_from", None)
    data.pop("scroll_seen_ids", None)
    data["scroll_page"] = 1

    msg = callback.message

    svc = manager.middleware_data.get("apartments_service")
    property_bot = manager.middleware_data.get("property_bot")
    if svc is None and property_bot is not None:
        svc = getattr(property_bot, "_apartments_service", None)

    if svc is None or msg is None or isinstance(msg, InaccessibleMessage):
        await manager.done()
        return

    try:
        filters = _build_funnel_filters(data)
        results, total_count, _next_start, _page_ids = await svc.scroll_with_filters(
            filters=filters,
            limit=_SCROLL_PAGE_SIZE,
            start_from=None,
        )
    except Exception:
        logger.exception("Failed to fetch funnel results")
        await manager.done()
        return

    view_mode = "list" if button.widget_id == "search_list" else "cards"

    state = manager.middleware_data.get("state")
    runtime = build_catalog_runtime(
        query=f"funnel:{data.get('city', 'any')}",
        source="funnel",
        filters=filters,
        view_mode=view_mode,
        results=results,
        total=total_count,
        next_offset=_next_start,
        shown_item_ids=_page_ids,
        bookmarks_context=False,
        origin_context={"funnel_data": dict(data)},
    )
    if state is not None:
        await state.update_data(**{CATALOG_RUNTIME_DATA_KEY: runtime})

    telegram_id = callback.from_user.id if callback.from_user else 0
    await run_catalog_search_and_render(
        msg=msg,
        manager=manager,
        runtime=runtime,
        results=results,
        property_bot=property_bot,
        view_mode=view_mode,
        telegram_id=telegram_id,
    )


async def on_change_filter_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Set return-to-summary flag and jump to selected step for editing."""
    manager.dialog_data["_return_to_summary"] = True
    _CHANGE_STATE_MAP = {
        "city": FunnelSG.city,
        "property_type": FunnelSG.property_type,
        "budget": FunnelSG.budget,
    }
    target = _CHANGE_STATE_MAP.get(item_id, FunnelSG.summary)
    await manager.switch_to(target)


async def on_zero_suggestion_selected(
    callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Apply zero-results recovery suggestion and refresh results/new search."""
    data = manager.dialog_data

    if item_id == "rm_floor":
        data.pop("floor", None)
    elif item_id == "rm_view":
        data.pop("view", None)
    elif item_id == "rm_furnished":
        data.pop("is_furnished", None)
    elif item_id == "rm_promotion":
        data.pop("is_promotion", None)
    elif item_id == "rm_area":
        data.pop("area", None)
    elif item_id == "rm_section":
        data.pop("section", None)
    elif item_id == "rm_budget":
        data["budget"] = "any"
    elif item_id == "new_search":
        for key in (
            "city",
            "complex",
            "property_type",
            "budget",
            "floor",
            "view",
            "area",
            "section",
            "is_furnished",
            "is_promotion",
            "scroll_start_from",
            "scroll_seen_ids",
            "scroll_page",
        ):
            data.pop(key, None)
        await manager.switch_to(FunnelSG.city)
        return
    else:
        return

    data.pop("scroll_start_from", None)
    data.pop("scroll_seen_ids", None)
    data["scroll_page"] = 1
    await manager.switch_to(FunnelSG.summary)
