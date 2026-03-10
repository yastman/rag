# tests/unit/keyboards/test_catalog_keyboard.py
"""Tests for catalog mode ReplyKeyboard."""

from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard


class TestBuildCatalogKeyboard:
    def test_has_6_buttons(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert len(buttons) == 6  # show_more + filters + bookmarks + viewing + manager + main_menu

    def test_show_more_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[0][0].text == "📥 Показать ещё (10 из 47)"

    def test_filters_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[1][0].text == "🔍 Фильтры"

    def test_main_menu_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[3][0].text == "🏠 Главное меню"

    def test_all_shown_hides_more_row(self):
        """When all shown, show_more row is removed; 3 rows remain."""
        kb = build_catalog_keyboard(shown=47, total=47)
        assert len(kb.keyboard) == 3  # filters+bookmarks, viewing+manager, main_menu
        assert kb.keyboard[0][0].text == "🔍 Фильтры"

    def test_resize_keyboard_true(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.resize_keyboard is True


class TestNoDuplicateCatalogCode:
    def test_parse_catalog_button_defined_once(self):
        """parse_catalog_button must not be duplicated in the module."""
        import inspect

        import telegram_bot.keyboards.client_keyboard as mod

        source = inspect.getsource(mod)
        assert source.count("def parse_catalog_button") == 1

    def test_build_catalog_keyboard_defined_once(self):
        """build_catalog_keyboard must not be duplicated in the module."""
        import inspect

        import telegram_bot.keyboards.client_keyboard as mod

        source = inspect.getsource(mod)
        assert source.count("def build_catalog_keyboard") == 1
