"""Tests for system prompt i18n and locale plumbing (#444)."""

from __future__ import annotations

from ._property_bot_ast import get_default_map, get_parameter_names, get_property_bot_method


def test_locale_to_language_mapping_covers_all_locales():
    """LOCALE_TO_LANGUAGE maps all supported locale codes."""
    from telegram_bot.pipeline.supervisor import LOCALE_TO_LANGUAGE

    assert "ru" in LOCALE_TO_LANGUAGE
    assert "en" in LOCALE_TO_LANGUAGE
    assert "uk" in LOCALE_TO_LANGUAGE
    assert LOCALE_TO_LANGUAGE["ru"] == "русском языке"
    assert LOCALE_TO_LANGUAGE["en"] == "English"
    assert LOCALE_TO_LANGUAGE["uk"] == "українською мовою"


def test_handle_query_accepts_locale_parameter():
    """handle_query signature accepts locale kwarg injected by i18n middleware."""
    method = get_property_bot_method("handle_query")
    assert "locale" in get_parameter_names(method)
    assert get_default_map(method)["locale"] == "ru"


def test_handle_query_supervisor_accepts_locale_parameter():
    """_handle_query_supervisor accepts locale kwarg."""
    method = get_property_bot_method("_handle_query_supervisor")
    assert "locale" in get_parameter_names(method)
    assert get_default_map(method)["locale"] == "ru"
