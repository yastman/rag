"""Tests for content_loader."""

from telegram_bot.services.content_loader import get_service_card, load_services_config


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


def test_load_services_config_file_not_found(monkeypatch, tmp_path):
    """FileNotFoundError when services.yaml is missing."""
    import telegram_bot.services.content_loader as mod

    # Clear lru_cache so the patched path is used
    mod.load_services_config.cache_clear()
    monkeypatch.setattr(mod, "_CONFIG_DIR", tmp_path / "nonexistent")

    import pytest

    with pytest.raises(FileNotFoundError):
        mod.load_services_config()

    # Restore cache for other tests
    mod.load_services_config.cache_clear()


def test_get_service_card_missing_key():
    assert get_service_card("nonexistent_key") is None
