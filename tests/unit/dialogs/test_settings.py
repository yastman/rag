"""Tests for settings dialog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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


async def test_language_selected_restarts_settings_root():
    """Changing language should restart settings instead of closing the stack."""
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.settings import on_language_selected

    callback = MagicMock()
    callback.from_user.id = 42
    button = MagicMock(widget_id="en")
    manager = AsyncMock()
    manager.middleware_data = {"user_service": AsyncMock()}

    await on_language_selected(callback, button, manager)

    manager.middleware_data["user_service"].set_locale.assert_awaited_once_with(
        telegram_id=42,
        locale="en",
    )
    manager.start.assert_awaited_once_with(SettingsSG.main, mode=StartMode.RESET_STACK)
    manager.done.assert_not_called()


# --- get_settings_data ---


async def test_get_settings_data_without_i18n():
    """get_settings_data returns default Russian labels without i18n."""
    from telegram_bot.dialogs.settings import get_settings_data

    result = await get_settings_data()

    assert result["title"] == "Настройки"
    assert result["btn_language"] == "Язык"
    assert result["btn_crm"] == "🔔 CRM настройки"
    assert result["btn_back"] == "Назад"


async def test_get_settings_data_with_fake_i18n():
    """get_settings_data uses i18n when provided."""
    from telegram_bot.dialogs.settings import get_settings_data

    i18n = MagicMock()
    i18n.get = MagicMock(
        side_effect=lambda key: {
            "settings-title": "Settings",
            "settings-language": "Language",
            "back": "Back",
        }.get(key, key)
    )

    result = await get_settings_data(i18n=i18n)

    assert result["title"] == "Settings"
    assert result["btn_language"] == "Language"
    assert result["btn_back"] == "Back"


# --- _get_redis ---


def test_get_redis_returns_redis():
    """_get_redis returns redis when property_bot and cache exist."""
    from telegram_bot.dialogs.settings import _get_redis

    redis = MagicMock()
    cache = MagicMock()
    cache.redis = redis
    property_bot = MagicMock()
    property_bot._cache = cache

    manager = MagicMock()
    manager.middleware_data = {"property_bot": property_bot}

    assert _get_redis(manager) is redis


def test_get_redis_returns_none_without_property_bot():
    """_get_redis returns None when property_bot is absent."""
    from telegram_bot.dialogs.settings import _get_redis

    manager = MagicMock()
    manager.middleware_data = {}

    assert _get_redis(manager) is None


def test_get_redis_returns_none_without_cache():
    """_get_redis returns None when cache is absent."""
    from telegram_bot.dialogs.settings import _get_redis

    property_bot = MagicMock()
    property_bot._cache = None

    manager = MagicMock()
    manager.middleware_data = {"property_bot": property_bot}

    assert _get_redis(manager) is None


# --- get_crm_settings_data ---


async def test_get_crm_settings_data_with_mocked_redis():
    """get_crm_settings_data loads settings from mocked redis."""
    from telegram_bot.dialogs.settings import get_crm_settings_data

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    cache = MagicMock()
    cache.redis = redis
    property_bot = MagicMock()
    property_bot._cache = cache

    event_from_user = MagicMock()
    event_from_user.id = 42

    result = await get_crm_settings_data(property_bot=property_bot, event_from_user=event_from_user)

    assert result["crm_title"] == "🔔 CRM настройки"
    assert "Уведомления" in result["notifications"]
    assert "09:00" in result["briefing"]


# --- CRM toggle handlers ---


async def test_on_toggle_notifications():
    """on_toggle_notifications flips notifications setting."""
    from telegram_bot.dialogs.settings import on_toggle_notifications

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    cache = MagicMock()
    cache.redis = redis
    property_bot = MagicMock()
    property_bot._cache = cache

    manager = MagicMock()
    manager.middleware_data = {"property_bot": property_bot}
    manager.update = AsyncMock()

    callback = MagicMock()
    callback.from_user.id = 7

    await on_toggle_notifications(callback, MagicMock(), manager)

    redis.set.assert_called_once()
    manager.update.assert_awaited_once_with({})


async def test_on_cycle_briefing_time():
    """on_cycle_briefing_time cycles to next briefing time."""
    from telegram_bot.dialogs.settings import on_cycle_briefing_time

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    cache = MagicMock()
    cache.redis = redis
    property_bot = MagicMock()
    property_bot._cache = cache

    manager = MagicMock()
    manager.middleware_data = {"property_bot": property_bot}
    manager.update = AsyncMock()

    callback = MagicMock()
    callback.from_user.id = 7

    await on_cycle_briefing_time(callback, MagicMock(), manager)

    redis.set.assert_called_once()
    manager.update.assert_awaited_once_with({})
    # Default is 09:00, next should be 10:00
    call_args = redis.set.call_args
    stored = __import__("json").loads(call_args.args[1])
    assert stored["briefing_time"] == "10:00"


async def test_on_toggle_card_lang():
    """on_toggle_card_lang toggles between ru and en."""
    from telegram_bot.dialogs.settings import on_toggle_card_lang

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    cache = MagicMock()
    cache.redis = redis
    property_bot = MagicMock()
    property_bot._cache = cache

    manager = MagicMock()
    manager.middleware_data = {"property_bot": property_bot}
    manager.update = AsyncMock()

    callback = MagicMock()
    callback.from_user.id = 7

    await on_toggle_card_lang(callback, MagicMock(), manager)

    redis.set.assert_called_once()
    manager.update.assert_awaited_once_with({})
    call_args = redis.set.call_args
    stored = __import__("json").loads(call_args.args[1])
    assert stored["card_lang"] == "en"


# --- Callback without from_user ---


async def test_on_toggle_notifications_no_from_user_returns():
    """on_toggle_notifications returns early when callback.from_user is None."""
    from telegram_bot.dialogs.settings import on_toggle_notifications

    manager = MagicMock()
    manager.update = AsyncMock()

    callback = MagicMock()
    callback.from_user = None

    await on_toggle_notifications(callback, MagicMock(), manager)

    manager.update.assert_not_called()


async def test_on_cycle_briefing_time_no_from_user_returns():
    """on_cycle_briefing_time returns early when callback.from_user is None."""
    from telegram_bot.dialogs.settings import on_cycle_briefing_time

    manager = MagicMock()
    manager.update = AsyncMock()

    callback = MagicMock()
    callback.from_user = None

    await on_cycle_briefing_time(callback, MagicMock(), manager)

    manager.update.assert_not_called()


async def test_on_toggle_card_lang_no_from_user_returns():
    """on_toggle_card_lang returns early when callback.from_user is None."""
    from telegram_bot.dialogs.settings import on_toggle_card_lang

    manager = MagicMock()
    manager.update = AsyncMock()

    callback = MagicMock()
    callback.from_user = None

    await on_toggle_card_lang(callback, MagicMock(), manager)

    manager.update.assert_not_called()
