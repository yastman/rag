"""Command handlers Router module.

Extracted from PropertyBot class methods into standalone functions registered
on an aiogram Router via the create_commands_router() factory.

Each handler accepts a ``bot`` instance as its first parameter. The factory
binds this via closures so that aiogram receives the correct signature.
Tests can import the raw handler functions and pass a mock bot directly.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


if TYPE_CHECKING:
    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handler functions (testable standalone — pass bot explicitly)
# ---------------------------------------------------------------------------


async def cmd_start(
    bot: PropertyBot,
    message: Message,
    command: CommandObject | None = None,
    dialog_manager: Any = None,
    i18n: Any = None,
) -> None:
    """Handle /start command with lower-menu client root and SDK dialogs for flows."""
    assert message.from_user is not None

    if dialog_manager is not None:
        with contextlib.suppress(Exception):
            await dialog_manager.reset_stack(remove_keyboard=True)
    from telegram_bot.dialogs.root_nav import show_client_main_menu

    await show_client_main_menu(message, i18n=i18n)


async def cmd_help(bot: PropertyBot, message: Message) -> None:
    """Handle /help command."""
    await message.answer(
        "\U0001f50d Примеры запросов:\n\n"
        "По цене:\n"
        "\u2022 Дешевле 80 000 евро\n"
        "\u2022 От 100к до 150к\n\n"
        "По комнатам:\n"
        "\u2022 2-комнатные квартиры\n"
        "\u2022 Трехкомнатная\n"
        "\u2022 Студия\n\n"
        "По городу:\n"
        "\u2022 В Несебр\n"
        "\u2022 Солнечный берег\n\n"
        "Комбинированные:\n"
        "\u2022 3 комнаты в Солнечный берег до 120к\n"
        "\u2022 Студия дешевле 60000\n\n"
        "Команды:\n"
        "/clear - Очистить историю диалога\n"
        "/stats - Показать статистику кеша\n"
        "/history <запрос> - Поиск по истории диалогов\n"
        "/metrics - Метрики пайплайна в JSON logs\n"
        "/clearcache - Очистить кеш Redis\n"
    )


async def cmd_clear(
    bot: PropertyBot,
    message: Message,
    state: FSMContext | None = None,
    dialog_manager: Any = None,
) -> None:
    """Handle /clear command - clear conversation history and exit any active dialog state.

    Closes any active aiogram-dialog stack (e.g. DemoSG apartment-search) and
    resets the FSM state so subsequent free-text questions are routed back to
    the supervisor / RAG path. See #1454.
    """
    from telegram_bot.services.checkpointer_utils import (
        _delete_checkpointer_thread,
        _supervisor_thread_id,
    )

    assert message.from_user is not None
    user_id = message.from_user.id
    # #1454: drop any active aiogram-dialog stack BEFORE clearing FSM
    dialog_reset_failed = False
    if dialog_manager is not None:
        try:
            if getattr(dialog_manager, "has_context", lambda: False)():
                await dialog_manager.reset_stack(remove_keyboard=False)
        except Exception:
            logger.warning(
                "Failed to reset aiogram-dialog stack during /clear for user_id=%s",
                user_id,
                exc_info=True,
            )
            dialog_reset_failed = True
    if state is not None:
        try:
            await state.clear()
        except Exception:
            logger.warning(
                "Failed to clear FSM state during /clear for user_id=%s",
                user_id,
                exc_info=True,
            )
            dialog_reset_failed = True
    checkpointer_cleared = True
    text_thread_id = _supervisor_thread_id(message.chat.id)
    seen_checkpointers: set[int] = set()
    for cp_name, checkpointer in (
        ("conversation", bot._checkpointer),
        ("agent", bot._agent_checkpointer),
    ):
        if checkpointer is None:
            continue
        cp_id = id(checkpointer)
        if cp_id in seen_checkpointers:
            continue
        seen_checkpointers.add(cp_id)
        for thread_id in (text_thread_id,):
            try:
                await _delete_checkpointer_thread(checkpointer, thread_id)
            except Exception:
                logger.warning(
                    "Failed to clear %s checkpointer thread %s",
                    cp_name,
                    thread_id,
                    exc_info=True,
                )
                checkpointer_cleared = False

    await bot._cache.clear_conversation(user_id)

    if checkpointer_cleared and not dialog_reset_failed:
        await message.answer("\u2705 История диалога очищена.")
    elif dialog_reset_failed and checkpointer_cleared:
        await message.answer(
            "\u26a0\ufe0f История очищена, но не удалось сбросить состояние активного диалога. "
            "Используйте /start, если бот продолжает отвечать в режиме поиска."
        )
    else:
        await message.answer(
            "\u26a0\ufe0f История очищена частично: локальный контекст сброшен, "
            "но долговременная память временно недоступна."
        )


async def cmd_stats(bot: PropertyBot, message: Message) -> None:
    """Handle /stats command - show cache statistics."""
    stats = bot._cache.get_metrics()
    lines = ["\U0001f4ca Статистика кеша:\n"]
    for tier, data in stats.items():
        hit_rate = data.get("hit_rate", 0)
        hits = data.get("hits", 0)
        misses = data.get("misses", 0)
        total = hits + misses
        lines.append(f"\u2022 {tier}: {hit_rate:.0f}% ({hits}/{total})")
    await message.answer("\n".join(lines))


async def cmd_metrics(bot: PropertyBot, message: Message) -> None:
    """Handle /metrics command — point operators to structured JSON logs."""
    _ = bot
    await message.answer(
        "Метрики пайплайна теперь пишутся в structured JSON logs: "
        "event=pipeline_latency и event=pipeline_counter. "
        "In-process Prometheus /metrics отключён."
    )


async def cmd_clearcache(bot: PropertyBot, message: Message) -> None:
    """Handle /clearcache command - show inline keyboard to select cache tier."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Semantic", callback_data="cc:semantic"),
                InlineKeyboardButton(text="Embeddings", callback_data="cc:embeddings"),
            ],
            [
                InlineKeyboardButton(text="Sparse", callback_data="cc:sparse"),
                InlineKeyboardButton(text="Search+Rerank", callback_data="cc:search"),
            ],
            [InlineKeyboardButton(text="Все кеши", callback_data="cc:all")],
            [InlineKeyboardButton(text="История диалога", callback_data="cc:history")],
            [InlineKeyboardButton(text="Всё (кеши + история)", callback_data="cc:all_and_history")],
        ]
    )
    await message.answer("Выберите тип кеша для очистки:", reply_markup=keyboard)


async def cmd_history(bot: PropertyBot, message: Message) -> None:
    """Handle /history command — removed (history service removed in #2843)."""
    await message.answer("История диалогов недоступна.")


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_commands_router(bot_instance: PropertyBot) -> Router:
    """Create Router with all command handlers bound to the bot instance.

    Parameters
    ----------
    bot_instance:
        The PropertyBot instance whose services are accessed by handlers.

    Returns
    -------
    Router
        Configured aiogram Router with command handlers registered.
    """
    router = Router(name="commands")

    # Wrap each handler to pre-fill the bot argument
    async def _cmd_start(
        message: Message,
        command: CommandObject | None = None,
        dialog_manager: Any = None,
        i18n: Any = None,
    ) -> None:
        await cmd_start(
            bot_instance, message, command=command, dialog_manager=dialog_manager, i18n=i18n
        )

    async def _cmd_help(message: Message) -> None:
        await cmd_help(bot_instance, message)

    async def _cmd_clear(
        message: Message,
        state: FSMContext | None = None,
        dialog_manager: Any = None,
    ) -> None:
        await cmd_clear(bot_instance, message, state=state, dialog_manager=dialog_manager)

    async def _cmd_stats(message: Message) -> None:
        await cmd_stats(bot_instance, message)

    async def _cmd_metrics(message: Message) -> None:
        await cmd_metrics(bot_instance, message)

    async def _cmd_history(message: Message) -> None:
        await cmd_history(bot_instance, message)

    async def _cmd_clearcache(message: Message) -> None:
        await cmd_clearcache(bot_instance, message)

    # Register on the router
    router.message(Command("start"))(_cmd_start)
    router.message(Command("help"))(_cmd_help)
    router.message(Command("clear"))(_cmd_clear)
    router.message(Command("stats"))(_cmd_stats)
    router.message(Command("metrics"))(_cmd_metrics)
    router.message(Command("history"))(_cmd_history)
    router.message(Command("clearcache"))(_cmd_clearcache)

    return router
