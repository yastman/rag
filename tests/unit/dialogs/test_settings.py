"""Tests for settings dialog."""

from __future__ import annotations

from unittest.mock import AsyncMock

from telegram_bot.dialogs.settings import settings_dialog
from telegram_bot.dialogs.states import SettingsSG


def test_settings_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(settings_dialog, Dialog)


def test_settings_has_main_and_language():
    windows = settings_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert SettingsSG.main in states
    assert SettingsSG.language in states


# --- CRM settings expansion (#697 Task 10) ---


def test_settings_has_crm_state():
    """SettingsSG has 'crm' state for CRM settings section."""
    assert hasattr(SettingsSG, "crm")


def test_settings_dialog_has_crm_window():
    """settings_dialog includes a window for SettingsSG.crm."""
    windows = settings_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert SettingsSG.crm in states


async def test_get_crm_settings_returns_defaults_when_redis_is_none():
    """get_crm_settings returns defaults when redis is None."""
    from telegram_bot.dialogs.settings import get_crm_settings

    settings = await get_crm_settings(None, tg_id=123)
    assert settings["notifications"] is True
    assert settings["briefing_time"] == "09:00"
    assert settings["card_lang"] == "ru"


async def test_get_crm_settings_returns_defaults_when_key_absent():
    """get_crm_settings returns defaults when Redis has no key for user."""
    from telegram_bot.dialogs.settings import get_crm_settings

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)

    settings = await get_crm_settings(redis, tg_id=999)
    assert settings["notifications"] is True
    assert settings["briefing_time"] == "09:00"
    assert settings["card_lang"] == "ru"


async def test_save_and_load_crm_settings_roundtrip():
    """save_crm_settings and get_crm_settings round-trip via mock Redis."""

    from telegram_bot.dialogs.settings import get_crm_settings, save_crm_settings

    stored: dict = {}

    async def mock_set(key: str, value: str, ex: int | None = None) -> None:
        stored[key] = value

    async def mock_get(key: str) -> str | None:
        return stored.get(key)

    redis = AsyncMock()
    redis.set = mock_set
    redis.get = mock_get

    new_settings = {"notifications": False, "briefing_time": "08:00", "card_lang": "en"}
    await save_crm_settings(redis, tg_id=456, settings=new_settings)

    loaded = await get_crm_settings(redis, tg_id=456)
    assert loaded["notifications"] is False
    assert loaded["briefing_time"] == "08:00"
    assert loaded["card_lang"] == "en"


async def test_save_crm_settings_stores_as_json():
    """save_crm_settings stores JSON in Redis with correct key format."""
    import json

    from telegram_bot.dialogs.settings import save_crm_settings

    redis = AsyncMock()
    redis.set = AsyncMock()

    settings = {"notifications": True, "briefing_time": "10:00", "card_lang": "ru"}
    await save_crm_settings(redis, tg_id=789, settings=settings)

    redis.set.assert_called_once()
    call_args = redis.set.call_args
    key = call_args.args[0]
    value = call_args.args[1]
    assert "789" in key
    assert json.loads(value) == settings


def test_crm_settings_key_contains_user_id():
    """CRM settings Redis key includes user tg_id."""
    from telegram_bot.dialogs.settings import _crm_settings_key

    key = _crm_settings_key(1234)
    assert "1234" in key
    assert key.startswith("user:")
