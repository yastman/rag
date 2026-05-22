"""Command handlers Router module.

Extracted from PropertyBot class methods into standalone functions registered
on an aiogram Router via the create_commands_router() factory.

Each handler accepts a ``bot`` instance as its first parameter. The factory
binds this via closures so that aiogram receives the correct signature.
Tests can import the raw handler functions and pass a mock bot directly.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from telegram_bot.observability import get_client, observe, propagate_attributes
from telegram_bot.scoring import write_history_scores
from telegram_bot.tracing_context import make_session_id


if TYPE_CHECKING:
    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handler functions (testable standalone — pass bot explicitly)
# ---------------------------------------------------------------------------


@observe(name="cmd-start", capture_input=False, capture_output=False)
async def cmd_start_deeplink(
    bot: PropertyBot,
    message: Message,
    command: CommandObject,
) -> None:
    """Handle /start q_<uuid> - Mini App deep link flow."""
    assert message.from_user is not None
    assert command.args is not None
    uuid_str = command.args[2:]  # strip "q_" prefix
    await bot._handle_deeplink_start(message, uuid_str)


async def cmd_start(
    bot: PropertyBot,
    message: Message,
    command: CommandObject | None = None,
    dialog_manager: Any = None,
    i18n: Any = None,
) -> None:
    """Handle /start command with lower-menu client root and SDK dialogs for flows."""
    assert message.from_user is not None

    role = await bot._resolve_user_role(message.from_user.id)

    kommo_enabled = getattr(bot.config, "kommo_enabled", False)
    if role == "manager" and kommo_enabled and dialog_manager is not None:
        from aiogram_dialog import StartMode

        from telegram_bot.dialogs.states import ManagerMenuSG

        await dialog_manager.start(ManagerMenuSG.main, mode=StartMode.RESET_STACK)
    else:
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
        "/metrics - Метрики пайплайна (p50/p95)\n"
        "/clearcache - Очистить кеш Redis\n"
    )


@observe(name="cmd-clear", capture_input=False, capture_output=False)
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
    history_cleared = True
    text_thread_id = _supervisor_thread_id(message.chat.id)
    voice_thread_id = str(user_id)
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
        for thread_id in (text_thread_id, voice_thread_id):
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

    if bot._history_service is not None:
        try:
            history_cleared = bool(await bot._history_service.delete_user_history(user_id))
        except Exception:
            logger.warning("Failed to clear Qdrant history for user_id=%s", user_id, exc_info=True)
            history_cleared = False

    if checkpointer_cleared and history_cleared and not dialog_reset_failed:
        await message.answer("\u2705 История диалога очищена.")
    elif dialog_reset_failed and checkpointer_cleared and history_cleared:
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
    """Handle /metrics command — emit current Prometheus metrics text format.

    Slice 1/2 of #2058: replaces the deprecated `PipelineMetrics.format_text()`
    rolling-window dump with the SDK-native
    :func:`prometheus_client.generate_latest` output. Admin behaviour is
    preserved (Telegram message in a Markdown code block); the content is
    now the canonical Prometheus exposition format.
    """
    from prometheus_client import REGISTRY, generate_latest

    payload = generate_latest(REGISTRY).decode("utf-8")
    # Telegram's Markdown code-block has practical length limits; truncate
    # at 3500 chars (admin command, debugging only) so the message always
    # delivers even when the registry is large.
    if len(payload) > 3500:
        payload = payload[:3500] + "\n# ...truncated"
    text = f"```\n{payload}\n```"
    await message.answer(text, parse_mode="Markdown")


@observe(name="cmd-clearcache", capture_input=False, capture_output=False)
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
            [InlineKeyboardButton(text="Все", callback_data="cc:all")],
        ]
    )
    await message.answer("Выберите тип кеша для очистки:", reply_markup=keyboard)


@observe(name="cmd-call", capture_input=False, capture_output=False)
async def cmd_call(bot: PropertyBot, message: Message) -> None:
    """Handle /call command - trigger outbound voice call.

    Usage: /call +380501234567 [lead description]
    Admin-only command.
    """
    assert message.from_user is not None
    if not bot._is_admin(message.from_user.id):
        await message.answer("Только администраторы могут инициировать звонки.")
        return

    if not bot.config.livekit_url or not bot.config.sip_trunk_id:
        await message.answer("Voice service не настроен (LIVEKIT_URL, SIP_TRUNK_ID).")
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)  # /call +380... description
    if len(parts) < 2:
        await message.answer("Использование: /call +380501234567 [описание заявки]")
        return

    phone = parts[1]
    if not re.match(r"^\+?\d{10,15}$", phone):
        await message.answer("Неверный формат номера. Пример: +380501234567")
        return

    lead_desc = parts[2] if len(parts) > 2 else ""
    trace_id = ""
    try:
        trace_id = get_client().get_current_trace_id() or ""
    except Exception:
        logger.debug("Failed to resolve current Langfuse trace id for /call", exc_info=True)
    if not trace_id:
        trace_id = f"call-{uuid.uuid4().hex}"

    try:
        from livekit import api

        lk = api.LiveKitAPI(
            url=bot.config.livekit_url,
            api_key=bot.config.livekit_api_key,
            api_secret=bot.config.livekit_api_secret,
        )

        try:
            room_name = f"voice-call-{uuid.uuid4().hex[:8]}"
            call_id = str(uuid.uuid4())

            # 1. Dispatch voice agent to room
            await lk.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name="voice-bot",
                    room=room_name,
                    metadata=json.dumps(
                        {
                            "call_id": call_id,
                            "phone": phone,
                            "lead_data": {
                                "description": lead_desc,
                                "triggered_by": message.from_user.id,
                            },
                            "callback_chat_id": message.chat.id,
                            "langfuse_trace_id": trace_id,
                        }
                    ),
                )
            )

            # 2. Create SIP participant (dials the phone)
            await lk.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=room_name,
                    sip_trunk_id=bot.config.sip_trunk_id,
                    sip_call_to=phone,
                    participant_identity=f"phone-{phone}",
                    participant_name="Phone User",
                    krisp_enabled=True,
                    wait_until_answered=True,
                )
            )

            await message.answer(
                f"Звонок инициирован!\nID: `{call_id}`\nТелефон: {phone}\nRoom: {room_name}",
                parse_mode="Markdown",
            )
        finally:
            await lk.aclose()

    except Exception:
        logger.exception("Failed to initiate call to %s", phone)
        await message.answer("Ошибка инициации звонка. Попробуйте позже.")


@observe(name="telegram-history-search")
async def cmd_history(bot: PropertyBot, message: Message) -> None:
    """Handle /history command - semantic search in conversation history."""
    search_start = time.perf_counter()
    assert message.from_user is not None
    user_id = message.from_user.id
    session_id = make_session_id("history", message.chat.id)

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("Использование: /history <запрос>\nПример: /history цены на квартиры")
        return

    query = parts[1]

    with propagate_attributes(
        session_id=session_id,
        user_id=str(user_id),
        tags=["telegram", "history"],
    ):
        lf = get_client()
        tid = lf.get_current_trace_id() or ""

        if bot._history_service is None:
            lf.update_current_span(
                input={"command": "/history", "query": query},
                output={"error": "service_unavailable"},
                metadata={"user_id": user_id},
            )
            write_history_scores(lf, tid, count=0)
            await message.answer("История диалогов временно недоступна.")
            return

        try:
            results = await bot._history_service.search_user_history(
                user_id=user_id,
                query=query,
                limit=5,
            )
        except Exception:
            logger.exception("History search failed for user %s", user_id)
            lf.update_current_span(
                input={"command": "/history", "query": query},
                output={"error": "backend_exception"},
                metadata={"user_id": user_id},
            )
            write_history_scores(lf, tid, count=0)
            await message.answer("Произошла ошибка при поиске в истории. Попробуйте позже.")
            return

        search_ms = (time.perf_counter() - search_start) * 1000

        valid = []
        for r in results:
            if not isinstance(r, dict):
                continue
            q = r.get("query")
            resp = r.get("response")
            if not isinstance(q, str) or not isinstance(resp, str):
                continue
            valid.append(r)

        lf.update_current_span(
            input={"command": "/history", "query": query},
            output={"results_count": len(results), "valid_count": len(valid)},
            metadata={"user_id": user_id, "search_latency_ms": round(search_ms, 1)},
        )
        write_history_scores(
            lf,
            tid,
            count=len(valid),
            latency_ms=search_ms,
        )

        if not valid:
            await message.answer(f"По запросу \u00ab{query}\u00bb ничего не найдено в истории.")
            return

        lines = [f"\U0001f4cb Найдено {len(valid)} записей:\n"]
        for i, r in enumerate(valid, 1):
            ts = r.get("timestamp", "")
            ts = ts[:16].replace("T", " ") if isinstance(ts, str) else ""
            lines.append(f"{i}. [{ts}]")
            lines.append(f"   В: {r['query']}")
            resp_preview = r["response"][:150]
            if len(r["response"]) > 150:
                resp_preview += "..."
            lines.append(f"   О: {resp_preview}\n")

        await message.answer("\n".join(lines))


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
    async def _cmd_start_deeplink(message: Message, command: CommandObject) -> None:
        await cmd_start_deeplink(bot_instance, message, command)

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

    async def _cmd_call(message: Message) -> None:
        await cmd_call(bot_instance, message)

    async def _cmd_history(message: Message) -> None:
        await cmd_history(bot_instance, message)

    async def _cmd_clearcache(message: Message) -> None:
        await cmd_clearcache(bot_instance, message)

    # Register on the router
    router.message(CommandStart(deep_link=True, magic=F.args.startswith("q_")))(_cmd_start_deeplink)
    router.message(Command("start"))(_cmd_start)
    router.message(Command("help"))(_cmd_help)
    router.message(Command("clear"))(_cmd_clear)
    router.message(Command("stats"))(_cmd_stats)
    router.message(Command("metrics"))(_cmd_metrics)
    router.message(Command("call"))(_cmd_call)
    router.message(Command("history"))(_cmd_history)
    router.message(Command("clearcache"))(_cmd_clearcache)

    return router
