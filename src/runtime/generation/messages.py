"""LLM message assembly and history selection (#3015)."""

from __future__ import annotations

from typing import Any

from .policy import _HISTORY_INSTRUCTION, _MAX_HISTORY_MESSAGES


def _select_recent_history(
    messages: list[Any], max_messages: int = _MAX_HISTORY_MESSAGES
) -> list[Any]:
    """Return only recent conversation history messages for LLM context."""
    if not messages:
        return []
    return messages[-max_messages:]


def _ensure_history_instruction(system_prompt: str) -> str:
    """Ensure all prompt paths include history handling instruction."""
    lowered = system_prompt.lower()
    if (
        "ссылается на предыдущие" in lowered
        or "из контекста разговора" in lowered
        or _HISTORY_INSTRUCTION.lower() in lowered
    ):
        return system_prompt

    separator = "\n" if system_prompt.endswith("\n") else "\n\n"
    return f"{system_prompt}{separator}{_HISTORY_INSTRUCTION}"


def _build_llm_messages(
    *,
    system_prompt: str,
    raw_history: list[Any],
    effective_query: str,
    context: str,
    extra: dict[str, Any],
) -> list[dict[str, str]]:
    """Build the LLM messages list from system prompt, history, and current query."""
    select_recent_history = extra.get("select_recent_history") or _select_recent_history
    messages = select_recent_history(raw_history, _MAX_HISTORY_MESSAGES)

    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in messages[:-1]:
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role in ("user", "human"):
            llm_messages.append({"role": "user", "content": str(content)})
        elif role in ("assistant", "ai"):
            llm_messages.append({"role": "assistant", "content": str(content)})

    user_content = f"Контекст:\n{context}\n\nВопрос: {effective_query}\n\nОтветь на вопрос на основе контекста выше."
    llm_messages.append({"role": "user", "content": user_content})
    return llm_messages
