# tests/unit/keyboards/test_catalog_keyboard.py
"""Tests for catalog mode ReplyKeyboard."""

from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard


class TestBuildCatalogKeyboard:
    def test_has_4_buttons(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert len(buttons) == 4

    def test_show_more_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[0][0].text == "📥 Показать ещё 10"

    def test_counter_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[0][1].text == "10 из 47"

    def test_filters_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[1][0].text == "🔍 Фильтры"

    def test_main_menu_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[1][1].text == "🏠 Главное меню"

    def test_all_shown_replaces_button(self):
        kb = build_catalog_keyboard(shown=47, total=47)
        assert kb.keyboard[0][0].text == "✅ Все 47 показаны"

    def test_resize_keyboard_true(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.resize_keyboard is True
