"""Tests for i18n middleware (fluentogram)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from telegram_bot.middlewares.i18n import (
    I18nMiddleware,
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
    keys = ["menu-search", "menu-settings", "menu-faq", "back", "close", "kb-demo"]
    for locale in ("ru", "en", "uk"):
        t = hub.get_translator_by_locale(locale)
        for key in keys:
            result = t.get(key)
            assert result, f"Missing key '{key}' in locale '{locale}'"


@pytest.mark.asyncio
async def test_i18n_middleware_injects_only_i18n(hub):
    """After H5 refactor: middleware injects only i18n + locale, not services."""
    middleware = I18nMiddleware(hub=hub)

    event = SimpleNamespace()
    data: dict = {"event_from_user": SimpleNamespace(id=123, language_code="ru")}

    async def handler(_event, _data):
        return _data

    result = await middleware(handler, event, data)
    assert "i18n" in result
    assert "locale" in result
    # Services are NOT injected by middleware; they come from dp.workflow_data
    assert "apartments_service" not in result
    assert "favorites_service" not in result
