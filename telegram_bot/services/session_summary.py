"""Session summary generation for CRM integration.

Generates structured summaries from Q&A dialog turns using LLM.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel


logger = logging.getLogger(__name__)


class SessionSummary(BaseModel):
    """Structured summary of a bot-client dialog session.

    Used for CRM note generation (Kommo) and manager context.
    """

    brief: str
    """1-2 sentences summarizing the main topic and outcome."""

    client_needs: list[str]
    """What the client is looking for (extracted needs)."""

    budget: str | None = None
    """Budget if mentioned by client, None otherwise."""

    preferences: list[str]
    """Client preferences: location, floor, area, amenities, etc."""

    next_steps: list[str]
    """Agreed next actions or follow-ups."""

    sentiment: Literal["positive", "neutral", "negative"]
    """Overall conversation tone."""


_SUMMARY_SYSTEM_PROMPT = """\
Ты — ассистент риелторского агентства. Проанализируй диалог бота с клиентом \
и создай structured summary для карточки сделки в CRM.

Правила:
- brief: 1-2 предложения, главная тема и итог разговора
- client_needs: конкретные запросы клиента (тип жилья, количество комнат, расположение)
- budget: точная сумма если озвучена, иначе null
- preferences: детали предпочтений (район, этаж, площадь, особенности)
- next_steps: что договорились сделать дальше
- sentiment: общий тон разговора (positive/neutral/negative)

Извлекай только факты из диалога. Не додумывай."""

_MAX_TURNS_FOR_SUMMARY = 40
_MAX_DIALOG_CHARS = 12_000


def format_turns_for_prompt(turns: list[dict]) -> str:
    """Format Q&A turns as readable dialog for LLM prompt."""
    if not turns:
        return ""
    lines = []
    for turn in turns:
        lines.append(f"Клиент: {turn.get('query', '')}")
        lines.append(f"Бот: {turn.get('response', '')}")
    return "\n".join(lines)


def _trim_turns_for_summary(turns: list[dict]) -> list[dict]:
    """Drop empty turns and cap dialog size for stable LLM latency."""
    cleaned = [t for t in turns if t.get("query") or t.get("response")]
    return cleaned[-_MAX_TURNS_FOR_SUMMARY:]


async def generate_summary(
    *,
    turns: list[dict],
    llm: Any,
    model: str = "gpt-4o-mini",
) -> SessionSummary | None:
    """Generate structured session summary from Q&A turns.

    Args:
        turns: List of Q&A dicts with query, response, timestamp, input_type.
        llm: AsyncOpenAI-compatible client with responses.parse or
            beta.chat.completions.parse method.
        model: LLM model name for summary generation.

    Returns:
        SessionSummary on success, None on empty input or error.
    """
    trimmed_turns = _trim_turns_for_summary(turns)
    if not trimmed_turns:
        return None

    dialog = format_turns_for_prompt(trimmed_turns)
    if len(dialog) > _MAX_DIALOG_CHARS:
        dialog = dialog[-_MAX_DIALOG_CHARS:]
        newline_idx = dialog.find("\n")
        if newline_idx > 0:
            dialog = dialog[newline_idx + 1 :]

    try:
        if hasattr(llm, "responses") and hasattr(llm.responses, "parse"):
            response = await llm.responses.parse(  # type: ignore[attr-defined]
                model=model,
                input=[
                    {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Диалог:\n{dialog}"},
                ],
                text_format=SessionSummary,
                temperature=0.0,
            )
            return getattr(response, "output_parsed", None)

        # Fallback for wrappers that expose only Chat Completions parse
        completion = await llm.beta.chat.completions.parse(  # type: ignore[attr-defined]
            model=model,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Диалог:\n{dialog}"},
            ],
            response_format=SessionSummary,
            temperature=0.0,
        )
        return getattr(completion.choices[0].message, "parsed", None)
    except Exception:
        logger.warning("Failed to generate session summary", exc_info=True)
        return None


def format_summary_as_note(summary: SessionSummary) -> str:
    """Format SessionSummary as a readable CRM note text.

    Output is designed for Kommo lead notes (plain text with labeled sections).
    """
    lines = [f"AI Summary ({datetime.now(UTC).strftime('%Y-%m-%d')})", ""]
    lines.append(summary.brief)
    lines.append("")

    if summary.client_needs:
        lines.append("Потребности: " + ", ".join(summary.client_needs))
    if summary.budget:
        lines.append(f"Бюджет: {summary.budget}")
    if summary.preferences:
        lines.append("Предпочтения: " + ", ".join(summary.preferences))
    if summary.next_steps:
        lines.append("Следующие шаги: " + ", ".join(summary.next_steps))

    return "\n".join(lines)
