"""Funnel dialog — data getters (aiogram-dialog getter callables)."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from telegram_bot.dialogs.root_nav import get_main_menu_label

from ._constants import (
    _CITY_OPTIONS,
    _COMPLEX_OPTIONS,
    _PREF_ITEMS,
    _PREF_MS_ID,
    _SECTION_OPTIONS,
    _compute_active_pref_categories,
)


if TYPE_CHECKING:
    from telegram_bot.services.apartment.apartments_service import ApartmentsService

logger = logging.getLogger(__name__)


async def get_city_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for city/resort selection (Step 1)."""
    dialog_manager = kwargs.get("dialog_manager")
    middleware = getattr(dialog_manager, "middleware_data", None) or kwargs.get(
        "middleware_data", {}
    )
    i18n = middleware.get("i18n")
    btn_back = i18n.get("back") if i18n else "Назад"

    svc = middleware.get("apartments_service")
    items: list[tuple[str, str]]
    if svc is not None:
        try:
            cities = await svc.get_distinct_values("city")
            items = [(c, c) for c in cities]
        except Exception:
            logger.warning("Failed to load dynamic cities, using fallback")
            items = list(_CITY_OPTIONS[:-1])
    else:
        items = list(_CITY_OPTIONS[:-1])

    items.append(("Любой город", "any"))
    return {
        "title": "Выберите город:",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


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
    return {
        "title": "Какой тип жилья?",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


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
    return {
        "title": "Какой бюджет?",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_preferences_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for preferences multi-select menu (Step 4).

    Syncs Multiselect widget state from dialog_data so checkmarks reflect
    actual selections. The "done" button is a separate Button widget.
    """
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    dialog_manager = kwargs.get("dialog_manager")
    data: dict[str, Any] = {}
    if dialog_manager is not None:
        data = getattr(dialog_manager, "dialog_data", {})

    btn_back = i18n.get("back") if i18n else "Назад"

    if dialog_manager is not None:
        with contextlib.suppress(AttributeError):
            dialog_manager.current_context().widget_data[_PREF_MS_ID] = (
                _compute_active_pref_categories(data)
            )

    return {
        "title": "✨ Есть ли дополнительные пожелания?",
        "items": _PREF_ITEMS,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_pref_floor_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for floor sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("0-1 этаж", "low"),
        ("2-3 этаж", "mid"),
        ("4-5 этаж", "high"),
        ("6+ этаж", "top"),
        ("Любой этаж", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {
        "title": "Какой этаж предпочитаете?",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_pref_view_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for view sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Море", "sea"),
        ("Бассейн", "pool"),
        ("Газон/сад", "garden"),
        ("Лес/горы", "forest"),
        ("Любой вид", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {
        "title": "Какой вид предпочитаете?",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_pref_furnished_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for furnished sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("С мебелью", "yes"),
        ("Без мебели", "no"),
        ("Не важно", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {
        "title": "Меблировка:",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_pref_promotion_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for promotion sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Только акции", "yes"),
        ("Неважно", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {
        "title": "Специальные акции:",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_pref_area_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for area sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("До 40 m²", "small"),
        ("40–60 m²", "mid"),
        ("60–80 m²", "large"),
        ("80–120 m²", "xlarge"),
        ("120+ m²", "xxlarge"),
        ("Любая площадь", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {
        "title": "Какую площадь предпочитаете?",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_pref_complex_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for complex sub-options in preferences."""
    dialog_manager = kwargs.get("dialog_manager")
    middleware = getattr(dialog_manager, "middleware_data", None) or kwargs.get(
        "middleware_data", {}
    )
    i18n = middleware.get("i18n")
    btn_back = i18n.get("back") if i18n else "← Назад"

    svc = middleware.get("apartments_service")
    items: list[tuple[str, str]]
    if svc is not None:
        try:
            complexes = await svc.get_distinct_values("complex_name")
            items = [(c, c) for c in complexes]
        except Exception:
            logger.warning("Failed to load dynamic complexes, using fallback")
            items = list(_COMPLEX_OPTIONS[:-1])
    else:
        items = list(_COMPLEX_OPTIONS[:-1])

    items.append(("Любой комплекс", "any"))
    return {
        "title": "Выберите комплекс:",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_pref_section_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for section sub-options in preferences."""
    dialog_manager = kwargs.get("dialog_manager")
    middleware = getattr(dialog_manager, "middleware_data", None) or kwargs.get(
        "middleware_data", {}
    )
    i18n = middleware.get("i18n")
    btn_back = i18n.get("back") if i18n else "← Назад"

    svc = middleware.get("apartments_service")
    items: list[tuple[str, str]]
    if svc is not None:
        try:
            sections = await svc.get_distinct_values("section")
            items = [(s, s) for s in sections]
        except Exception:
            logger.warning("Failed to load dynamic sections, using fallback")
            items = list(_SECTION_OPTIONS[:-1])
    else:
        items = list(_SECTION_OPTIONS[:-1])

    items.append(("Любая секция", "any"))
    return {
        "title": "Выберите секцию:",
        "items": items,
        "btn_back": btn_back,
        "btn_main_menu": get_main_menu_label(i18n),
    }


def _build_summary_lines(data: dict[str, Any]) -> list[str]:
    """Build the human-readable filter display lines for the summary window."""
    from telegram_bot.dialogs.filter_constants import (
        AREA_DISPLAY as _AREA_DISPLAY,
    )
    from telegram_bot.dialogs.filter_constants import (
        BUDGET_DISPLAY as _BUDGET_DISPLAY,
    )
    from telegram_bot.dialogs.filter_constants import (
        FLOOR_DISPLAY as _FLOOR_DISPLAY,
    )
    from telegram_bot.dialogs.filter_constants import (
        VIEW_DISPLAY as _VIEW_DISPLAY,
    )

    from ._constants import _PROPERTY_TYPE_DISPLAY

    lines: list[str] = ["Ваши параметры поиска:\n"]

    city_val = data.get("city", "any")
    lines.append(f"🏙 Город: {city_val if city_val and city_val != 'any' else 'Любой'}")

    complex_val = data.get("complex")
    if complex_val and complex_val != "any":
        lines.append(f"🏢 Комплекс: {complex_val}")

    property_type_val = data.get("property_type", "any")
    property_type_label = (
        _PROPERTY_TYPE_DISPLAY.get(property_type_val, property_type_val)
        if property_type_val and property_type_val != "any"
        else "Любой"
    )
    lines.append(f"🏠 Тип: {property_type_label}")

    budget_val = data.get("budget", "any")
    budget_label = (
        _BUDGET_DISPLAY.get(budget_val, budget_val)
        if budget_val and budget_val != "any"
        else "Любой"
    )
    lines.append(f"💰 Бюджет: {budget_label}")

    floor_val = data.get("floor")
    if floor_val and floor_val != "any":
        lines.append(f"🏗 Этаж: {_FLOOR_DISPLAY.get(floor_val, floor_val)}")

    view_val = data.get("view")
    if view_val and view_val != "any":
        lines.append(f"🌅 Вид: {_VIEW_DISPLAY.get(view_val, view_val)}")

    area_val = data.get("area")
    if area_val and area_val != "any":
        lines.append(f"📐 Площадь: {_AREA_DISPLAY.get(area_val, area_val)}")

    section_val = data.get("section")
    if section_val and section_val != "any":
        lines.append(f"📍 Секция: {section_val}")

    furnished_val = data.get("is_furnished")
    if furnished_val == "yes":
        lines.append("🛋 Меблировка: С мебелью")
    elif furnished_val == "no":
        lines.append("🛋 Меблировка: Без мебели")

    promotion_val = data.get("is_promotion")
    if promotion_val == "yes":
        lines.append("🎁 Акции: Только акции")

    return lines


async def _count_apartments_for_summary(
    svc: ApartmentsService,
    data: dict[str, Any],
) -> int:
    """Count apartments matching funnel filters; returns 0 on any error."""
    try:
        from ._constants import _build_funnel_filters

        filters = _build_funnel_filters(data)
        return await svc.count_with_filters(filters=filters)
    except Exception:
        logger.exception("Failed to count apartments for summary")
        return 0


async def get_summary_data(**kwargs: Any) -> dict[str, Any]:
    """Getter for summary window — shows selected filters and can_search flag."""
    dialog_manager = kwargs.get("dialog_manager")
    data: dict[str, Any] = {}
    if dialog_manager is not None:
        data = getattr(dialog_manager, "dialog_data", {})
        start = getattr(dialog_manager, "start_data", None) or {}
        if start and not data:
            data.update(start)

    lines = _build_summary_lines(data)
    summary_text = "\n".join(lines)

    svc = None
    if dialog_manager is not None:
        middleware = getattr(dialog_manager, "middleware_data", {})
        svc = middleware.get("apartments_service")
    count = await _count_apartments_for_summary(svc, data) if svc is not None else 0
    summary_text += f"\n\nНайдено: {count} апартаментов\nСортировка: по цене ↑"

    return {
        "summary_text": summary_text,
        "can_search": True,
        "btn_main_menu": get_main_menu_label(
            getattr(dialog_manager, "middleware_data", {}).get("i18n")
            if dialog_manager is not None
            else None
        ),
    }


async def get_change_filter_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for change-filter selection window."""
    items = [
        ("Город", "city"),
        ("Тип жилья", "property_type"),
        ("Бюджет", "budget"),
    ]
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    return {
        "title": "Что хотите изменить?",
        "items": items,
        "btn_back": "← Назад",
        "btn_main_menu": get_main_menu_label(i18n),
    }
