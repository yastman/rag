from __future__ import annotations

import re
from dataclasses import dataclass
from time import time
from typing import Any

from telegram_bot.services.grounding_policy import semantic_cache_safe_reuse_allowed
from telegram_bot.services.query_filter_signal import build_filter_signature


_SEMANTIC_CACHEABLE_QUERY_TYPES = {"ENTITY", "FAQ", "GENERAL", "STRUCTURED"}
SEMANTIC_CACHE_SCHEMA_VERSION = "v8"
_CONTEXTUAL_RE = re.compile(
    r"\b(?:"
    r"расскажи\s+подробнее(?:\s+(?:об|про)\s+(?:этом|этой|этих|этот|эту|них)\s+\w+)?"
    r"|покажи\s+подробнее(?:\s+(?:об|про)\s+(?:этом|этой|этих|этот|эту|них)\s+\w+)?"
    r"|объясни\s+подробнее(?:\s+(?:об|про)\s+(?:этом|этой|этих|этот|эту|них)\s+\w+)?"
    r"|подробнее\s+об\s+(?:этом|этих|них)\s+\w+"
    r"|подробнее\s+об\s+этой\s+\w+"
    r"|подробнее\s+про\s+(?:этот|эту|эти|них)\s+\w+"
    r"|перв(?:ый|ую|ое)\s+(?:вариант|объект)"
    r"|втор(?:ой|ую|ое)\s+(?:вариант|объект)"
    r"|трет(?:ий|ью|ье)\s+(?:вариант|объект)"
    r"|это\s+(?:правильн\w*|тот\s+же|та\s+же|то\s+же|вариант|объект)"
    r"|тот\s+же\s+(?:вариант|объект)"
    r"|та\s+же\s+(?:квартира|сделка|локация|планировка|цена)"
    r"|то\s+же(?:\s+самое)?"
    r"|они"
    r"|другие\s+есть"
    r"|друг(?:ой|ую)\s+(?:вариант|объект)"
    r"|ещ[её]\s+вариант\w*\s+есть"
    r"|следующ(?:ий|ую|ее)\s+(?:вариант|объект)"
    r"|предыдущ(?:ий|ую|ее)\s+(?:вариант|объект)"
    r")\b",
    re.IGNORECASE,
)


@dataclass(slots=True, frozen=True)
class SemanticCacheDecision:
    response_state: str
    degraded_reason: str | None
    cache_eligible: bool
    metadata: dict[str, Any]
    store_reason: str


def _normalize_query_type(query_type: str) -> str:
    return str(query_type or "").strip().upper()


def _classify_response_state(result: dict[str, Any]) -> tuple[str, str | None]:
    response_text = str(result.get("response", "") or "").strip()
    fallback_used = bool(result.get("fallback_used", False))
    safe_fallback_used = bool(result.get("safe_fallback_used", False))
    provider_model = str(result.get("llm_provider_model", "") or "")
    llm_timeout = bool(result.get("llm_timeout", False))

    if safe_fallback_used:
        return "safe_fallback", "safe_fallback"
    if fallback_used or provider_model == "fallback":
        return "fallback", "provider_fallback"
    if not response_text:
        return "error", "empty_response"
    if llm_timeout:
        return "degraded", "timeout"
    return "ok", None


def build_cacheability_decision(
    *,
    result: dict[str, Any],
    query_type: str,
    grounding_mode: str,
    documents: list[dict[str, Any]],
    cache_hit: bool,
    contextual: bool,
    grade_confidence: float,
    confidence_threshold: float,
    schema_version: str,
) -> SemanticCacheDecision:
    normalized_query_type = _normalize_query_type(query_type)
    response_state, degraded_reason = _classify_response_state(result)
    response_text = str(result.get("response", "") or "").strip()
    grounded = bool(result.get("grounded", False))
    legal_answer_safe = bool(result.get("legal_answer_safe", False))
    safe_reuse_flag = bool(result.get("semantic_cache_safe_reuse", False))
    meets_confidence_gate = grade_confidence >= confidence_threshold

    strict_safe_reuse = semantic_cache_safe_reuse_allowed(
        grounding_mode=grounding_mode,
        grounded=grounded,
        legal_answer_safe=legal_answer_safe,
        semantic_cache_safe_reuse=safe_reuse_flag,
        safe_fallback_used=bool(result.get("safe_fallback_used", False)),
    )

    cache_eligible = all(
        (
            response_state == "ok",
            bool(response_text),
            not cache_hit,
            not contextual,
            normalized_query_type in _SEMANTIC_CACHEABLE_QUERY_TYPES,
            bool(documents),
            meets_confidence_gate,
            strict_safe_reuse,
        )
    )

    metadata = {
        "cache_eligible": cache_eligible,
        "created_at": int(time()),
        "degraded_reason": degraded_reason,
        "grounding_mode": grounding_mode,
        "legal_answer_safe": legal_answer_safe,
        "provider_model": str(result.get("llm_provider_model", "") or ""),
        "query_type": normalized_query_type,
        "response_state": response_state,
        "schema_version": schema_version,
        "semantic_cache_safe_reuse": safe_reuse_flag,
    }
    store_reason = (
        "store_allowed" if cache_eligible else f"skip_{degraded_reason or response_state}"
    )

    return SemanticCacheDecision(
        response_state=response_state,
        degraded_reason=degraded_reason,
        cache_eligible=cache_eligible,
        metadata=metadata,
        store_reason=store_reason,
    )


def resolve_semantic_cache_signature(
    *,
    filters: dict[str, Any] | None,
    explicit_signature: str | None = None,
) -> str | None:
    if explicit_signature:
        return explicit_signature
    return build_filter_signature(filters)


def is_contextual_query(query: str) -> bool:
    """Return True for follow-up queries that depend on prior conversational context."""
    return bool(_CONTEXTUAL_RE.search(query))


async def maybe_store_semantic_response(
    *,
    cache: Any,
    query: str,
    response: str,
    vector: list[float],
    query_type: str,
    cache_scope: str,
    decision: SemanticCacheDecision,
    agent_role: str | None = None,
    filter_signature: str | None = None,
) -> bool:
    if cache_scope != "rag":
        return False
    if not str(response or "").strip():
        return False
    if not decision.cache_eligible:
        return False

    await cache.store_semantic(
        query=query,
        response=response,
        vector=vector,
        query_type=query_type,
        cache_scope=cache_scope,
        agent_role=agent_role,
        metadata=decision.metadata,
        filter_signature=filter_signature,
    )
    return True
