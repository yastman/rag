"""Bridge between Mini App API and Telegram Bot for topic management."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from aiogram import Bot

    from telegram_bot.services.topic_service import TopicService

_bridge: BotBridge | None = None


@dataclass
class BotBridge:
    """Holds references to bot + topic service for Mini App API."""

    bot: Bot
    topic_service: TopicService
    rag_fn: Callable[..., Awaitable[dict[str, Any]]]

    async def ensure_topic(
        self,
        chat_id: int,
        user_id: int,
        expert_id: str,
        topic_name: str,
    ) -> int:
        """Get or create forum topic, return thread_id."""
        return await self.topic_service.get_or_create_thread(
            bot=self.bot,
            chat_id=chat_id,
            user_id=user_id,
            expert_id=expert_id,
            topic_name=topic_name,
        )

    async def send_to_topic(
        self,
        chat_id: int,
        thread_id: int,
        message: str,
        expert_id: str,
    ) -> None:
        """Send user message to topic and trigger RAG response."""
        result = await self.rag_fn(query=message)
        response = result.get("response", "")
        if response:
            await self.bot.send_message(
                chat_id=chat_id,
                text=response,
                message_thread_id=thread_id,
            )


def set_bot_bridge(bridge: BotBridge) -> None:
    global _bridge
    _bridge = bridge


def get_bot_bridge() -> BotBridge:
    if _bridge is None:
        raise RuntimeError("BotBridge not initialized — bot not started yet")
    return _bridge
