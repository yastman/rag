"""Tests for content_loader — structured services config (no locale parameter)."""

from telegram_bot.services.content_loader import get_service_card, load_services_config


def test_load_returns_dict():
    config = load_services_config()
    assert isinstance(config, dict)


def test_services_key_present():
    config = load_services_config()
    assert "services" in config


def test_services_has_known_keys():
    config = load_services_config()
    services = config.get("services", {})
    assert "passive_income" in services
    assert "installment" in services
    assert "infotour" in services


def test_service_card_has_required_fields():
    config = load_services_config()
    for key, svc in config.get("services", {}).items():
        assert "card_text" in svc, f"Service {key!r} missing card_text"
        assert "callback_id" in svc, f"Service {key!r} missing callback_id"


def test_get_service_card_returns_dict():
    card = get_service_card("installment")
    assert card is not None
    assert "card_text" in card


def test_get_service_card_unknown_returns_none():
    card = get_service_card("nonexistent_service_xyz")
    assert card is None


def test_load_is_cached():
    config1 = load_services_config()
    config2 = load_services_config()
    assert config1 is config2
