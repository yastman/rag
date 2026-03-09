# tests/unit/keyboards/test_client_keyboard.py
"""Tests for client ReplyKeyboard."""

from unittest.mock import MagicMock

from telegram_bot.keyboards.client_keyboard import (
    _ACTION_IDS,
    MENU_BUTTONS,
    build_client_keyboard,
    get_menu_button_texts,
    parse_menu_button,
)


# --- Fallback (no i18n) tests ---


def test_build_client_keyboard_returns_markup():
    from aiogram.types import ReplyKeyboardMarkup

    kb = build_client_keyboard()
    assert isinstance(kb, ReplyKeyboardMarkup)


def test_keyboard_has_4_rows():
    kb = build_client_keyboard()
    assert len(kb.keyboard) == 4


def test_keyboard_has_7_buttons():
    kb = build_client_keyboard()
    buttons = [btn for row in kb.keyboard for btn in row]
    assert len(buttons) == 7


def test_keyboard_is_persistent():
    kb = build_client_keyboard()
    assert kb.is_persistent is True
    assert kb.resize_keyboard is True


def test_build_no_i18n_uses_ru_fallback():
    from aiogram.types import ReplyKeyboardMarkup

    kb = build_client_keyboard()
    assert isinstance(kb, ReplyKeyboardMarkup)
    buttons = [btn.text for row in kb.keyboard for btn in row]
    assert any("Подобрать" in b for b in buttons)


def test_menu_buttons_has_7_entries():
    assert len(MENU_BUTTONS) == 7


def test_action_ids_has_7_entries():
    assert len(_ACTION_IDS) == 7


# --- i18n-aware tests ---


def _make_mock_i18n(translations: dict[str, str]) -> MagicMock:
    """Create a mock FluentTranslator that returns translations by key."""
    i18n = MagicMock()
    i18n.get.side_effect = lambda key, **_kw: translations.get(key, key)
    return i18n


def test_build_with_i18n():
    from aiogram.types import ReplyKeyboardMarkup

    i18n = _make_mock_i18n(
        {
            "kb-search": "🏠 Search",
            "kb-services": "🔑 Services",
            "kb-viewing": "📅 Viewing",
            "kb-manager": "👤 Manager",
            "kb-ask": "💬 Ask",
            "kb-bookmarks": "📌 Bookmarks",
            "kb-demo": "🎯 Demo",
        }
    )
    kb = build_client_keyboard(i18n=i18n)
    assert isinstance(kb, ReplyKeyboardMarkup)
    buttons = [btn.text for row in kb.keyboard for btn in row]
    assert len(buttons) == 7
    assert "🏠 Search" in buttons
    assert "🔑 Services" in buttons


def test_build_with_i18n_calls_all_keys():
    i18n = MagicMock()
    i18n.get.return_value = "test"
    build_client_keyboard(i18n=i18n)
    called_keys = [call.args[0] for call in i18n.get.call_args_list]
    for key in _ACTION_IDS:
        assert key in called_keys


# --- parse_menu_button tests ---


def test_parse_ru_button_fallback():
    assert parse_menu_button("🏠 Подобрать квартиру") == "search"
    assert parse_menu_button("🔑 Услуги") == "services"


def test_parse_menu_button_known():
    assert parse_menu_button("🏠 Подобрать квартиру") == "search"
    assert parse_menu_button("🔑 Услуги") == "services"
    assert parse_menu_button("📅 Запись на осмотр") == "viewing"
    assert parse_menu_button("👤 Связаться с менеджером") == "manager"
    assert parse_menu_button("💬 Задать вопрос") == "ask"
    assert parse_menu_button("📌 Мои закладки") == "bookmarks"


def test_parse_unknown_returns_none():
    assert parse_menu_button("totally unknown text xyz") is None


def test_parse_menu_button_unknown():
    assert parse_menu_button("random text") is None


def test_parse_with_i18n_hub():
    mock_hub = MagicMock()
    mock_translator = MagicMock()
    mock_translator.get.side_effect = lambda key: {
        "kb-search": "🏠 Підібрати квартиру",
        "kb-services": "🔑 Послуги",
        "kb-viewing": "📅 Запис на огляд",
        "kb-manager": "👤 Менеджер",
        "kb-ask": "💬 Задати питання",
        "kb-bookmarks": "📌 Мої закладки",
    }.get(key, key)
    mock_hub.get_translator_by_locale.return_value = mock_translator

    assert parse_menu_button("🏠 Підібрати квартиру", i18n_hub=mock_hub) == "search"
    assert parse_menu_button("🔑 Послуги", i18n_hub=mock_hub) == "services"


def test_parse_with_i18n_hub_fallback_to_menu_buttons():
    mock_hub = MagicMock()
    mock_translator = MagicMock()
    mock_translator.get.return_value = "something else"
    mock_hub.get_translator_by_locale.return_value = mock_translator

    # Russian text not in i18n translations but matches MENU_BUTTONS
    result = parse_menu_button("🏠 Подобрать квартиру", i18n_hub=mock_hub)
    assert result == "search"


def test_parse_with_i18n_hub_unknown():
    mock_hub = MagicMock()
    mock_translator = MagicMock()
    mock_translator.get.return_value = "unrelated"
    mock_hub.get_translator_by_locale.return_value = mock_translator

    assert parse_menu_button("totally unknown", i18n_hub=mock_hub) is None


def test_parse_menu_button_i18n_hub_raises_fallback():
    """When i18n_hub.get_translator_by_locale raises, fallback to MENU_BUTTONS."""
    mock_hub = MagicMock()
    mock_hub.get_translator_by_locale.side_effect = RuntimeError("hub broken")

    # Still resolves via MENU_BUTTONS fallback
    assert parse_menu_button("🏠 Подобрать квартиру", i18n_hub=mock_hub) == "search"
    # Unknown text still returns None
    assert parse_menu_button("random", i18n_hub=mock_hub) is None


def test_parse_menu_button_empty_returns_none():
    assert parse_menu_button("") is None


# --- MENU_BUTTONS key verification tests ---


def test_menu_buttons_manager_key_is_updated():
    """MENU_BUTTONS must use '👤 Связаться с менеджером', not old '👤 Менеджер'."""
    assert MENU_BUTTONS["👤 Связаться с менеджером"] == "manager"
    assert "👤 Менеджер" not in MENU_BUTTONS


def test_get_menu_button_texts_includes_localized_labels():
    mock_hub = MagicMock()

    def _translator_for(locale: str) -> MagicMock:
        translator = MagicMock()
        mapping = {
            "ru": {
                "kb-search": "🏠 Подобрать квартиру",
                "kb-services": "🔑 Услуги",
                "kb-viewing": "📅 Запись на осмотр",
                "kb-manager": "👤 Менеджер",
                "kb-ask": "💬 Задать вопрос",
                "kb-bookmarks": "📌 Мои закладки",
            },
            "uk": {
                "kb-search": "🏠 Підібрати квартиру",
                "kb-services": "🔑 Послуги",
                "kb-viewing": "📅 Запис на огляд",
                "kb-manager": "👤 Менеджер",
                "kb-ask": "💬 Задати питання",
                "kb-bookmarks": "📌 Мої закладки",
            },
            "en": {
                "kb-search": "🏠 Find Apartment",
                "kb-services": "🔑 Services",
                "kb-viewing": "📅 Book a Viewing",
                "kb-manager": "👤 Manager",
                "kb-ask": "💬 Ask a Question",
                "kb-bookmarks": "📌 My Bookmarks",
            },
        }[locale]
        translator.get.side_effect = lambda key, **_kw: mapping.get(key, key)
        return translator

    mock_hub.get_translator_by_locale.side_effect = _translator_for

    texts = get_menu_button_texts(i18n_hub=mock_hub)
    assert "🔑 Послуги" in texts
    assert "🏠 Find Apartment" in texts
    assert "🔑 Услуги" in texts
