"""Generate AI summary of chat history for manager handoff."""

from __future__ import annotations

import logging

from langfuse.openai import AsyncOpenAI


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Ты — ассистент агентства недвижимости. Сгенерируй краткое саммари разговора \
для менеджера, который подключается к клиенту.

Формат (строго):
- Что искал клиент (тип, район, бюджет)
- Просмотренные объекты (если были)
- Неотвеченные вопросы
- Уровень готовности (холодный/тёплый/горячий)

Максимум 5 строк. Без приветствий. Только факты."""


async def _call_llm(messages: list[dict[str, str]]) -> str:
    import os

    client = AsyncOpenAI(
        api_key=os.getenv("LLM_API_KEY", "sk-dev"),
        base_url=os.getenv("LLM_BASE_URL", "http://litellm:4000/v1"),
    )
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,  # type: ignore[arg-type]
        max_tokens=300,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


async def generate_handoff_summary(
    history: list[dict[str, str]],
    min_messages: int = 3,
) -> str | None:
    if len(history) < min_messages:
        return None

    # Trim to last 20 messages to avoid token overflow.
    trimmed = history[-20:]
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *trimmed,
    ]
    try:
        return await _call_llm(messages)
    except Exception:
        logger.exception("Failed to generate handoff summary")
        return None
