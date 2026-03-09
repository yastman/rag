"""Tests for inline filter panel keyboard and text builder (Task 7 + Task 9)."""

from __future__ import annotations

from telegram_bot.callback_data import FilterPanelCB
from telegram_bot.keyboards.filter_panel import (
    build_filter_options_keyboard,
    build_filter_panel_keyboard,
    build_filter_panel_text,
)


class TestFilterPanelText:
    def test_shows_city_filter(self) -> None:
        text = build_filter_panel_text(
            filters={"city": "Солнечный берег", "rooms": 2},
            count=23,
        )
        assert "Солнечный берег" in text

    def test_shows_count(self) -> None:
        text = build_filter_panel_text(
            filters={"city": "Солнечный берег", "rooms": 2},
            count=23,
        )
        assert "23" in text

    def test_shows_found_label(self) -> None:
        text = build_filter_panel_text(filters={}, count=297)
        assert "Найдено" in text

    def test_shows_count_no_filters(self) -> None:
        text = build_filter_panel_text(filters={}, count=297)
        assert "297" in text

    def test_shows_rooms(self) -> None:
        text = build_filter_panel_text(filters={"rooms": 2}, count=10)
        assert "1-спальня" in text or "Комнаты" in text

    def test_shows_price_range(self) -> None:
        text = build_filter_panel_text(
            filters={"price_eur": {"gte": 50000, "lte": 100000}},
            count=5,
        )
        assert "50" in text or "Бюджет" in text

    def test_shows_furnished(self) -> None:
        text = build_filter_panel_text(filters={"is_furnished": True}, count=3)
        assert "Мебель" in text or "Да" in text

    def test_shows_promotion(self) -> None:
        text = build_filter_panel_text(filters={"is_promotion": True}, count=8)
        assert "Акции" in text or "Да" in text


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

    def test_apply_button_zero_count_by_default(self) -> None:
        kb = build_filter_panel_keyboard()
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Применить" in t and "0" in t for t in texts)

    def test_filter_buttons_have_select_action(self) -> None:
        kb = build_filter_panel_keyboard()
        first_btn = kb.inline_keyboard[0][0]
        cb = FilterPanelCB.unpack(first_btn.callback_data)
        assert cb.action == "select"

    def test_apply_button_action(self) -> None:
        kb = build_filter_panel_keyboard(count=5)
        apply_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "Применить" in btn.text:
                    apply_btn = btn
        assert apply_btn is not None
        cb = FilterPanelCB.unpack(apply_btn.callback_data)
        assert cb.action == "apply"

    def test_reset_button_action(self) -> None:
        kb = build_filter_panel_keyboard()
        reset_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "Сбросить" in btn.text:
                    reset_btn = btn
        assert reset_btn is not None
        cb = FilterPanelCB.unpack(reset_btn.callback_data)
        assert cb.action == "reset"

    def test_back_button_action(self) -> None:
        kb = build_filter_panel_keyboard()
        back_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if "Назад" in btn.text:
                    back_btn = btn
        assert back_btn is not None
        cb = FilterPanelCB.unpack(back_btn.callback_data)
        assert cb.action == "back"


class TestFilterOptionsKeyboard:
    """Task 9: Sub-menus for each filter."""

    def test_city_options_contains_cities(self) -> None:
        kb = build_filter_options_keyboard("city", current_value="Солнечный берег")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Солнечный берег" in t for t in texts)
        assert any("Свети Влас" in t for t in texts)

    def test_city_current_value_has_checkmark(self) -> None:
        kb = build_filter_options_keyboard("city", current_value="Солнечный берег")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "✅ Солнечный берег" in texts

    def test_city_other_options_no_checkmark(self) -> None:
        kb = build_filter_options_keyboard("city", current_value="Солнечный берег")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        # Other cities should not have checkmark
        assert any(t == "Свети Влас" for t in texts)

    def test_city_options_has_any_option(self) -> None:
        kb = build_filter_options_keyboard("city")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Любой" in t or "Все" in t for t in texts)

    def test_rooms_options_contains_studio(self) -> None:
        kb = build_filter_options_keyboard("rooms", current_value=2)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Студия" in t for t in texts)

    def test_rooms_current_value_has_checkmark(self) -> None:
        kb = build_filter_options_keyboard("rooms", current_value=2)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        # rooms=2 maps to "1-спальня"
        assert any("✅" in t and "1-спальня" in t for t in texts)

    def test_budget_options_with_current(self) -> None:
        kb = build_filter_options_keyboard("budget", current_value="mid")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("✅" in t and "50 000" in t for t in texts)

    def test_back_button_present(self) -> None:
        kb = build_filter_options_keyboard("city")
        last_btn = kb.inline_keyboard[-1][0]
        assert "Назад" in last_btn.text

    def test_back_button_action_is_main(self) -> None:
        kb = build_filter_options_keyboard("city")
        last_btn = kb.inline_keyboard[-1][0]
        cb = FilterPanelCB.unpack(last_btn.callback_data)
        assert cb.action == "main"

    def test_option_buttons_have_set_action(self) -> None:
        kb = build_filter_options_keyboard("city")
        # First non-back button should have "set" action
        first_btn = kb.inline_keyboard[0][0]
        cb = FilterPanelCB.unpack(first_btn.callback_data)
        assert cb.action == "set"

    def test_option_buttons_have_correct_field(self) -> None:
        kb = build_filter_options_keyboard("city")
        first_btn = kb.inline_keyboard[0][0]
        cb = FilterPanelCB.unpack(first_btn.callback_data)
        assert cb.field == "city"

    def test_furnished_options(self) -> None:
        kb = build_filter_options_keyboard("furnished")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Да" in t for t in texts)
        assert any("Нет" in t for t in texts)

    def test_promotion_options(self) -> None:
        kb = build_filter_options_keyboard("promotion")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Да" in t for t in texts)
