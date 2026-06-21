"""CRM / cache callback handlers extracted from ``telegram_bot/bot.py``.

Split #2980: extracted ``handle_clearcache_callback`` as a module-level
function so it can be tested without instantiating the full bot stack.

Module-level imports are stdlib and typing only; heavy dependencies
(aiogram, langgraph, qdrant_client, fastapi) are imported lazily inside
function bodies. This is pinned by the contract test
``tests/contract/test_bot_crm_callbacks_extraction_contract.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING


if TYPE_CHECKING:  # pragma: no cover
    from aiogram.types import CallbackQuery

    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)

_TIER_NAMES: dict[str, str] = {
    "semantic": "Semantic cache",
    "embeddings": "Embeddings cache",
    "sparse": "Sparse embeddings cache",
    "search": "Search + Rerank cache",
    "rerank": "Rerank cache",
    "all": "Все кеши",
    "history": "История диалога",
    "all_and_history": "Все кеши + История диалога",
}


async def handle_clearcache_callback(
    bot: PropertyBot,
    callback_query: CallbackQuery,
) -> None:
    """Handle /clearcache inline keyboard callbacks (cc: prefix)."""
    data = (callback_query.data or "").removeprefix("cc:")
    tier_name = _TIER_NAMES.get(data, data)
    text: str
    try:
        if data in ("history", "all_and_history"):
            from telegram_bot.services.checkpointer_utils import (
                _delete_checkpointer_thread,
                _supervisor_thread_id,
            )

            assert callback_query.from_user is not None
            user_id = callback_query.from_user.id
            chat_id = callback_query.message.chat.id if callback_query.message else user_id
            text_thread_id = _supervisor_thread_id(chat_id)
            seen: set[int] = set()
            for checkpointer in (bot._checkpointer, bot._agent_checkpointer):
                if checkpointer is None or id(checkpointer) in seen:
                    continue
                seen.add(id(checkpointer))
                for thread_id in (text_thread_id,):
                    try:
                        await _delete_checkpointer_thread(checkpointer, thread_id)
                    except Exception:
                        logger.warning(
                            "Failed to clear checkpointer thread %s", thread_id, exc_info=True
                        )
            if data == "history":
                text = "Очищено: История диалога"
            else:
                result = await bot._cache.clear_all_caches()
                lines = [
                    f"Очищено: {_TIER_NAMES.get(t, t)} — {n} ключей" for t, n in result.items()
                ]
                lines.append("Очищено: История диалога")
                text = "\n".join(lines)
        elif data == "all":
            result = await bot._cache.clear_all_caches()
            lines = [f"Очищено: {_TIER_NAMES.get(t, t)} — {n} ключей" for t, n in result.items()]
            text = "\n".join(lines)
        elif data == "semantic":
            deleted = await bot._cache.clear_semantic_cache()
            text = f"Очищено: {tier_name} — {deleted} ключей"
        else:
            deleted = await bot._cache.clear_by_tier(data)
            text = f"Очищено: {tier_name} — {deleted} ключей"
    except Exception:
        logger.warning("Failed to clear cache tier: %s", data, exc_info=True)
        text = "Ошибка очистки кеша"

    await callback_query.answer()
    if callback_query.message is not None:
        await callback_query.message.edit_text(text)  # type: ignore[union-attr]
