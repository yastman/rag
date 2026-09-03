"""Catalog dialog assembly — windows, input handlers, and the Dialog object."""

from __future__ import annotations

from aiogram.enums import ContentType
from aiogram.types import Message
from aiogram_dialog import Dialog, DialogManager, LaunchMode, ShowMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.text import Const

from telegram_bot.dialogs.catalog._handlers import dispatch_catalog_text_action
from telegram_bot.dialogs.catalog._runtime import _get_state
from telegram_bot.dialogs.catalog._search import search_catalog_from_query
from telegram_bot.dialogs.states import CatalogSG
from telegram_bot.services.voice_transcription import transcribe_voice


async def on_catalog_text_input(
    message: Message,
    _widget: MessageInput,
    manager: DialogManager,
) -> None:
    if not message.text:
        return
    i18n_hub = manager.middleware_data.get("i18n_hub")
    if i18n_hub is None:
        property_bot = manager.middleware_data.get("property_bot")
        if property_bot is not None:
            i18n_hub = getattr(property_bot, "_i18n_hub", None)
    if await dispatch_catalog_text_action(message=message, manager=manager, i18n_hub=i18n_hub):
        return

    manager.show_mode = ShowMode.NO_UPDATE
    state = await _get_state(manager)
    if state is None:
        return
    manager.middleware_data.setdefault("state", state)
    await search_catalog_from_query(message=message, dialog_manager=manager, query=message.text)


async def on_catalog_voice_input(
    message: Message,
    _widget: MessageInput,
    manager: DialogManager,
) -> None:
    manager.show_mode = ShowMode.NO_UPDATE
    state = await _get_state(manager)
    if state is None:
        return
    manager.middleware_data.setdefault("state", state)

    await message.answer("🎤 Распознаю голос...")
    text = await transcribe_voice(message, llm=manager.middleware_data.get("llm"))
    if not text:
        await message.answer("Не удалось распознать речь. Попробуйте ещё раз.")
        return
    await message.answer(f"📝 Распознано: {text}")
    await search_catalog_from_query(message=message, dialog_manager=manager, query=text)


_results_and_empty_widgets = [
    MessageInput(on_catalog_text_input, content_types=[ContentType.TEXT]),
    MessageInput(on_catalog_voice_input, content_types=[ContentType.VOICE]),
]

catalog_dialog = Dialog(
    Window(
        Const("Каталог активен."),
        *_results_and_empty_widgets,
        state=CatalogSG.results,
    ),
    Window(
        Const("Каталог активен."),
        *_results_and_empty_widgets,
        state=CatalogSG.empty,
    ),
    Window(
        Const("Детали объекта скоро будут доступны."),
        state=CatalogSG.details,
    ),
    launch_mode=LaunchMode.ROOT,
)


__all__ = [
    "catalog_dialog",
    "on_catalog_text_input",
    "on_catalog_voice_input",
]
