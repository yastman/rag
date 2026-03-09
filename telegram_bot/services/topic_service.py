"""Forum topic mapping service — Redis-backed, one thread per expert per user."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from redis.asyncio import Redis


class TopicService:
    """Maps (user_id, expert_id) ↔ message_thread_id via Redis."""

    _PREFIX = "topics"

    def __init__(self, redis: Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis

    # ── Keys ────────────────────────────────────────────────────────

    def _key(self, user_id: int, expert_id: str) -> str:
        return f"{self._PREFIX}:{user_id}:{expert_id}"

    def _reverse_key(self, user_id: int, thread_id: int) -> str:
        return f"{self._PREFIX}:{user_id}:thread:{thread_id}"

    # ── Read ────────────────────────────────────────────────────────

    async def get_thread_id(self, user_id: int, expert_id: str) -> int | None:
        """Get message_thread_id for a user+expert pair, or None."""
        val = await self._redis.get(self._key(user_id, expert_id))
        return int(val) if val is not None else None

    async def get_expert_by_thread(self, user_id: int, thread_id: int) -> str | None:
        """Reverse lookup: thread_id → expert_id."""
        val = await self._redis.get(self._reverse_key(user_id, thread_id))
        return val.decode() if val is not None else None

    # ── Write ───────────────────────────────────────────────────────

    async def save_thread(self, user_id: int, expert_id: str, thread_id: int) -> None:
        """Store bidirectional mapping (persistent, no TTL)."""
        await self._redis.set(self._key(user_id, expert_id), str(thread_id))
        await self._redis.set(self._reverse_key(user_id, thread_id), expert_id)

    async def get_or_create_thread(
        self,
        bot: Any,
        chat_id: int,
        user_id: int,
        expert_id: str,
        topic_name: str,
    ) -> int:
        """Get existing thread or create new one via Telegram API."""
        existing = await self.get_thread_id(user_id, expert_id)
        if existing is not None:
            return existing

        forum_topic = await bot.create_forum_topic(chat_id=chat_id, name=topic_name)
        thread_id = forum_topic.message_thread_id
        await self.save_thread(user_id, expert_id, thread_id)
        return thread_id
