"""Tests for Kommo CRM config fields (#389)."""

from telegram_bot.config import BotConfig


def test_kommo_config_fields_exist_and_defaults():
    cfg = BotConfig(telegram_token="x", llm_api_key="y")
    assert cfg.kommo_enabled is False
    assert cfg.kommo_rate_limit_rps == 7
    assert cfg.kommo_client_id == ""
    assert cfg.kommo_client_secret.get_secret_value() == ""


def test_kommo_secret_field_is_secretstr():
    cfg = BotConfig(telegram_token="x", llm_api_key="y", kommo_client_secret="super-secret")
    assert "super-secret" not in str(cfg.kommo_client_secret)


def test_kommo_oauth_fields_defaults():
    cfg = BotConfig(telegram_token="x", llm_api_key="y")
    assert cfg.kommo_redirect_uri == ""
    assert cfg.kommo_auth_code.get_secret_value() == ""
    assert cfg.kommo_default_pipeline_id == 0
    assert cfg.kommo_responsible_user_id is None
    assert cfg.kommo_session_field_id == 0
    assert cfg.kommo_max_retries == 3
