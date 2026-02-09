"""generate_node — LLM answer generation with conversation history.

Formats top-5 retrieved documents as context, builds system prompt with
domain from GraphConfig, includes conversation history, and calls LLM.
Falls back to a summary of retrieved docs if LLM is unavailable.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.graph.state import RAGState
from telegram_bot.integrations.prompt_manager import get_prompt
from telegram_bot.observability import observe


logger = logging.getLogger(__name__)

_MAX_CONTEXT_DOCS = 5


def _get_config() -> Any:
    """Get GraphConfig from environment."""
    from telegram_bot.graph.config import GraphConfig

    return GraphConfig.from_env()


_GENERATE_FALLBACK = (
    "Ты — ассистент по {{domain}}.\n\n"
    "Отвечай на вопросы пользователя на основе предоставленного контекста.\n"
    "Если информации недостаточно, честно скажи об этом.\n"
    "Всегда указывай цены в евро и расстояния в метрах.\n"
    "Будь вежливым и полезным.\n\n"
    "Форматируй ответ с Markdown: используй **жирный** для важного, • для списков."
)


def _build_system_prompt(domain: str) -> str:
    """Build system prompt with domain context."""
    return get_prompt("generate", fallback=_GENERATE_FALLBACK, variables={"domain": domain})


def _format_context(documents: list[dict[str, Any]], max_docs: int = _MAX_CONTEXT_DOCS) -> str:
    """Format top-N retrieved documents into LLM context string."""
    if not documents:
        return "Релевантной информации не найдено."

    parts: list[str] = []
    for i, doc in enumerate(documents[:max_docs], 1):
        text = doc.get("text", "")
        metadata = doc.get("metadata", {})
        score = doc.get("score", 0)

        meta_str = ""
        if "title" in metadata:
            meta_str += f"Название: {metadata['title']}\n"
        if "city" in metadata:
            meta_str += f"Город: {metadata['city']}\n"
        if "price" in metadata:
            meta_str += f"Цена: {metadata['price']:,}€\n"

        parts.append(f"[Объект {i}] (релевантность: {score:.2f})\n{meta_str}{text}")

    return "\n\n---\n\n".join(parts)


def _build_fallback_response(documents: list[dict[str, Any]]) -> str:
    """Build fallback response from retrieved documents when LLM fails."""
    if not documents:
        return "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."

    fallback = "⚠️ Сервис генерации ответов временно недоступен.\n\n"
    fallback += "Вот найденные объекты по вашему запросу:\n\n"

    for i, doc in enumerate(documents[:3], 1):
        meta = doc.get("metadata", {})
        fallback += f"{i}. "
        if "title" in meta:
            fallback += f"{meta['title']}\n"
        if "price" in meta:
            price = meta["price"]
            if isinstance(price, int | float):
                fallback += f"   Цена: {price:,}€\n"
            else:
                fallback += f"   Цена: {price}€\n"
        if "city" in meta:
            fallback += f"   Город: {meta['city']}\n"
        fallback += "\n"

    fallback += "Пожалуйста, попробуйте повторить запрос позже для получения детального ответа."
    return fallback


@observe(name="node-generate")
async def generate_node(state: RAGState) -> dict[str, Any]:
    """Generate an answer from retrieved documents using LLM.

    Builds a prompt with:
    - System prompt (domain from config)
    - Formatted context from top-5 documents
    - Conversation history from state messages

    Returns partial state update with response and latency.
    """
    t0 = time.monotonic()

    documents = state.get("documents", [])
    messages = state.get("messages", [])

    config = _get_config()
    context = _format_context(documents)
    system_prompt = _build_system_prompt(config.domain)

    # Build OpenAI-format messages
    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Add conversation history (all messages except the last user message)
    for msg in messages[:-1]:
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role in ("user", "human"):
            llm_messages.append({"role": "user", "content": str(content)})
        elif role in ("assistant", "ai"):
            llm_messages.append({"role": "assistant", "content": str(content)})

    # Add current query with context
    last_msg = messages[-1] if messages else None
    query = ""
    if last_msg:
        query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )

    user_content = (
        f"Контекст:\n{context}\n\nВопрос: {query}\n\nОтветь на вопрос на основе контекста выше."
    )
    llm_messages.append({"role": "user", "content": user_content})

    try:
        llm = config.create_llm()
        response = await llm.chat.completions.create(
            model=config.llm_model,
            messages=llm_messages,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens,
            name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
        )
        answer = response.choices[0].message.content or ""
    except Exception:
        logger.exception("generate_node: LLM call failed, using fallback")
        answer = _build_fallback_response(documents)

    elapsed = time.monotonic() - t0
    return {
        "response": answer,
        "latency_stages": {**state.get("latency_stages", {}), "generate": elapsed},
    }
