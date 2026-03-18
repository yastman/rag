from __future__ import annotations

from typing import Any


STRICT_TOPICS = {"legal", "relocation", "immigration"}


def get_grounding_mode(*, query_type: str, topic_hint: str | None) -> str:
    _ = query_type
    return "strict" if topic_hint in STRICT_TOPICS else "normal"


def should_safe_fallback(
    *,
    grounding_mode: str,
    documents: list[dict[str, Any]],
    sources_enabled: bool,
) -> bool:
    if grounding_mode != "strict":
        return False
    return len(documents) == 0 or not sources_enabled


def build_safe_fallback_response(documents: list[dict[str, Any]]) -> str:
    if documents:
        return (
            "Не могу дать надежный ответ только на основе найденных материалов.\n\n"
            "Уточните вопрос или попросите менеджера проверить документы вручную."
        )
    return (
        "Не могу дать надежный ответ без подтвержденных материалов по этому вопросу.\n\n"
        "Уточните запрос или обратитесь к менеджеру за проверенной консультацией."
    )
