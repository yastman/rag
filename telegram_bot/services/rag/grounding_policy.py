from __future__ import annotations

from typing import Any


STRICT_TOPICS = {"legal", "relocation", "immigration"}
STRICT_QUERY_TYPES = {"LEGAL", "RELOCATION", "IMMIGRATION"}
STRICT_GROUNDING_CONFIDENCE_THRESHOLD = 0.5


def is_high_risk_grounding_request(*, query_type: str, topic_hint: str | None) -> bool:
    normalized_query_type = query_type.strip().upper()
    normalized_topic_hint = topic_hint.strip().lower() if isinstance(topic_hint, str) else None
    return normalized_query_type in STRICT_QUERY_TYPES or normalized_topic_hint in STRICT_TOPICS


def get_grounding_mode(*, query_type: str, topic_hint: str | None) -> str:
    return (
        "strict"
        if is_high_risk_grounding_request(query_type=query_type, topic_hint=topic_hint)
        else "normal"
    )


def is_strict_grounding_safe(
    *,
    documents: list[dict[str, Any]],
    sources_enabled: bool,
    grade_confidence: float | None = None,
) -> bool:
    if not documents or not sources_enabled:
        return False
    if grade_confidence is None:
        return True
    return grade_confidence >= STRICT_GROUNDING_CONFIDENCE_THRESHOLD


def semantic_cache_safe_reuse_allowed(
    *,
    grounding_mode: str,
    grounded: bool,
    legal_answer_safe: bool,
    semantic_cache_safe_reuse: bool,
    safe_fallback_used: bool,
) -> bool:
    if grounding_mode != "strict":
        return True
    return grounded and legal_answer_safe and semantic_cache_safe_reuse and not safe_fallback_used


def should_safe_fallback(
    *,
    grounding_mode: str,
    documents: list[dict[str, Any]],
    sources_enabled: bool,
    grade_confidence: float | None = None,
    legal_answer_safe: bool | None = None,
) -> bool:
    if grounding_mode != "strict":
        return False
    if legal_answer_safe is not None:
        return not legal_answer_safe
    return not is_strict_grounding_safe(
        documents=documents,
        sources_enabled=sources_enabled,
        grade_confidence=grade_confidence,
    )


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
