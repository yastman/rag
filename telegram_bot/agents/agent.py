"""Agent factory — creates the bot agent via create_agent SDK (#413).

Replaces build_supervisor_graph() from supervisor.py.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent

from telegram_bot.agents.context import BotContext


logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """Ты — AI-ассистент по недвижимости в Болгарии. Помогаешь клиентам и менеджерам.

ИНСТРУМЕНТЫ:
- rag_search — поиск по базе знаний (объекты, цены, районы)
- history_search — поиск в истории диалогов (deal_id для конкретной сделки)
- crm_get_deal — данные сделки из CRM
- crm_create_lead — создать новую сделку
- crm_update_lead — обновить сделку
- crm_upsert_contact — создать/обновить контакт
- crm_add_note — добавить заметку к сделке/контакту
- crm_create_task — создать задачу (follow-up, показ)
- crm_link_contact_to_deal — привязать контакт к сделке
- crm_get_contacts — поиск контактов

ПРАВИЛА:
1. Вопрос о прошлых разговорах → history_search
2. Упоминает сделку/deal → crm_get_deal, затем history_search если нужно
3. Просит создать сделку → crm_create_lead (+ crm_upsert_contact если есть данные)
4. Вопрос по недвижимости → rag_search
5. Приветствия, small talk → отвечай сам, без tools
6. Можно вызывать несколько tools для сложных запросов
7. Отвечай на {language}
"""


def create_bot_agent(
    *,
    model: str,
    tools: list[Any],
    checkpointer: Any | None = None,
    system_prompt: str | None = None,
) -> Any:
    """Create the bot agent using langchain create_agent SDK.

    Args:
        model: LLM model name (e.g. "openai/gpt-oss-120b").
        tools: List of @tool decorated functions.
        checkpointer: AsyncRedisSaver or None.
        system_prompt: Override default system prompt.

    Returns:
        Compiled agent graph ready for .ainvoke() / .astream().
    """
    prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
        context_schema=BotContext,
        checkpointer=checkpointer,
    )

    logger.info(
        "Created bot agent: model=%s, tools=%d, checkpointer=%s",
        model,
        len(tools),
        type(checkpointer).__name__ if checkpointer else "None",
    )

    return agent
