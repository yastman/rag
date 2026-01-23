# tests/load/chat_simulator.py
"""Realistic chat conversation simulator for load tests."""

import asyncio
import random
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Callable

from tests.smoke.queries import ExpectedQueryType


@dataclass
class Message:
    """Chat message."""

    query_type: ExpectedQueryType
    text: str


# Conversation template (6 messages per chat)
CONVERSATION_TEMPLATE = [
    Message(ExpectedQueryType.CHITCHAT, "Привет!"),
    Message(ExpectedQueryType.COMPLEX, "{property_query_1}"),
    Message(ExpectedQueryType.SIMPLE, "Сколько стоит?"),
    Message(ExpectedQueryType.COMPLEX, "{property_query_2}"),
    Message(ExpectedQueryType.SIMPLE, "Какая цена на студию?"),
    Message(ExpectedQueryType.CHITCHAT, "Спасибо, пока!"),
]

# Property queries for template substitution
PROPERTY_QUERIES = [
    "Найди квартиру в Солнечном берегу до 50000 евро",
    "Студии в Несебре с видом на море",
    "Апартаменты в Святом Власе с бассейном",
    "Двухкомнатные квартиры в Бургасе центр",
    "Новостройки в Поморие до 40000 евро",
    "Квартиры на первой линии в Равде",
    "Дома у моря в Созополе",
    "Апартаменты с паркингом в Солнечном берегу",
]


def generate_conversation() -> list[Message]:
    """Generate a realistic conversation sequence."""
    queries = random.sample(PROPERTY_QUERIES, 2)

    conversation = []
    for msg in CONVERSATION_TEMPLATE:
        text = msg.text
        if "{property_query_1}" in text:
            text = queries[0]
        elif "{property_query_2}" in text:
            text = queries[1]
        conversation.append(Message(msg.query_type, text))

    return conversation


@dataclass
class ChatResult:
    """Result of a single chat conversation."""

    chat_id: int
    messages_sent: int
    errors: int
    total_latency_ms: float


async def simulate_chat(
    chat_id: int,
    process_message: Callable[[str, int], Awaitable[float]],
    message_delay_range: tuple[float, float] = (2.0, 5.0),
) -> ChatResult:
    """Simulate a single chat conversation."""
    conversation = generate_conversation()
    total_latency = 0.0
    errors = 0

    for i, msg in enumerate(conversation):
        try:
            latency = await process_message(msg.text, chat_id)
            total_latency += latency
        except Exception:
            errors += 1

        if i < len(conversation) - 1:
            delay = random.uniform(*message_delay_range)
            await asyncio.sleep(delay)

    return ChatResult(
        chat_id=chat_id,
        messages_sent=len(conversation),
        errors=errors,
        total_latency_ms=total_latency,
    )


async def run_parallel_chats(
    chat_count: int,
    process_message: Callable[[str, int], Awaitable[float]],
    stagger_start_sec: float = 0.5,
) -> list[ChatResult]:
    """Run multiple chats in parallel with staggered start."""
    tasks = []

    for i in range(chat_count):
        task = asyncio.create_task(simulate_chat(i, process_message))
        tasks.append(task)

        if i < chat_count - 1:
            await asyncio.sleep(stagger_start_sec)

    return await asyncio.gather(*tasks)
