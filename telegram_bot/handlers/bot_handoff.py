"""Handoff handlers extracted from ``telegram_bot/bot.py``.

Split #2816: extracted ``_handle_manager``, ``_handle_group_message``,
``_complete_handoff``, ``_close_handoff`` as module-level functions.

Raw FSM access is an intentional #1232 boundary exception: this module
maintains the single ``HandoffStates.active`` re-entry guard owned by
``handlers/handoff.py``, and manager-group ``/close`` messages must clear the
client's state by storage key because they have no client ``FSMContext``.

``PropertyBot`` retains thin wrappers so aiogram registration in
``_register_handlers`` and existing callers are unchanged.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

from aiogram.exceptions import TelegramBadRequest

from src.services.handoff_state import HandoffData
from telegram_bot.handlers.handoff import HandoffStates, start_qualification
from telegram_bot.services.util.business_hours import is_business_hours


if TYPE_CHECKING:  # pragma: no cover
    from aiogram.fsm.context import FSMContext
    from aiogram.types import Message

    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)

# Truthful failure copy (#3239): never promise manager contact after a failed
# bridge. The phone fallback it mentions is real — the durable request sink
# (#3213) is present wherever the forum handoff capability is on.
_HANDOFF_FAILURE_TEXT = (
    "⚠️ Не удалось передать ваш запрос менеджеру — обращение не было отправлено.\n\n"
    "Попробуйте позже или оставьте номер телефона, и мы перезвоним."
)

# Shown only when capability is off and the FSM context is unavailable, so the
# phone-request route cannot start either. No promises (#3239).
_MANAGER_UNAVAILABLE_TEXT = "⚠️ Связь с менеджером сейчас недоступна. Попробуйте позже."


async def _report_handoff_failure(message: Any) -> None:
    """Replace the qualification stub with explicit failure copy (#3239)."""
    if message is None:
        return
    edit_text = getattr(message, "edit_text", None)
    if edit_text is not None:
        try:
            await edit_text(_HANDOFF_FAILURE_TEXT)
            return
        except Exception:
            logger.warning("Failed to edit qualification message with failure copy")
    answer = getattr(message, "answer", None)
    if answer is not None:
        with contextlib.suppress(Exception):
            await answer(_HANDOFF_FAILURE_TEXT)


async def _handle_manager(
    bot: PropertyBot,
    message: Message,
    i18n: Any = None,
    state: FSMContext | None = None,
    dialog_manager: Any = None,
) -> None:
    """Handoff to manager (#628, #730).

    The qualification dialog (Forum Topics) is capability-gated (#3239):
    without ``HANDOFF_ENABLED`` + bridge + Redis state the manager button
    falls back to the durable phone-request sink (#3213), and — when even
    that is impossible — answers with truthful copy instead of dispatching
    "connect me to a manager" into the agent pipeline.
    """
    if bot.forum_handoff_available:
        await start_qualification(
            message,
            i18n=i18n,
            state=state,
            dialog_manager=dialog_manager,
        )
    elif state is not None:
        from telegram_bot.handlers.phone_collector import start_phone_collection

        await start_phone_collection(message, state, service_key="manager")
    else:
        logger.warning("Manager handoff unavailable: no capability and no FSM context")
        await message.answer(_MANAGER_UNAVAILABLE_TEXT)


async def _handle_group_message(bot: PropertyBot, message: Message) -> None:
    """Handle messages in managers group — relay to client (#730)."""
    if not message.message_thread_id:
        return
    if message.from_user and bot._bot_user_id and message.from_user.id == bot._bot_user_id:
        return  # Skip own messages (echo).

    if bot._handoff_state is None:
        return
    handoff = await bot._handoff_state.get_by_topic(message.message_thread_id)
    if not handoff:
        return

    # /close command — return client to bot.
    if message.text and message.text.strip().lower() == "/close":
        await _close_handoff(bot, handoff)
        return

    # First manager message — transition human_waiting → human.
    if handoff.mode == "human_waiting":
        await bot._handoff_state.update_mode(handoff.client_id, "human")
        manager_name = message.from_user.full_name if message.from_user else "Менеджер"
        await bot.bot.send_message(
            chat_id=handoff.client_id,
            text=f"🟢 {manager_name} подключился к чату",
        )

    # Relay manager message to client.
    if bot._forum_bridge is not None:
        try:
            await bot._forum_bridge.relay_to_client(
                topic_id=message.message_thread_id,
                message_id=message.message_id,
                client_chat_id=handoff.client_id,
            )
        except TelegramBadRequest:
            logger.warning("Failed to relay message to client %s", handoff.client_id)


async def _complete_handoff(
    bot: PropertyBot,
    user_id: int,
    username: str | None,
    display_name: str,
    locale: str,
    qualification: dict[str, str],
    message: Any,
    state: FSMContext | None = None,
) -> None:
    """Create forum topic and set handoff state (#730).

    Topic-creation failures are explicit (#3239): the user sees truthful
    failure copy — never a promise that a manager will make contact.
    """
    if bot._forum_bridge is None:
        # Capability gate bypassed — fail explicitly instead of leaving the
        # "connecting…" stub on screen (#3239).
        logger.warning("Handoff completion without Forum bridge — capability gate missed")
        await _report_handoff_failure(message)
        return

    # Stale topic cleanup: if Redis has data but topic is deleted — clean up.
    if bot._handoff_state is not None:
        existing = await bot._handoff_state.get_by_client(user_id)
        if existing is not None:
            try:
                topic_alive = await bot._forum_bridge.send_to_topic(
                    topic_id=existing.topic_id,
                    text="⚡ Клиент повторно запросил связь с менеджером.",
                )
            except Exception:
                # Cannot verify the old topic — report instead of guessing (#3239).
                logger.exception("Liveness check failed for handoff topic %s", existing.topic_id)
                await _report_handoff_failure(message)
                return
            if topic_alive:
                if state is not None:
                    await state.set_state(HandoffStates.active)
                return
            logger.info("Stale handoff topic %s — recreating", existing.topic_id)
            await bot._handoff_state.delete(user_id)

    goal_map = {"buy": "Покупка", "rent": "Аренда", "consult": "Консультация"}
    goal_text = goal_map.get(qualification.get("goal", ""), "Консультация")

    # 1. Create forum topic.
    try:
        topic_id = await bot._forum_bridge.create_topic(
            client_name=display_name,
            goal=goal_text,
        )
    except Exception:
        logger.exception("Forum topic creation failed — handoff not started")
        await _report_handoff_failure(message)
        return

    # 2. AI summary (if sufficient history).
    summary = None
    history: list[dict[str, str]] = []
    if bot._cache.redis is not None:
        try:
            raw = await bot._cache.redis.lrange(f"conversation:{user_id}", 0, -1)  # type: ignore[misc]
            for item in raw:
                entry = json.loads(item) if isinstance(item, str) else item
                if isinstance(entry, dict) and "role" in entry and "content" in entry:
                    history.append({"role": entry["role"], "content": entry["content"]})
        except Exception:
            logger.warning("Failed to fetch chat history for handoff summary")
    if len(history) >= bot.config.handoff_summary_min_messages:
        from telegram_bot.services.crm.handoff_summary import generate_handoff_summary

        summary = await generate_handoff_summary(history, llm=bot._llm)

    # 3. Post context pack.
    await bot._forum_bridge.post_context_pack(
        topic_id=topic_id,
        client_name=display_name,
        username=username,
        locale=locale,
        qualification=qualification,
        summary=summary,
        lead_url=None,
    )

    # 4. Set Redis state + FSM.
    data = HandoffData(
        client_id=user_id,
        topic_id=topic_id,
        lead_id=None,
        mode="human_waiting",
        qualification=qualification,
    )
    if bot._handoff_state is not None:
        await bot._handoff_state.set(data)
    if state is not None:
        await state.set_state(HandoffStates.active)

    # 6. Business hours notice.
    in_hours = is_business_hours(
        start=bot.config.business_hours_start,
        end=bot.config.business_hours_end,
        tz=bot.config.business_hours_tz,
    )
    if not in_hours:
        start_h = bot.config.business_hours_start
        end_h = bot.config.business_hours_end
        await message.answer(
            "📨 Ваш запрос принят!\n\n"
            "Менеджер ответит в рабочее время:\n"
            f"Пн–Пт, {start_h}:00–{end_h}:00 (🇧🇬 София)\n\n"
            "Мы пришлём уведомление, когда менеджер подключится."
        )


async def _close_handoff(bot: PropertyBot, handoff: HandoffData) -> None:
    """Manager sends /close — return client to bot (#730)."""
    # Notify topic.
    if bot._forum_bridge is not None:
        await bot._forum_bridge.send_to_topic(
            topic_id=handoff.topic_id,
            text="✅ Диалог закрыт, клиент возвращён боту.",
        )
        await bot._forum_bridge.close_topic(topic_id=handoff.topic_id)

    # Notify client.
    await bot.bot.send_message(
        chat_id=handoff.client_id,
        text="Диалог с менеджером завершён.\n\n🤖 Вы снова общаетесь с ботом. Задавайте вопросы — помогу!",
    )

    # Cleanup Redis + FSM state.
    if bot._handoff_state is not None:
        await bot._handoff_state.delete(handoff.client_id)
    # Clear client's FSM state from group context via storage key.
    from aiogram.fsm.storage.base import StorageKey

    key = StorageKey(bot_id=bot.bot.id, chat_id=handoff.client_id, user_id=handoff.client_id)
    await bot.dp.storage.set_state(key, state=None)
