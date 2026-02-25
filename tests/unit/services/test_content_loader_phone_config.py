"""Tests for get_phone_config and get_entry_point_config in content_loader."""

from telegram_bot.services.content_loader import get_entry_point_config, get_phone_config


def test_get_phone_config_returns_service() -> None:
    result = get_phone_config("passive_income")
    assert result is not None
    assert result["crm_title"] == "Пассивный доход"


def test_get_phone_config_returns_entry_point() -> None:
    result = get_phone_config("viewing")
    assert result is not None
    assert result["crm_title"] == "Осмотр объектов"


def test_get_phone_config_returns_entry_point_manager() -> None:
    result = get_phone_config("manager")
    assert result is not None
    assert result["crm_title"] == "Консультация"


def test_get_phone_config_returns_none_for_unknown() -> None:
    result = get_phone_config("nonexistent_key_xyz")
    assert result is None


def test_service_has_crm_fields() -> None:
    for key in ("passive_income", "online_deals", "vnzh", "installment", "infotour"):
        cfg = get_phone_config(key)
        assert cfg is not None, f"service {key} not found"
        assert "crm_title" in cfg, f"{key} missing crm_title"
        assert "phone_prompt" in cfg, f"{key} missing phone_prompt"
        assert "phone_success" in cfg, f"{key} missing phone_success"


def test_get_entry_point_config_viewing() -> None:
    cfg = get_entry_point_config("viewing")
    assert cfg is not None
    assert "phone_prompt" in cfg
    assert "phone_success" in cfg


def test_get_entry_point_config_unknown_returns_none() -> None:
    assert get_entry_point_config("unknown") is None
