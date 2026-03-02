"""Generate AI summary of chat history for manager handoff."""

from __future__ import annotations

import logging

from langfuse.openai import AsyncOpenAI

from telegram_bot.observability import observe


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


@observe(name="handoff-generate-summary")
async def generate_handoff_summary(
    history: list[dict[str, str]],
    *,
    llm: AsyncOpenAI | None = None,
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
            import os

            llm = AsyncOpenAI(
                api_key=os.getenv("LLM_API_KEY", "sk-dev"),
                base_url=os.getenv("LLM_BASE_URL", "http://litellm:4000/v1"),
            )
        resp = await llm.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=300,
            temperature=0.3,
            name="handoff-summary",  # type: ignore[call-overload]
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.exception("Failed to generate handoff summary")
        return None
