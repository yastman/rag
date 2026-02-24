"""Tests for content_loader."""

from telegram_bot.services.content_loader import load_services_config


def test_load_services_config():
    config = load_services_config()
    assert "services" in config
    assert len(config["services"]) == 5


def test_each_service_has_required_fields():
    config = load_services_config()
    for key, svc in config["services"].items():
        assert "emoji" in svc, f"{key} missing emoji"
        assert "title" in svc, f"{key} missing title"
        assert "callback_id" in svc, f"{key} missing callback_id"
        assert "card_text" in svc, f"{key} missing card_text"


def test_welcome_text_exists():
    config = load_services_config()
    assert "welcome" in config
    assert "FortNoks" in config["welcome"]["text"]


def test_services_menu_text_exists():
    config = load_services_config()
    assert "services_menu_text" in config
