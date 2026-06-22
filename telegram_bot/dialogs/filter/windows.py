"""Window definitions for the filter dialog."""

from __future__ import annotations

from aiogram_dialog import Window
from aiogram_dialog.widgets.kbd import Button, Column, Radio, Row, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from telegram_bot.dialogs.filter._state import _make_switch_trace_handler
from telegram_bot.dialogs.filter.getters import (
    get_area_data,
    get_budget_data,
    get_city_data,
    get_complex_data,
    get_floor_data,
    get_furnished_data,
    get_hub_data,
    get_promotion_data,
    get_rooms_data,
    get_view_data,
)
from telegram_bot.dialogs.filter.handlers import (
    on_apply,
    on_radio_area,
    on_radio_budget,
    on_radio_city,
    on_radio_complex,
    on_radio_floor,
    on_radio_furnished,
    on_radio_promotion,
    on_radio_rooms,
    on_radio_view,
    on_reset,
)
from telegram_bot.dialogs.root_nav import root_menu_button
from telegram_bot.dialogs.states import FilterSG


hub_window = Window(
    Format("🏠 Фильтры поиска\n\n{active_filters}\n\nНайдено: {count} апартаментов"),
    Row(
        SwitchTo(
            Const("📍 Город"),
            id="sw_city",
            state=FilterSG.city,
            on_click=_make_switch_trace_handler("open-city", FilterSG.city),
        ),
        SwitchTo(
            Const("🛏 Комнаты"),
            id="sw_rooms",
            state=FilterSG.rooms,
            on_click=_make_switch_trace_handler("open-rooms", FilterSG.rooms),
        ),
        SwitchTo(
            Const("💰 Бюджет"),
            id="sw_budget",
            state=FilterSG.budget,
            on_click=_make_switch_trace_handler("open-budget", FilterSG.budget),
        ),
    ),
    Row(
        SwitchTo(
            Const("🌅 Вид"),
            id="sw_view",
            state=FilterSG.view,
            on_click=_make_switch_trace_handler("open-view", FilterSG.view),
        ),
        SwitchTo(
            Const("📐 Площадь"),
            id="sw_area",
            state=FilterSG.area,
            on_click=_make_switch_trace_handler("open-area", FilterSG.area),
        ),
        SwitchTo(
            Const("🏢 Этаж"),
            id="sw_floor",
            state=FilterSG.floor,
            on_click=_make_switch_trace_handler("open-floor", FilterSG.floor),
        ),
    ),
    Row(
        SwitchTo(
            Const("🏘 Комплекс"),
            id="sw_complex",
            state=FilterSG.complex_name,
            on_click=_make_switch_trace_handler("open-complex", FilterSG.complex_name),
        ),
        SwitchTo(
            Const("🛋 Мебель"),
            id="sw_furnished",
            state=FilterSG.furnished,
            on_click=_make_switch_trace_handler("open-furnished", FilterSG.furnished),
        ),
        SwitchTo(
            Const("🏷 Акции"),
            id="sw_promotion",
            state=FilterSG.promotion,
            on_click=_make_switch_trace_handler("open-promotion", FilterSG.promotion),
        ),
    ),
    Row(
        Button(
            Format("✅ Применить ({count})"),
            id="btn_apply",
            on_click=on_apply,
        ),
        Button(
            Const("🗑 Сбросить"),
            id="btn_reset",
            on_click=on_reset,
        ),
    ),
    root_menu_button(),
    getter=get_hub_data,
    state=FilterSG.hub,
)

city_window = Window(
    Const("📍 Выберите город:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_city",
            item_id_getter=lambda item: item[1],
            items="city_options",
            on_state_changed=on_radio_city,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_city",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-city", FilterSG.hub),
    ),
    getter=get_city_data,
    state=FilterSG.city,
)

rooms_window = Window(
    Const("🛏 Выберите количество комнат:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_rooms",
            item_id_getter=lambda item: item[1],
            items="rooms_options",
            on_state_changed=on_radio_rooms,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_rooms",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-rooms", FilterSG.hub),
    ),
    getter=get_rooms_data,
    state=FilterSG.rooms,
)

budget_window = Window(
    Const("💰 Выберите бюджет:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_budget",
            item_id_getter=lambda item: item[1],
            items="budget_options",
            on_state_changed=on_radio_budget,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_budget",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-budget", FilterSG.hub),
    ),
    getter=get_budget_data,
    state=FilterSG.budget,
)

view_window = Window(
    Const("🌅 Выберите вид:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_view",
            item_id_getter=lambda item: item[1],
            items="view_options",
            on_state_changed=on_radio_view,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_view",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-view", FilterSG.hub),
    ),
    getter=get_view_data,
    state=FilterSG.view,
)

area_window = Window(
    Const("📐 Выберите площадь:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_area",
            item_id_getter=lambda item: item[1],
            items="area_options",
            on_state_changed=on_radio_area,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_area",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-area", FilterSG.hub),
    ),
    getter=get_area_data,
    state=FilterSG.area,
)

floor_window = Window(
    Const("🏢 Выберите этаж:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_floor",
            item_id_getter=lambda item: item[1],
            items="floor_options",
            on_state_changed=on_radio_floor,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_floor",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-floor", FilterSG.hub),
    ),
    getter=get_floor_data,
    state=FilterSG.floor,
)

complex_window = Window(
    Const("🏘 Выберите комплекс:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_complex",
            item_id_getter=lambda item: item[1],
            items="complex_options",
            on_state_changed=on_radio_complex,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_complex",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-complex", FilterSG.hub),
    ),
    getter=get_complex_data,
    state=FilterSG.complex_name,
)

furnished_window = Window(
    Const("🛋 Наличие мебели:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_furnished",
            item_id_getter=lambda item: item[1],
            items="furnished_options",
            on_state_changed=on_radio_furnished,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_furnished",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-furnished", FilterSG.hub),
    ),
    getter=get_furnished_data,
    state=FilterSG.furnished,
)

promotion_window = Window(
    Const("🏷 Акционные предложения:"),
    Column(
        Radio(
            Format("✅ {item[0]}"),
            Format("  ◻️ {item[0]}"),
            id="r_promotion",
            item_id_getter=lambda item: item[1],
            items="promotion_options",
            on_state_changed=on_radio_promotion,
        ),
    ),
    root_menu_button(),
    SwitchTo(
        Const("← Назад"),
        id="back_promotion",
        state=FilterSG.hub,
        on_click=_make_switch_trace_handler("back-promotion", FilterSG.hub),
    ),
    getter=get_promotion_data,
    state=FilterSG.promotion,
)
