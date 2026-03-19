"""Settings dialog: language switch, CRM notifications (#697 Task 10)."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, Column, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from .root_nav import back_to_main_menu_button, get_main_menu_label, root_menu_button
from .states import SettingsSG


logger = logging.getLogger(__name__)

_SUPPORTED_LOCALES = [
    ("ru", "lang-ru"),
    ("en", "lang-en"),
    ("uk", "lang-uk"),
]

# CRM settings defaults and helpers

DEFAULT_CRM_SETTINGS: dict[str, Any] = {
    "notifications": True,
    "briefing_time": "09:00",
    "card_lang": "ru",
}

_BRIEFING_TIMES = ["06:00", "07:00", "08:00", "09:00", "10:00", "12:00", "выкл"]


def _crm_settings_key(tg_id: int) -> str:
    """Redis key for CRM settings of a user."""
    return f"user:{tg_id}:crm_settings"


async def get_crm_settings(redis: Any | None, tg_id: int) -> dict[str, Any]:
    """Get CRM settings from Redis. Returns defaults if redis is None or key absent."""
    if redis is None:
        return dict(DEFAULT_CRM_SETTINGS)
    try:
        raw = await redis.get(_crm_settings_key(tg_id))
        if raw is None:
            return dict(DEFAULT_CRM_SETTINGS)
        return json.loads(raw)  # type: ignore[no-any-return]
    except Exception:
        logger.warning("Failed to load CRM settings for user %d", tg_id, exc_info=True)
        return dict(DEFAULT_CRM_SETTINGS)


async def save_crm_settings(redis: Any, tg_id: int, settings: dict[str, Any]) -> None:
    """Save CRM settings to Redis as JSON (30-day TTL)."""
    try:
        await redis.set(_crm_settings_key(tg_id), json.dumps(settings), ex=86400 * 30)
    except Exception:
        logger.warning("Failed to save CRM settings for user %d", tg_id, exc_info=True)


# --- Main settings window getters/handlers ---


async def get_settings_data(i18n: Any = None, **kwargs: Any) -> dict[str, str]:
    """Getter for settings main window."""
    if i18n is None:
        return {
            "title": "Настройки",
            "btn_language": "Язык",
            "btn_crm": "🔔 CRM настройки",
            "btn_back": "Назад",
            "btn_main_menu": get_main_menu_label(),
        }
    return {
        "title": i18n.get("settings-title"),
        "btn_language": i18n.get("settings-language"),
        "btn_crm": "🔔 CRM настройки",
        "btn_back": i18n.get("back"),
        "btn_main_menu": get_main_menu_label(i18n),
    }


async def get_language_data(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for language selection window."""
    if i18n is None:
        return {
            "title": "Язык",
            "btn_back": "Назад",
            "btn_main_menu": get_main_menu_label(),
            "languages": _SUPPORTED_LOCALES,
        }

    languages = [(code, i18n.get(label_key)) for code, label_key in _SUPPORTED_LOCALES]
    return {
        "title": i18n.get("settings-language"),
        "btn_back": i18n.get("back"),
        "btn_main_menu": get_main_menu_label(i18n),
        "languages": languages,
    }


async def on_language_selected(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Handle language selection button click."""
    locale = button.widget_id  # widget_id = locale code (ru, en, uk)
    user_service = manager.middleware_data.get("user_service")
    if user_service is not None and callback.from_user:
        try:
            await user_service.set_locale(
                telegram_id=callback.from_user.id,
                locale=locale,
            )
        except Exception:
            logger.warning(
                "Failed to save locale for user %s", callback.from_user.id, exc_info=True
            )
    # Restart the settings root instead of closing the stack entirely.
    await manager.start(SettingsSG.main, mode=StartMode.RESET_STACK)


# --- CRM settings window getters/handlers ---


def _get_redis(manager: DialogManager) -> Any | None:
    """Extract Redis client from property_bot in middleware_data."""
    property_bot = manager.middleware_data.get("property_bot")
    if property_bot is None:
        return None
    cache = getattr(property_bot, "_cache", None)
    return getattr(cache, "redis", None) if cache is not None else None


async def get_crm_settings_data(
    property_bot: Any = None,
    event_from_user: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for CRM settings window."""
    redis = None
    if property_bot is not None:
        cache = getattr(property_bot, "_cache", None)
        redis = getattr(cache, "redis", None) if cache is not None else None

    tg_id = event_from_user.id if event_from_user else 0
    settings = await get_crm_settings(redis, tg_id)

    notif_icon = "✅" if settings["notifications"] else "🔕"
    notif_label = "Вкл" if settings["notifications"] else "Выкл"
    briefing = settings["briefing_time"]
    lang = settings["card_lang"].upper()

    return {
        "crm_title": "🔔 CRM настройки",
        "notifications": f"{notif_icon} Уведомления: {notif_label}",
        "briefing": f"⏰ Брифинг: {briefing}",
        "card_lang": f"🌐 Язык карточек: {lang}",
        "btn_back": "← Назад",
        "btn_main_menu": get_main_menu_label(kwargs.get("i18n")),
    }


async def on_toggle_notifications(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Toggle CRM notifications on/off."""
    if callback.from_user is None:
        return
    redis = _get_redis(manager)
    settings = await get_crm_settings(redis, callback.from_user.id)
    settings["notifications"] = not settings["notifications"]
    if redis is not None:
        await save_crm_settings(redis, callback.from_user.id, settings)
    await manager.update({})


async def on_cycle_briefing_time(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Cycle morning briefing time through available options."""
    if callback.from_user is None:
        return
    redis = _get_redis(manager)
    settings = await get_crm_settings(redis, callback.from_user.id)
    current = settings.get("briefing_time", "09:00")
    try:
        idx = _BRIEFING_TIMES.index(current)
    except ValueError:
        idx = -1
    settings["briefing_time"] = _BRIEFING_TIMES[(idx + 1) % len(_BRIEFING_TIMES)]
    if redis is not None:
        await save_crm_settings(redis, callback.from_user.id, settings)
    await manager.update({})


async def on_toggle_card_lang(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Toggle card language between ru and en."""
    if callback.from_user is None:
        return
    redis = _get_redis(manager)
    settings = await get_crm_settings(redis, callback.from_user.id)
    settings["card_lang"] = "en" if settings["card_lang"] == "ru" else "ru"
    if redis is not None:
        await save_crm_settings(redis, callback.from_user.id, settings)
    await manager.update({})


settings_dialog = Dialog(
    # Main settings window
    Window(
        Format("{title}"),
        Column(
            SwitchTo(
                Format("{btn_language}"),
                id="lang",
                state=SettingsSG.language,
            ),
            SwitchTo(
                Format("{btn_crm}"),
                id="crm_settings",
                state=SettingsSG.crm,
            ),
        ),
        root_menu_button(),
        back_to_main_menu_button(widget_id="settings_back"),
        getter=get_settings_data,
        state=SettingsSG.main,
    ),
    # Language selection window
    Window(
        Format("{title}"),
        Column(
            Button(Const("Русский"), id="ru", on_click=on_language_selected),
            Button(Const("English"), id="en", on_click=on_language_selected),
            Button(Const("Українська"), id="uk", on_click=on_language_selected),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="back_to_settings", state=SettingsSG.main),
        getter=get_language_data,
        state=SettingsSG.language,
    ),
    # CRM settings window
    Window(
        Format("{crm_title}\n\n{notifications}\n{briefing}\n{card_lang}"),
        Column(
            Button(
                Format("{notifications}"),
                id="crm_notif",
                on_click=on_toggle_notifications,
            ),
            Button(
                Format("{briefing}"),
                id="crm_briefing",
                on_click=on_cycle_briefing_time,
            ),
            Button(
                Format("{card_lang}"),
                id="crm_lang",
                on_click=on_toggle_card_lang,
            ),
        ),
        root_menu_button(),
        SwitchTo(Format("{btn_back}"), id="crm_back_to_settings", state=SettingsSG.main),
        getter=get_crm_settings_data,
        state=SettingsSG.crm,
    ),
)
