"""Funnel dialog — Window definitions and Dialog assembly."""

from __future__ import annotations

import operator

from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import (
    Back,
    Button,
    Cancel,
    Column,
    Multiselect,
    Row,
    Select,
    SwitchTo,
)
from aiogram_dialog.widgets.text import Format

from telegram_bot.dialogs.root_nav import back_to_main_menu_button, root_menu_button
from telegram_bot.dialogs.states import FunnelSG

from ._constants import _PREF_MS_ID
from ._getters import (
    get_budget_options,
    get_change_filter_options,
    get_city_options,
    get_pref_area_options,
    get_pref_complex_options,
    get_pref_floor_options,
    get_pref_furnished_options,
    get_pref_promotion_options,
    get_pref_section_options,
    get_pref_view_options,
    get_preferences_options,
    get_property_types,
    get_summary_data,
)
from ._handlers import (
    on_budget_selected,
    on_change_filter_selected,
    on_city_selected,
    on_pref_area_selected,
    on_pref_category_selected,
    on_pref_complex_selected,
    on_pref_done,
    on_pref_floor_selected,
    on_pref_furnished_selected,
    on_pref_promotion_selected,
    on_pref_section_selected,
    on_pref_view_selected,
    on_property_type_selected,
    on_summary_search,
)


funnel_dialog = Dialog(
    # Step 1: City selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="city",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_city_selected,
            ),
        ),
        root_menu_button(),
        back_to_main_menu_button(widget_id="funnel_back"),
        getter=get_city_options,
        state=FunnelSG.city,
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
        root_menu_button(),
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
        root_menu_button(),
        Back(Format("{btn_back}")),
        getter=get_budget_options,
        state=FunnelSG.budget,
    ),
    # Step 4: Preferences multi-select menu
    Window(
        Format("{title}"),
        Column(
            Multiselect(
                checked_text=Format("✓ {item[0]}"),
                unchecked_text=Format("{item[0]}"),
                id=_PREF_MS_ID,
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_category_selected,
            ),
        ),
        Button(
            Format("▶️ Нет, перейти к результатам"),
            id="pref_done",
            on_click=on_pref_done,
        ),
        root_menu_button(),
        Back(Format("{btn_back}")),
        getter=get_preferences_options,
        state=FunnelSG.preferences,
    ),
    # Step 4a: Floor sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_floor",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_floor_selected,
            ),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="pref_floor_back", state=FunnelSG.preferences),
        getter=get_pref_floor_options,
        state=FunnelSG.pref_floor,
    ),
    # Step 4b: View sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_view",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_view_selected,
            ),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="pref_view_back", state=FunnelSG.preferences),
        getter=get_pref_view_options,
        state=FunnelSG.pref_view,
    ),
    # Step 4c: Furnished sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_furnished",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_furnished_selected,
            ),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="pref_furn_back", state=FunnelSG.preferences),
        getter=get_pref_furnished_options,
        state=FunnelSG.pref_furnished,
    ),
    # Step 4d: Promotion sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_promotion",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_promotion_selected,
            ),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="pref_promo_back", state=FunnelSG.preferences),
        getter=get_pref_promotion_options,
        state=FunnelSG.pref_promotion,
    ),
    # Step 4f: Area sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_area",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_area_selected,
            ),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="pref_area_back", state=FunnelSG.preferences),
        getter=get_pref_area_options,
        state=FunnelSG.pref_area,
    ),
    # Step 4e: Complex sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_complex",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_complex_selected,
            ),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="pref_cplx_back", state=FunnelSG.preferences),
        getter=get_pref_complex_options,
        state=FunnelSG.pref_complex,
    ),
    # Step 4g: Section sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_section",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_section_selected,
            ),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="pref_section_back", state=FunnelSG.preferences),
        getter=get_pref_section_options,
        state=FunnelSG.pref_section,
    ),
    # Step 5: Summary + confirmation
    Window(
        Format("{summary_text}"),
        Row(
            Button(
                Format("📋 Списком"),
                id="search_list",
                on_click=on_summary_search,
                when="can_search",
            ),
            Button(
                Format("🏠 Карточками"),
                id="search_cards",
                on_click=on_summary_search,
                when="can_search",
            ),
        ),
        Row(
            SwitchTo(
                Format("✏️ Изменить"),
                id="change",
                state=FunnelSG.change_filter,
            ),
            Cancel(Format("Отмена")),
        ),
        root_menu_button(),
        getter=get_summary_data,
        state=FunnelSG.summary,
    ),
    # Step 5a: Change filter selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="change_filter",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_change_filter_selected,
            ),
        ),
        root_menu_button(),
        Back(Format("{btn_back}")),
        getter=get_change_filter_options,
        state=FunnelSG.change_filter,
    ),
)
