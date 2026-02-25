"""Tests for i18n-aware content_loader (locale parameter support)."""

from telegram_bot.services.content_loader import load_services_config


def test_load_ru():
    config = load_services_config(locale="ru")
    assert "welcome" in config


def test_load_uk():
    config = load_services_config(locale="uk")
    assert config is not None


def test_load_en():
    config = load_services_config(locale="en")
    assert config is not None


def test_fallback_to_ru():
    config = load_services_config(locale="fr")
    assert config is not None
    assert "welcome" in config


def test_welcome_text_differs_by_locale():
    ru = load_services_config(locale="ru")
    uk = load_services_config(locale="uk")
    en = load_services_config(locale="en")
    assert ru["welcome"]["text"] != uk["welcome"]["text"]
    assert ru["welcome"]["text"] != en["welcome"]["text"]


def test_menu_buttons_keys():
    config = load_services_config(locale="ru")
    assert "menu" in config
    assert "search" in config["menu"]
    assert "services" in config["menu"]


def test_funnel_keys():
    config = load_services_config(locale="ru")
    assert "funnel" in config
    assert "step_rooms" in config["funnel"]
    assert "step_budget" in config["funnel"]
