"""Session summary generation for CRM integration.

Generates structured summaries from Q&A dialog turns using LLM.

Compatibility:
    - ``responses.parse`` (Responses API) requires langfuse >= 3.2.4 (fix:
      langfuse-python#1292, merged 2025-08-12) and openai >= 1.37.0.
    - Older versions expose the attribute but fail at runtime; the guard
      below detects this and forces the ``beta.chat.completions.parse``
      fallback automatically.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)

# Module-level flag: when True, skip responses.parse even if the attribute
# exists on the client.  Set by check_responses_parse_compat() at startup.
_force_chat_completions_fallback: bool = False
_compat_checked: bool = False


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


def check_responses_parse_compat(llm: Any) -> bool:
    """Probe whether *llm.responses.parse* is safe to call.

    Performs a lightweight attribute check **without** making a network call.
    If the Responses API is absent or the wrapper is known-incompatible
    (e.g. langfuse < 3.2.4 that exposes the attribute but raises at runtime),
    the module-level ``_force_chat_completions_fallback`` flag is set so all
    future calls skip the Responses path.

    Call once at application startup / preflight.

    Returns:
        True if responses.parse looks usable, False otherwise.
    """
    global _force_chat_completions_fallback, _compat_checked

    _compat_checked = True

    if not hasattr(llm, "responses") or not hasattr(llm.responses, "parse"):
        _force_chat_completions_fallback = True
        logger.info(
            "responses.parse not available on LLM client — "
            "using beta.chat.completions.parse fallback"
        )
        return False

    # Extra guard: some langfuse wrappers (< 3.2.4) expose the attribute but
    # the underlying object is not callable or raises TypeError on invocation.
    parse_attr = getattr(llm.responses, "parse", None)
    if not callable(parse_attr):
        _force_chat_completions_fallback = True
        logger.warning(
            "responses.parse exists but is not callable (langfuse < 3.2.4?) — "
            "forcing beta.chat.completions.parse fallback"
        )
        return False

    logger.debug("responses.parse compatibility check passed")
    return True


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


@observe(name="session-summary-generate", capture_input=False, capture_output=False)
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

    # Determine whether to attempt the Responses API path.
    # Skipped when: (a) preflight set the fallback flag, or (b) attribute missing.
    use_responses = (
        not _force_chat_completions_fallback
        and hasattr(llm, "responses")
        and hasattr(llm.responses, "parse")
    )

    if use_responses:
        try:
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
        except Exception:
            # Graceful degradation: responses.parse failed at runtime
            # (e.g. langfuse wrapper incompatibility).  Fall through to
            # beta.chat.completions.parse instead of returning None.
            logger.warning(
                "responses.parse raised at runtime — falling back to beta.chat.completions.parse",
                exc_info=True,
            )

    # Fallback: beta.chat.completions.parse (stable across all langfuse versions)
    try:
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
