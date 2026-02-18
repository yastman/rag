"""Tests for i18n middleware (fluentogram)."""

from __future__ import annotations

from pathlib import Path

import pytest

from telegram_bot.middlewares.i18n import (
    create_translator_hub,
)


@pytest.fixture
def locales_dir():
    return Path(__file__).resolve().parents[3] / "telegram_bot" / "locales"


@pytest.fixture
def hub(locales_dir):
    return create_translator_hub(locales_dir=locales_dir)


def test_create_translator_hub(hub):
    """TranslatorHub created with 3 locales."""
    translator = hub.get_translator_by_locale("ru")
    assert translator is not None


def test_translator_ru(hub):
    """Russian translation works."""
    t = hub.get_translator_by_locale("ru")
    result = t.get("hello", name="Тест")
    assert "Тест" in result
    assert "бот-помощник" in result


def test_translator_en(hub):
    """English translation works."""
    t = hub.get_translator_by_locale("en")
    result = t.get("hello", name="Test")
    assert "Test" in result
    assert "real estate" in result


def test_translator_uk(hub):
    """Ukrainian translation works."""
    t = hub.get_translator_by_locale("uk")
    result = t.get("hello", name="Тест")
    assert "Тест" in result
    assert "бот-помічник" in result


def test_translator_menu_keys(hub):
    """All menu keys exist in all locales."""
    keys = ["menu-search", "menu-settings", "menu-faq", "back", "close"]
    for locale in ("ru", "en", "uk"):
        t = hub.get_translator_by_locale(locale)
        for key in keys:
            result = t.get(key)
            assert result, f"Missing key '{key}' in locale '{locale}'"
