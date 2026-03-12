"""Forum topic manager for expert chats in private conversations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest


if TYPE_CHECKING:
    from aiogram import Bot
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_MAX_TOPIC_NAME_LEN = 128
_TOPIC_TTL = 30 * 86400  # 30 дней


def _truncate(name: str) -> str:
    if len(name) <= _MAX_TOPIC_NAME_LEN:
        return name
    return name[: _MAX_TOPIC_NAME_LEN - 1].rstrip() + "\u2026"


class TopicManager:
    """Manage forum topics per expert in private chats.

    Redis keys:
        topic:{chat_id}:{expert_id}          → message_thread_id
        topic_rev:{chat_id}:{message_thread_id} → expert_id
    """

    def __init__(self, *, bot: Bot, redis: Redis) -> None:
        self._bot = bot
        self._redis = redis

    def _fwd_key(self, chat_id: int, expert_id: str) -> str:
        return f"topic:{chat_id}:{expert_id}"

    def _rev_key(self, chat_id: int, topic_id: int) -> str:
        return f"topic_rev:{chat_id}:{topic_id}"

    async def _verify_topic(self, chat_id: int, topic_id: int, name: str) -> bool:
        """Check if cached topic still exists via edit_forum_topic probe."""
        try:
            await self._bot.edit_forum_topic(chat_id=chat_id, message_thread_id=topic_id, name=name)
            return True
        except TelegramBadRequest:
            logger.warning("Stale topic %d in chat %d — deleted by user", topic_id, chat_id)
            return False

    async def get_or_create_topic(
        self,
        chat_id: int,
        expert_id: str,
        expert_name: str,
        expert_emoji: str,
    ) -> int:
        """Return existing topic_id or create a new one."""
        fwd = self._fwd_key(chat_id, expert_id)
        name = _truncate(f"{expert_emoji} {expert_name}")

        cached = await self._redis.get(fwd)
        if cached is not None:
            tid = int(cached)
            if await self._verify_topic(chat_id, tid, name):
                return tid
            # Topic deleted — invalidate cache and fall through to create
            await self._redis.delete(fwd, self._rev_key(chat_id, tid))
            logger.info("Invalidated stale topic %d for expert=%s chat=%d", tid, expert_id, chat_id)

        topic = await self._bot.create_forum_topic(chat_id=chat_id, name=name)
        tid = topic.message_thread_id

        await self._redis.set(fwd, tid, ex=_TOPIC_TTL)
        await self._redis.set(self._rev_key(chat_id, tid), expert_id, ex=_TOPIC_TTL)
        logger.info("Created topic %d for expert=%s chat=%d", tid, expert_id, chat_id)
        return tid

    async def get_expert_for_topic(self, chat_id: int, topic_id: int) -> str | None:
        """Reverse lookup: topic_id → expert_id."""
        val = await self._redis.get(self._rev_key(chat_id, topic_id))
        return val if val is None else str(val)

    async def rename_topic(self, chat_id: int, topic_id: int, new_name: str) -> None:
        """Rename topic with truncation."""
        await self._bot.edit_forum_topic(
            chat_id=chat_id,
            message_thread_id=topic_id,
            name=_truncate(new_name),
        )

    async def invalidate_topic(self, chat_id: int, expert_id: str) -> None:
        """Remove topic mapping (e.g. when topic deleted by user)."""
        fwd = self._fwd_key(chat_id, expert_id)
        cached = await self._redis.get(fwd)
        if cached is not None:
            await self._redis.delete(fwd, self._rev_key(chat_id, int(cached)))
