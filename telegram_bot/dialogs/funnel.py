"""Property search funnel dialog (aiogram-dialog) — #628."""

from __future__ import annotations

import asyncio
import logging
import operator
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Back, Cancel, Column, Select
from aiogram_dialog.widgets.text import Format

from .states import FunnelSG


# --- Filter building helpers ---

_ROOMS_MAP: dict[str, int | list[int]] = {"studio": [0, 1], "1bed": 2, "2bed": 3, "3bed": 4}
_PROPERTY_TYPE_QUERY_TEXT: dict[str, str] = {
    "studio": "студия",
    "1bed": "1 спальня",
    "2bed": "2 спальни",
    "3bed": "3 спальни",
}

_BUDGET_MAP: dict[str, dict[str, int]] = {
    "low": {"lte": 50000},
    "mid": {"gte": 50000, "lte": 100000},
    "high": {"gte": 100000, "lte": 150000},
    "premium": {"gte": 150000, "lte": 200000},
    "luxury": {"gte": 200000},
}

_FLOOR_MAP: dict[str, dict[str, int]] = {
    "low": {"gte": 0, "lte": 1},
    "mid": {"gte": 2, "lte": 3},
    "high": {"gte": 4, "lte": 5},
    "top": {"gte": 6},
}

_ROOMS_DISPLAY: dict[int, str] = {
    0: "Студия",
    1: "Студия",
    2: "1-спальня",
    3: "2-спальни",
    4: "3-спальни",
}

_LOCATION_TO_CITY: dict[str, str] = {
    "sunny_beach": "Sunny Beach",
    "elenite": "Elenite",
    "nessebar": "Nesebar",
}


def _build_funnel_filters(data: dict[str, Any]) -> dict[str, Any]:
    """Build Qdrant filters from dialog_data dict."""
    return build_funnel_filters(
        rooms=data.get("property_type", "any"),
        budget=data.get("budget", "any"),
        city=data.get("location"),
        floor=data.get("floor"),
        view=data.get("view"),
    )


def _build_query_text(data: dict[str, Any]) -> str:
    """Build semantic query text without internal placeholder tokens like 'any'."""
    location_key = data.get("location")
    city = _LOCATION_TO_CITY.get(location_key, location_key) if location_key != "any" else ""

    property_type = data.get("property_type")
    prop_text = (
        _PROPERTY_TYPE_QUERY_TEXT.get(property_type, property_type)
        if property_type and property_type != "any"
        else ""
    )

    query_parts = [part.strip() for part in (city or "", prop_text or "") if str(part).strip()]
    return " ".join(query_parts) or "апартаменты в Болгарии"


def build_funnel_filters(
    *,
    rooms: str = "any",
    budget: str = "any",
    complex_name: str | None = None,
    city: str | None = None,
    floor: str | None = None,
    view: str | None = None,
) -> dict[str, Any]:
    """Build Qdrant payload filter dict from funnel dialog selections."""
    filters: dict[str, Any] = {}
    if rooms in _ROOMS_MAP:
        filters["rooms"] = _ROOMS_MAP[rooms]
    if budget in _BUDGET_MAP:
        filters["price_eur"] = _BUDGET_MAP[budget]
    if complex_name:
        filters["complex_name"] = complex_name
    if city and city != "any":
        filters["city"] = _LOCATION_TO_CITY.get(city, city)
    if floor and floor != "any" and floor in _FLOOR_MAP:
        filters["floor"] = _FLOOR_MAP[floor]
    if view and view != "any":
        filters["view_tags"] = [view]
    return filters


logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


async def _persist_funnel_lead_score_safe(**kwargs: Any) -> None:
    """Persist/sync funnel score without breaking callback flow."""
    try:
        from telegram_bot.services.funnel_lead_scoring import persist_and_sync_funnel_lead_score

        await persist_and_sync_funnel_lead_score(**kwargs)
    except Exception:
        logger.exception("Failed to persist/sync funnel lead score")


def _spawn_persist_funnel_lead_score(**kwargs: Any) -> None:
    """Run heavy side effects in the background to keep callback responsive."""
    task = asyncio.create_task(_persist_funnel_lead_score_safe(**kwargs))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


# --- Getters (provide data to windows) ---


async def get_location_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for location (district) selection."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Солнечный Берег", "sunny_beach"),
        ("Елените", "elenite"),
        ("Несебр", "nessebar"),
        ("Любой район", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "Назад"
    return {"title": "В каком районе ищете?", "items": items, "btn_back": btn_back}


async def get_property_types(**kwargs: Any) -> dict[str, Any]:
    """Getter for property type selection."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Студия", "studio"),
        ("1-спальня", "1bed"),
        ("2-спальни", "2bed"),
        ("3-спальни", "3bed"),
        ("Любой тип", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "Назад"
    return {"title": "Какой тип жилья?", "items": items, "btn_back": btn_back}


async def get_budget_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for budget selection."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("До 50 000 €", "low"),
        ("50 000 – 100 000 €", "mid"),
        ("100 000 – 150 000 €", "high"),
        ("150 000 – 200 000 €", "premium"),
        ("Более 200 000 €", "luxury"),
        ("Любой бюджет", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "Назад"
    return {"title": "Какой бюджет?", "items": items, "btn_back": btn_back}


async def get_refine_or_show_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for refine-or-show decision step."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Показать результаты", "show"),
        ("Уточнить параметры", "refine"),
    ]
    btn_back = i18n.get("back") if i18n else "Назад"
    return {"title": "Что делаем дальше?", "items": items, "btn_back": btn_back}


async def get_floor_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for floor selection (optional refinement)."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("0-1 этаж", "low"),
        ("2-3 этаж", "mid"),
        ("4-5 этаж", "high"),
        ("6+ этаж", "top"),
        ("Любой этаж", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "Назад"
    return {"title": "Какой этаж предпочитаете?", "items": items, "btn_back": btn_back}


async def get_view_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for view selection (optional refinement)."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Море", "sea"),
        ("Бассейн", "pool"),
        ("Газон/сад", "garden"),
        ("Лес/горы", "forest"),
        ("Любой вид", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "Назад"
    return {"title": "Какой вид предпочитаете?", "items": items, "btn_back": btn_back}


async def get_results_data(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for results window — fetches real apartments via hybrid search (#628)."""
    from telegram_bot.keyboards.property_card import format_property_card

    i18n = dialog_manager.middleware_data.get("i18n")
    data = dialog_manager.dialog_data

    no_results_text = (
        i18n.get("results-no-results")
        if i18n
        else "К сожалению, по вашим критериям ничего не найдено."
    )
    results_title = i18n.get("funnel-results-title") if i18n else "Подобрали для вас:"
    btn_back = i18n.get("back") if i18n else "Назад"

    # Resolve apartments_service and hybrid_embeddings with property_bot fallback
    svc = dialog_manager.middleware_data.get("apartments_service")
    embeddings = dialog_manager.middleware_data.get("hybrid_embeddings")
    if svc is None or embeddings is None:
        property_bot = dialog_manager.middleware_data.get("property_bot")
        if property_bot is not None:
            if svc is None:
                svc = getattr(property_bot, "_apartments_service", None)
            if embeddings is None:
                embeddings = getattr(property_bot, "_embeddings", None)

    results_text: str
    if svc is not None and embeddings is not None:
        try:
            location = data.get("location", "")
            city = _LOCATION_TO_CITY.get(location, location)
            query_text = _build_query_text(data)

            dense, sparse = await embeddings.aembed_hybrid(query_text)
            filters = _build_funnel_filters(data)
            results = await svc.search(
                dense_vector=dense,
                sparse_vector=sparse,
                filters=filters,
                top_k=5,
            )
            if results:
                cards = []
                for apt in results:
                    p = apt["payload"]
                    rooms_num = p.get("rooms", 1)
                    rooms_display = _ROOMS_DISPLAY.get(rooms_num, str(rooms_num))
                    cards.append(
                        format_property_card(
                            property_id=apt["id"],
                            complex_name=p.get("complex_name", ""),
                            location=p.get("city") or (city if city != "any" else "Болгария"),
                            property_type=rooms_display,
                            floor=p.get("floor", 0),
                            area_m2=p.get("area_m2", 0),
                            view=p.get("view_primary", ""),
                            price_eur=p.get("price_eur", 0),
                        )
                    )
                results_text = "\n\n".join(cards)
            else:
                results_text = no_results_text
        except Exception:
            logger.exception("Failed to fetch funnel results from Qdrant")
            results_text = no_results_text
    else:
        results_text = "Не нашли подходящих вариантов."

    return {
        "title": results_title,
        "results_text": results_text,
        "btn_back": btn_back,
    }


# --- Handlers (on_click) ---


async def on_location_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save location and advance to property type."""
    manager.dialog_data["location"] = item_id
    await manager.switch_to(FunnelSG.property_type)


async def on_property_type_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save property type and advance to budget."""
    manager.dialog_data["property_type"] = item_id
    await manager.switch_to(FunnelSG.budget)


async def on_budget_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save budget and advance to refine-or-show."""
    manager.dialog_data["budget"] = item_id
    await manager.switch_to(FunnelSG.refine_or_show)


async def on_refine_or_show_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Branch: show results immediately or go to optional refinement steps."""
    manager.dialog_data["refine_or_show"] = item_id
    if item_id == "show":
        try:
            from telegram_bot.bot import make_session_id

            if callback.from_user is not None:
                data = manager.dialog_data
                _spawn_persist_funnel_lead_score(
                    telegram_user_id=callback.from_user.id,
                    session_id=make_session_id("chat", callback.message.chat.id)
                    if callback.message is not None
                    else make_session_id("chat", callback.from_user.id),
                    property_type=data.get("property_type"),
                    budget=data.get("budget"),
                    timeline=data.get("refine_or_show"),
                    user_service=manager.middleware_data.get("user_service"),
                    pg_pool=manager.middleware_data.get("pg_pool"),
                    lead_scoring_store=manager.middleware_data.get("lead_scoring_store"),
                    kommo_client=manager.middleware_data.get("kommo_client"),
                    hot_lead_notifier=manager.middleware_data.get("hot_lead_notifier"),
                    config=manager.middleware_data.get("bot_config"),
                )
        except Exception:
            logger.exception("Failed to schedule funnel lead score persistence")

        await manager.switch_to(FunnelSG.results)
    else:
        await manager.switch_to(FunnelSG.floor)


async def on_floor_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save floor preference and advance to view selection."""
    manager.dialog_data["floor"] = item_id
    await manager.switch_to(FunnelSG.view)


async def on_view_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save view preference, persist lead score and show results."""
    manager.dialog_data["view"] = item_id

    try:
        from telegram_bot.bot import make_session_id

        if callback.from_user is not None:
            data = manager.dialog_data
            _spawn_persist_funnel_lead_score(
                telegram_user_id=callback.from_user.id,
                session_id=make_session_id("chat", callback.message.chat.id)
                if callback.message is not None
                else make_session_id("chat", callback.from_user.id),
                property_type=data.get("property_type"),
                budget=data.get("budget"),
                timeline=data.get("refine_or_show"),
                user_service=manager.middleware_data.get("user_service"),
                pg_pool=manager.middleware_data.get("pg_pool"),
                lead_scoring_store=manager.middleware_data.get("lead_scoring_store"),
                kommo_client=manager.middleware_data.get("kommo_client"),
                hot_lead_notifier=manager.middleware_data.get("hot_lead_notifier"),
                config=manager.middleware_data.get("bot_config"),
            )
    except Exception:
        logger.exception("Failed to schedule funnel lead score persistence")

    await manager.switch_to(FunnelSG.results)


# --- Dialog ---


funnel_dialog = Dialog(
    # Step 1: Location (район)
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="location",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_location_selected,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_location_options,
        state=FunnelSG.location,
    ),
    # Step 2: Property type
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="property_type",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_property_type_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_property_types,
        state=FunnelSG.property_type,
    ),
    # Step 3: Budget
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="budget",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_budget_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_budget_options,
        state=FunnelSG.budget,
    ),
    # Step 4: Refine or show
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="refine_or_show",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_refine_or_show_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_refine_or_show_options,
        state=FunnelSG.refine_or_show,
    ),
    # Step 4a: Floor (optional)
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="floor",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_floor_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_floor_options,
        state=FunnelSG.floor,
    ),
    # Step 4b: View (optional)
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="view",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_view_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_view_options,
        state=FunnelSG.view,
    ),
    # Step 5: Results
    Window(
        Format("{title}\n\n{results_text}"),
        Cancel(Format("{btn_back}")),
        getter=get_results_data,
        state=FunnelSG.results,
    ),
)
