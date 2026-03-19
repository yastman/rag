"""Client main menu dialog (aiogram-dialog)."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, LaunchMode, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, Group, Start
from aiogram_dialog.widgets.text import Format

from telegram_bot.services.content_loader import load_services_config

from .states import ClientMenuSG, FunnelSG, ViewingSG


logger = logging.getLogger(__name__)

_DIRECT_ACTIONS = frozenset({"services", "ask", "bookmarks", "demo"})


def _message_for_actor(callback: CallbackQuery) -> Any:
    """Return a message object that reflects the clicking user as from_user."""
    message = callback.message
    actor = callback.from_user
    if message is None or actor is None:
        return message

    model_copy = getattr(message, "model_copy", None)
    if callable(model_copy):
        with contextlib.suppress(Exception):
            copied = model_copy(update={"from_user": actor})
            copied.from_user = actor
            return copied

    with contextlib.suppress(Exception):
        message.from_user = actor
    return message


async def get_menu_data(
    callback: Any = None,
    event_from_user: Any = None,
    i18n: Any = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Getter: provide localized menu text."""
    name = ""
    if event_from_user is not None:
        name = getattr(event_from_user, "first_name", "") or ""

    if i18n is None:
        welcome = load_services_config().get("welcome", {}).get("text", "Добро пожаловать!")
        if name:
            welcome = welcome.replace("Привет! 👋", f"Привет, {name}! 👋", 1)
        # Fallback if i18n not injected (e.g., tests)
        return {
            "title": welcome,
            "btn_search": "🏠 Подобрать квартиру",
            "btn_services": "🔑 Услуги",
            "btn_viewing": "📅 Запись на осмотр",
            "btn_manager": "👤 Связаться с менеджером",
            "btn_ask": "💬 Задать вопрос",
            "btn_bookmarks": "📌 Мои закладки",
            "btn_demo": "🎯 Демонстрация",
        }

    return {
        "title": i18n.get("welcome-text", name=name),
        "btn_search": i18n.get("kb-search"),
        "btn_services": i18n.get("kb-services"),
        "btn_viewing": i18n.get("kb-viewing"),
        "btn_manager": i18n.get("kb-manager"),
        "btn_ask": i18n.get("kb-ask"),
        "btn_bookmarks": i18n.get("kb-bookmarks"),
        "btn_demo": i18n.get("kb-demo"),
    }


async def on_menu_action(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Handle legacy root-menu actions while keeping SDK dialog ownership."""
    action_id = button.widget_id or ""
    bot_instance = manager.middleware_data.get("property_bot")
    state = manager.middleware_data.get("state")
    i18n = manager.middleware_data.get("i18n")
    actor_message = _message_for_actor(callback)
    if bot_instance is None or actor_message is None:
        return

    try:
        if action_id in _DIRECT_ACTIONS:
            await manager.done()
            if action_id == "services":
                await bot_instance._handle_services(actor_message, i18n=i18n)
            elif action_id == "ask":
                await bot_instance._handle_ask(actor_message, i18n=i18n)
            elif action_id == "bookmarks":
                await bot_instance._handle_bookmarks(actor_message, state)
            elif action_id == "demo":
                await bot_instance._handle_demo(actor_message)
            return

        if action_id == "manager":
            await bot_instance._handle_manager(
                actor_message,
                i18n=i18n,
                state=state,
                dialog_manager=manager,
            )
    except Exception:
        logger.exception("client_menu action failed for widget_id=%s", button.widget_id)


client_menu_dialog = Dialog(
    Window(
        Format("{title}"),
        Group(
            Start(
                Format("{btn_search}"),
                id="funnel",
                state=FunnelSG.city,
                mode=StartMode.RESET_STACK,
            ),
            Button(
                Format("{btn_services}"),
                id="services",
                on_click=on_menu_action,
            ),
            Start(
                Format("{btn_viewing}"),
                id="viewing",
                state=ViewingSG.date,
                mode=StartMode.RESET_STACK,
            ),
            Button(
                Format("{btn_manager}"),
                id="manager",
                on_click=on_menu_action,
            ),
            Button(
                Format("{btn_ask}"),
                id="ask",
                on_click=on_menu_action,
            ),
            Button(
                Format("{btn_bookmarks}"),
                id="bookmarks",
                on_click=on_menu_action,
            ),
            width=2,
        ),
        Button(
            Format("{btn_demo}"),
            id="demo",
            on_click=on_menu_action,
        ),
        getter=get_menu_data,
        state=ClientMenuSG.main,
    ),
    launch_mode=LaunchMode.ROOT,
)
