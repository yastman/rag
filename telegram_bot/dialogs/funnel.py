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
    items = [
        ("Солнечный Берег", "sunny_beach"),
        ("Святой Влас", "sveti_vlas"),
        ("Елените", "elenite"),
        ("Несебр", "nessebar"),
        ("Равда", "ravda"),
        ("Бургас", "burgas"),
        ("Поморие", "pomorie"),
        ("Созополь", "sozopol"),
        ("Приморско", "primorsko"),
        ("Банско", "bansko"),
        ("София", "sofia"),
        ("Любой район", "any"),
    ]
    return {"title": "В каком районе ищете?", "items": items, "btn_back": "Назад"}


async def get_property_types(**kwargs: Any) -> dict[str, Any]:
    """Getter for property type selection."""
    items = [
        ("Студия", "studio"),
        ("1-спальня", "1bed"),
        ("2-спальни", "2bed"),
        ("3-спальни", "3bed"),
        ("Любой тип", "any"),
    ]
    return {"title": "Какой тип жилья?", "items": items, "btn_back": "Назад"}


async def get_budget_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for budget selection."""
    items = [
        ("До 50 000 €", "low"),
        ("50 000 – 100 000 €", "mid"),
        ("100 000 – 150 000 €", "high"),
        ("150 000 – 200 000 €", "premium"),
        ("Более 200 000 €", "luxury"),
        ("Любой бюджет", "any"),
    ]
    return {"title": "Какой бюджет?", "items": items, "btn_back": "Назад"}


async def get_refine_or_show_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for refine-or-show decision step."""
    items = [
        ("Показать результаты", "show"),
        ("Уточнить параметры", "refine"),
    ]
    return {"title": "Что делаем дальше?", "items": items, "btn_back": "Назад"}


async def get_floor_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for floor selection (optional refinement)."""
    items = [
        ("0-1 этаж", "low"),
        ("2-3 этаж", "mid"),
        ("4-5 этаж", "high"),
        ("6+ этаж", "top"),
        ("Любой этаж", "any"),
    ]
    return {"title": "Какой этаж предпочитаете?", "items": items, "btn_back": "Назад"}


async def get_view_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for view selection (optional refinement)."""
    items = [
        ("Море", "sea"),
        ("Бассейн", "pool"),
        ("Газон/сад", "garden"),
        ("Лес/горы", "forest"),
        ("Любой вид", "any"),
    ]
    return {"title": "Какой вид предпочитаете?", "items": items, "btn_back": "Назад"}


async def get_results_data(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for results window — compiles funnel answers."""
    data = dialog_manager.dialog_data
    return {
        "title": "Подобрали для вас:",
        "location": data.get("location", ""),
        "property_type": data.get("property_type", ""),
        "budget": data.get("budget", ""),
        "floor": data.get("floor", ""),
        "view": data.get("view", ""),
        "results_text": "Пока не нашли вариантов.",  # Phase 2: RAG integration
        "btn_back": "Назад",
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
