"""BANT sales funnel dialog (aiogram-dialog)."""

from __future__ import annotations

import operator
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Back, Cancel, Column, Select
from aiogram_dialog.widgets.text import Format

from .states import FunnelSG


# --- Getters (provide data to windows) ---


async def get_property_types(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for property type selection."""
    if i18n is None:
        items = [
            ("Купить квартиру", "apartment"),
            ("Купить дом", "house"),
            ("Арендовать", "rent"),
            ("Просто посмотреть", "looking"),
        ]
    else:
        items = [
            (i18n.get("funnel-buy-apartment"), "apartment"),
            (i18n.get("funnel-buy-house"), "house"),
            (i18n.get("funnel-rent"), "rent"),
            (i18n.get("funnel-just-looking"), "looking"),
        ]

    title = i18n.get("funnel-what-looking") if i18n else "Что вас интересует?"
    back = i18n.get("back") if i18n else "Назад"
    return {"title": title, "items": items, "btn_back": back}


async def get_budget_options(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for budget selection."""
    if i18n is None:
        items = [
            ("До 50 000 €", "low"),
            ("50 000 – 100 000 €", "mid"),
            ("100 000 – 200 000 €", "high"),
            ("Более 200 000 €", "premium"),
        ]
    else:
        items = [
            (i18n.get("funnel-budget-low"), "low"),
            (i18n.get("funnel-budget-mid"), "mid"),
            (i18n.get("funnel-budget-high"), "high"),
            (i18n.get("funnel-budget-premium"), "premium"),
        ]

    title = i18n.get("funnel-budget") if i18n else "Какой бюджет?"
    back = i18n.get("back") if i18n else "Назад"
    return {"title": title, "items": items, "btn_back": back}


async def get_timeline_options(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for timeline selection."""
    if i18n is None:
        items = [
            ("В ближайший месяц", "asap"),
            ("В течение 3 месяцев", "3months"),
            ("В течение полугода", "6months"),
            ("Просто присматриваюсь", "looking"),
        ]
    else:
        items = [
            (i18n.get("funnel-timeline-asap"), "asap"),
            (i18n.get("funnel-timeline-3m"), "3months"),
            (i18n.get("funnel-timeline-6m"), "6months"),
            (i18n.get("funnel-timeline-looking"), "looking"),
        ]

    title = i18n.get("funnel-timeline") if i18n else "Когда планируете?"
    back = i18n.get("back") if i18n else "Назад"
    return {"title": title, "items": items, "btn_back": back}


async def get_results_data(
    dialog_manager: DialogManager,
    i18n: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for results window — compiles funnel answers."""
    data = dialog_manager.dialog_data
    title = i18n.get("funnel-results-title") if i18n else "Подобрали для вас:"
    empty_msg = i18n.get("funnel-results-empty") if i18n else "Пока не нашли вариантов."
    back = i18n.get("back") if i18n else "Назад"
    return {
        "title": title,
        "property_type": data.get("property_type", ""),
        "budget": data.get("budget", ""),
        "timeline": data.get("timeline", ""),
        "results_text": empty_msg,  # Placeholder — Phase 2 integrates RAG
        "btn_back": back,
    }


# --- Handlers (on_click) ---


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
    """Save budget and advance to timeline."""
    manager.dialog_data["budget"] = item_id
    await manager.switch_to(FunnelSG.timeline)


async def on_timeline_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save timeline and show results."""
    manager.dialog_data["timeline"] = item_id
    await manager.switch_to(FunnelSG.results)


# --- Dialog ---


funnel_dialog = Dialog(
    # Step 1: Property type (SPIN: Situation)
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
        Cancel(Format("{btn_back}")),
        getter=get_property_types,
        state=FunnelSG.property_type,
    ),
    # Step 2: Budget (BANT: Budget)
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
    # Step 3: Timeline (BANT: Timeline)
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="timeline",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_timeline_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_timeline_options,
        state=FunnelSG.timeline,
    ),
    # Step 4: Results
    Window(
        Format("{title}\n\n{results_text}"),
        Cancel(Format("{btn_back}")),
        getter=get_results_data,
        state=FunnelSG.results,
    ),
)
