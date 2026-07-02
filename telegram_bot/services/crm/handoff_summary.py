"""Generate AI summary of chat history for manager handoff."""

from __future__ import annotations

import logging
from typing import Any

from src.runtime.llm import create_litellm_chat_client


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


async def generate_handoff_summary(
    history: list[dict[str, str]],
    *,
    llm: Any | None = None,
    model: str = "gpt-4o-mini",
    min_messages: int = 3,
) -> str | None:
    """Generate a concise summary of chat history for manager context."""
    if len(history) < min_messages:
        return None

    trimmed = history[-20:]
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *trimmed,
    ]
    try:
        if llm is None:
            llm = create_litellm_chat_client(model=model)
        resp = await llm.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=300,
            temperature=0.3,
            name="handoff-summary",  # type: ignore[call-overload]
        )
        content = resp.choices[0].message.content
        return content.strip() if content else None
    except Exception:
        logger.exception("Failed to generate handoff summary")
        return None
