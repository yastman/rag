"""Telegram Forum Topics bridge for manager-client communication."""

from __future__ import annotations

import logging

from aiogram import Bot


logger = logging.getLogger(__name__)

# Telegram API: topic name 1-128 characters.
_MAX_TOPIC_NAME_LEN = 128


def _truncate_topic_name(name: str) -> str:
    if len(name) <= _MAX_TOPIC_NAME_LEN:
        return name
    return name[: _MAX_TOPIC_NAME_LEN - 1].rstrip() + "\u2026"


class ForumBridge:
    """Create forum topics and relay messages between client and manager."""

    def __init__(self, *, bot: Bot, managers_group_id: int) -> None:
        self._bot = bot
        self._group_id = managers_group_id

    async def create_topic(self, *, client_name: str, goal: str) -> int:
        raw_name = f"{client_name} — {goal}"
        name = _truncate_topic_name(raw_name)
        topic = await self._bot.create_forum_topic(chat_id=self._group_id, name=name)
        return topic.message_thread_id

    async def post_context_pack(
        self,
        *,
        topic_id: int,
        client_name: str,
        username: str | None,
        locale: str,
        qualification: dict[str, str],
        summary: str | None,
        lead_url: str | None,
    ) -> None:
        lines: list[str] = ["--- Новый клиент ---"]
        # Identity
        user_line = client_name
        if username:
            user_line += f" (@{username})"
        lines.append(user_line)
        lines.append(f"Язык: {locale}")
        # Qualification
        goal_map = {"buy": "Покупка", "rent": "Аренда", "consult": "Консультация"}
        goal = qualification.get("goal", "")
        lines.append(f"Цель: {goal_map.get(goal, goal)}")
        if budget := qualification.get("budget"):
            lines.append(f"Бюджет: {budget}")
        # AI summary
        if summary:
            lines.append("")
            lines.append(f"AI-саммари:\n{summary}")
        ***REMOVED*** link
        if lead_url:
            lines.append("")
            lines.append(f"Kommo: {lead_url}")
        lines.append("")
        lines.append("/close — вернуть клиента боту")
        lines.append("---")

        text = "\n".join(lines)
        await self._bot.send_message(
            chat_id=self._group_id,
            text=text,
            message_thread_id=topic_id,
        )

    async def relay_to_topic(self, *, from_chat_id: int, message_id: int, topic_id: int) -> None:
        await self._bot.copy_message(
            chat_id=self._group_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            message_thread_id=topic_id,
        )

    async def relay_to_client(self, *, topic_id: int, message_id: int, client_chat_id: int) -> None:
        await self._bot.copy_message(
            chat_id=client_chat_id,
            from_chat_id=self._group_id,
            message_id=message_id,
        )

    async def close_topic(self, *, topic_id: int) -> None:
        await self._bot.close_forum_topic(
            chat_id=self._group_id,
            message_thread_id=topic_id,
        )

    async def send_to_topic(self, *, topic_id: int, text: str) -> None:
        await self._bot.send_message(
            chat_id=self._group_id,
            text=text,
            message_thread_id=topic_id,
        )
