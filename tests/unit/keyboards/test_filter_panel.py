"""Tests for inline filter panel keyboard and text builder (Task 7 + Task 9)."""

from __future__ import annotations

from telegram_bot.callback_data import FilterPanelCB
from telegram_bot.keyboards.filter_panel import (
    build_filter_options_keyboard,
    build_filter_panel_keyboard,
    build_filter_panel_text,
)


class TestFilterPanelText:
    def test_shows_active_city_filter(self) -> None:
        text = build_filter_panel_text(
            filters={"city": "Солнечный берег", "rooms": 2},
            count=23,
        )
        assert "Солнечный берег" in text
        assert "23" in text

    def test_shows_count_with_no_filters(self) -> None:
        text = build_filter_panel_text(filters={}, count=297)
        assert "297" in text

    def test_shows_rooms_filter(self) -> None:
        text = build_filter_panel_text(filters={"rooms": 2}, count=10)
        assert "1-спальня" in text or "Комнат" in text

    def test_shows_price_filter(self) -> None:
        text = build_filter_panel_text(
            filters={"price_eur": {"gte": 50000, "lte": 100000}},
            count=5,
        )
        assert "50" in text
        assert "100" in text

    def test_shows_view_tags(self) -> None:
        text = build_filter_panel_text(
            filters={"view_tags": ["море", "горы"]},
            count=3,
        )
        assert "море" in text

    def test_shows_complex_name(self) -> None:
        text = build_filter_panel_text(
            filters={"complex_name": "Sky Garden"},
            count=7,
        )
        assert "Sky Garden" in text

    def test_shows_furnished(self) -> None:
        text = build_filter_panel_text(filters={"is_furnished": True}, count=4)
        assert "Да" in text

    def test_shows_promotion(self) -> None:
        text = build_filter_panel_text(filters={"is_promotion": True}, count=2)
        assert "Акции" in text or "акции" in text.lower()

    def test_header_present(self) -> None:
        text = build_filter_panel_text(filters={}, count=0)
        assert "апартамент" in text.lower() or "поиск" in text.lower()

    def test_found_label(self) -> None:
        text = build_filter_panel_text(filters={}, count=42)
        assert "Найдено" in text


class TestFilterPanelKeyboard:
    def test_has_9_filter_buttons(self) -> None:
        kb = build_filter_panel_keyboard()
        filter_buttons = [btn for row in kb.inline_keyboard[:3] for btn in row]
        assert len(filter_buttons) == 9

    def test_has_apply_button_with_count(self) -> None:
        kb = build_filter_panel_keyboard(count=23)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Применить" in t and "23" in t for t in texts)

    def test_has_reset_button(self) -> None:
        kb = build_filter_panel_keyboard()
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Сбросить" in t for t in texts)

    def test_has_back_button(self) -> None:
        kb = build_filter_panel_keyboard()
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Назад" in t for t in texts)

    def test_callback_data_prefix(self) -> None:
        kb = build_filter_panel_keyboard()
        first_btn = kb.inline_keyboard[0][0]
        assert first_btn.callback_data is not None
        assert first_btn.callback_data.startswith("fpanel:")

    def test_apply_callback_action(self) -> None:
        kb = build_filter_panel_keyboard(count=5)
        # Find apply button
        apply_btn = next(
            btn
            for row in kb.inline_keyboard
            for btn in row
            if btn.callback_data and "apply" in btn.callback_data
        )
        data = FilterPanelCB.unpack(apply_btn.callback_data)
        assert data.action == "apply"

    def test_reset_callback_action(self) -> None:
        kb = build_filter_panel_keyboard()
        reset_btn = next(
            btn
            for row in kb.inline_keyboard
            for btn in row
            if btn.callback_data and "reset" in btn.callback_data
        )
        data = FilterPanelCB.unpack(reset_btn.callback_data)
        assert data.action == "reset"

    def test_back_callback_action(self) -> None:
        kb = build_filter_panel_keyboard()
        back_btn = next(
            btn
            for row in kb.inline_keyboard
            for btn in row
            if btn.callback_data and "back" in btn.callback_data
        )
        data = FilterPanelCB.unpack(back_btn.callback_data)
        assert data.action == "back"

    def test_select_callback_has_field(self) -> None:
        kb = build_filter_panel_keyboard()
        city_btn = kb.inline_keyboard[0][0]
        data = FilterPanelCB.unpack(city_btn.callback_data)
        assert data.action == "select"
        assert data.field == "city"

    def test_apply_zero_count(self) -> None:
        kb = build_filter_panel_keyboard(count=0)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Применить" in t and "0" in t for t in texts)


class TestFilterOptionsKeyboard:
    """Task 9: sub-menus for each filter."""

    def test_city_options_include_known_cities(self) -> None:
        kb = build_filter_options_keyboard("city", current_value="Солнечный берег")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "✅ Солнечный берег" in texts
        assert any("Свети Влас" in t or "свети" in t.lower() for t in texts)

    def test_city_options_include_any(self) -> None:
        kb = build_filter_options_keyboard("city")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Любой" in t or "Все" in t for t in texts)

    def test_city_no_checkmark_on_unselected(self) -> None:
        kb = build_filter_options_keyboard("city", current_value="Солнечный берег")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        # "Свети Влас" should NOT have checkmark since it's not selected
        sveti_texts = [t for t in texts if "Свети Влас" in t and "✅" not in t]
        assert len(sveti_texts) > 0

    def test_rooms_options_include_studio(self) -> None:
        kb = build_filter_options_keyboard("rooms", current_value=2)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Студия" in t for t in texts)

    def test_rooms_options_checkmark_on_current(self) -> None:
        kb = build_filter_options_keyboard("rooms", current_value=2)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        # 2 rooms = "1-спальня"
        assert any("✅" in t and ("1-спальня" in t or "1 " in t) for t in texts)

    def test_budget_options_include_ranges(self) -> None:
        kb = build_filter_options_keyboard("budget", current_value="mid")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("50 000" in t for t in texts)

    def test_budget_options_checkmark_on_mid(self) -> None:
        kb = build_filter_options_keyboard("budget", current_value="mid")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("✅" in t and "50 000" in t for t in texts)

    def test_back_button_present(self) -> None:
        kb = build_filter_options_keyboard("city")
        last_row = kb.inline_keyboard[-1]
        assert any("Назад" in btn.text for btn in last_row)

    def test_back_button_callback(self) -> None:
        kb = build_filter_options_keyboard("city")
        back_btn = next(btn for row in kb.inline_keyboard for btn in row if "Назад" in btn.text)
        data = FilterPanelCB.unpack(back_btn.callback_data)
        assert data.action == "back"

    def test_set_callback_on_city_option(self) -> None:
        kb = build_filter_options_keyboard("city")
        # First non-back button should be a "set" action
        first_btn = kb.inline_keyboard[0][0]
        data = FilterPanelCB.unpack(first_btn.callback_data)
        assert data.action == "set"
        assert data.field == "city"
        assert data.value != ""

    def test_view_options_present(self) -> None:
        kb = build_filter_options_keyboard("view")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("море" in t.lower() or "Море" in t for t in texts)

    def test_furnished_options_yes_no(self) -> None:
        kb = build_filter_options_keyboard("furnished")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Да" in t for t in texts)
        assert any("Нет" in t for t in texts)

    def test_promotion_options(self) -> None:
        kb = build_filter_options_keyboard("promotion")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Да" in t for t in texts)

    def test_area_options_present(self) -> None:
        kb = build_filter_options_keyboard("area")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert len(texts) >= 2  # at least some options + back

    def test_floor_options_present(self) -> None:
        kb = build_filter_options_keyboard("floor")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert len(texts) >= 2
