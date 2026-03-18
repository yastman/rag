"""Handoff qualification dialog (aiogram-dialog) — #730."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, ShowMode, Window
from aiogram_dialog.widgets.kbd import Back, Button, Group, Select
from aiogram_dialog.widgets.text import Format

from .states import HandoffSG


logger = logging.getLogger(__name__)

# ── Goal options ─────────────────────────────────────────────────

_GOAL_OPTIONS: list[tuple[str, str]] = [
    ("🏠 Подбор недвижимости", "search"),
    ("🔑 Услуги", "services"),
    ("💬 Консультация", "consult"),
    ("📎 Другое", "other"),
]


def _resolve_i18n_context(
    dialog_manager: DialogManager,
    kwargs: dict[str, Any],
) -> tuple[Any | None, str | None]:
    """Prefer the current getter context over potentially stale manager middleware data."""
    current_middleware = kwargs.get("middleware_data") or {}
    manager_middleware = getattr(dialog_manager, "middleware_data", None) or {}
    middleware = current_middleware or manager_middleware

    i18n = kwargs.get("i18n") or middleware.get("i18n")
    locale = kwargs.get("locale") or middleware.get("locale")
    return i18n, locale


# ── Getters ──────────────────────────────────────────────────────


async def _goal_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Provide goal options with i18n support."""
    i18n, _locale = _resolve_i18n_context(dialog_manager, kwargs)
    if i18n:
        items = [
            (i18n.get("handoff-goal-search"), "search"),
            (i18n.get("handoff-goal-services"), "services"),
            (i18n.get("handoff-goal-consult"), "consult"),
            (i18n.get("handoff-goal-other"), "other"),
        ]
        prompt = i18n.get("handoff-qual-prompt")
    else:
        items = list(_GOAL_OPTIONS)
        prompt = "📋 Какая тема вас интересует?"
    return {"goals": items, "prompt": prompt}


async def _contact_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Provide contact prompt with i18n support."""
    i18n, _locale = _resolve_i18n_context(dialog_manager, kwargs)
    if i18n:
        prompt = i18n.get("handoff-contact-prompt")
        btn_chat = i18n.get("handoff-contact-chat")
        btn_phone = i18n.get("handoff-contact-phone")
        btn_back = i18n.get("back") if i18n else "← Назад"
    else:
        prompt = "Какой способ связи предпочитаете?"
        btn_chat = "💬 Чат с менеджером"
        btn_phone = "📞 Перезвоните мне"
        btn_back = "← Назад"
    return {
        "prompt": prompt,
        "btn_chat": btn_chat,
        "btn_phone": btn_phone,
        "btn_back": btn_back,
    }


# ── Handlers ─────────────────────────────────────────────────────


async def _on_goal_selected(
    callback: CallbackQuery,
    _widget: Any,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save selected goal and advance to contact step."""
    manager.dialog_data["goal"] = item_id
    await manager.switch_to(HandoffSG.contact)


async def _on_contact_chat(
    callback: CallbackQuery,
    _button: Button,
    manager: DialogManager,
) -> None:
    """Complete qualification with chat — trigger handoff via PropertyBot."""
    start_data = manager.start_data if isinstance(manager.start_data, dict) else {}
    goal = manager.dialog_data.get("goal") or start_data.get("goal", "")
    qualification = {"goal": goal, "contact": "chat"}

    # Grab refs BEFORE done() destroys dialog context.
    property_bot = manager.middleware_data.get("property_bot")
    state = manager.middleware_data.get("state")
    msg = callback.message
    user_id = callback.from_user.id
    display_name = callback.from_user.full_name or "User"
    username = callback.from_user.username
    locale = manager.middleware_data.get("locale", "ru")
    i18n = manager.middleware_data.get("i18n")
    if i18n is None and property_bot is not None:
        hub = getattr(property_bot, "_i18n_hub", None)
        if hub is not None:
            with contextlib.suppress(Exception):
                i18n = hub.get_translator_by_locale(locale)

    # Tell aiogram-dialog NOT to touch the message after done().
    manager.show_mode = ShowMode.NO_UPDATE
    await manager.done()

    # Replace dialog message with status text (removes inline buttons).
    if msg and hasattr(msg, "edit_text"):
        with contextlib.suppress(Exception):
            connecting_text = (
                i18n.get("handoff-connecting")
                if i18n is not None
                else "💬 Соединяю с менеджером..."
            )
            await msg.edit_text(connecting_text)

    if property_bot is None:
        logger.warning("property_bot not in middleware_data, cannot complete handoff")
        return

    await property_bot._complete_handoff(
        user_id=user_id,
        username=username,
        display_name=display_name,
        locale=locale,
        qualification=qualification,
        message=msg,
        state=state,
    )


async def _on_contact_phone(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Complete qualification with phone — start phone collection."""
    # Grab refs BEFORE done() destroys dialog context.
    state = manager.middleware_data.get("state")
    msg = callback.message

    # Tell aiogram-dialog NOT to touch the message after done().
    manager.show_mode = ShowMode.NO_UPDATE
    await manager.done()

    # Remove inline keyboard message — phone_collector sends its own prompt.
    if msg and hasattr(msg, "delete"):
        with contextlib.suppress(Exception):
            await msg.delete()

    if state is None:
        logger.warning("FSMContext not in middleware_data for phone handoff")
        return

    from telegram_bot.handlers.phone_collector import start_phone_collection

    await start_phone_collection(callback, state, service_key="manager")


# ── Dialog ───────────────────────────────────────────────────────

handoff_dialog = Dialog(
    Window(
        Format("{prompt}"),
        Group(
            Select(
                Format("{item[0]}"),
                id="handoff_goal",
                item_id_getter=lambda item: item[1],
                items="goals",
                on_click=_on_goal_selected,
            ),
            width=2,
        ),
        state=HandoffSG.goal,
        getter=_goal_getter,
    ),
    Window(
        Format("{prompt}"),
        Button(
            Format("{btn_chat}"),
            id="handoff_contact_chat",
            on_click=_on_contact_chat,
        ),
        Button(
            Format("{btn_phone}"),
            id="handoff_contact_phone",
            on_click=_on_contact_phone,
        ),
        Back(Format("{btn_back}")),
        state=HandoffSG.contact,
        getter=_contact_getter,
    ),
)
