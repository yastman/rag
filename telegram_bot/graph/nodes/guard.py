"""guard_node — prompt injection detection for the RAG pipeline.

Phase 1: Regex heuristics (~21 patterns, EN+RU) with configurable guard mode.
Phase 2: llm-guard ML classifier (opt-in, DeBERTa v3, ~100-200ms CPU).
Combined risk score: max(regex_score, ml_score).

Guard modes:
- "hard": block injection, set response, route to respond
- "soft": flag injection, log, continue to classify
- "log": log only, continue to classify
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


# --- Injection pattern categories ---
# Note: \b does NOT work with Cyrillic in Python regex.
# For Russian patterns, use (?<!\w) / (?!\w) or omit word boundaries.

_IGNORE_INSTRUCTIONS_PATTERNS = [
    # EN: ignore/disregard previous instructions
    r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|above|prior|all)\b.{0,30}\b(instructions?|rules?|prompt|context)\b",
    # RU: игнорируй предыдущие инструкции
    r"(игнорируй|забудь|отбрось).{0,30}(предыдущ|прошл|все|прежн).{0,30}(инструкц|правил|указан|промпт)",
]

_ROLE_OVERRIDE_PATTERNS = [
    # EN: you are now unrestricted / developer mode (exclude DAN — handled in dan_jailbreak)
    r"\byou are now\b.{0,30}\b(unrestricted|unfiltered|no rules?|jailbr[oe]ak|developer mode)\b",
    r"\b(enter|enable|activate|switch to)\b.{0,20}\b(developer mode|admin mode|god mode|DAN mode)\b",
    # RU: ты теперь без ограничений
    r"ты теперь.{0,30}(без ограничен|свободн|неограничен|разработчик)",
    # RU: включи режим разработчика
    r"(включи|активируй|перейди в).{0,20}(режим разработчик|режим админ|без цензур)",
]

_SYSTEM_PROMPT_LEAK_PATTERNS = [
    # EN: reveal/show system prompt
    r"\b(reveal|show|display|print|output|repeat|echo)\b.{0,30}\b(system prompt|hidden instructions?|initial prompt|secret instructions?)\b",
    r"\bwhat (is|are) your\b.{0,20}\b(system prompt|instructions?|rules?|guidelines)\b",
    # RU: покажи системный промпт
    r"(покажи|выведи|напиши|повтори).{0,30}(системн\w* промпт|скрыт\w* инструкц|начальн\w* промпт)",
    r"как\w* тво[ийя].{0,20}(системн\w* промпт|инструкц|правила)",
]

_POLICY_BYPASS_PATTERNS = [
    # EN: override/bypass system/policy/safety
    r"\b(override|bypass|circumvent|disable|turn off)\b.{0,20}\b(system|policy|safety|filter|guard|restriction|moderation)\b",
    # RU: обойди / отключи фильтр
    r"(обойди|отключи|выключи|обход).{0,20}(систем|политик|фильтр|защит|ограничен|модерац)",
]

_PERSONA_HIJACK_PATTERNS = [
    # EN: act as admin/root/developer
    r"\b(act|pretend|behave|respond)\b.{0,10}\bas\b.{0,20}\b(admin|root|developer|hacker|unrestricted|evil)\b",
    # RU: действуй как / притворись
    r"(действуй|притворись|веди себя|отвечай).{0,10}как.{0,20}(админ|разработчик|хакер|злодей)",
]

_ENCODING_EVASION_PATTERNS = [
    # Base64 / rot13 / hex encoded instructions
    r"\b(base64|rot13|hex|decode|encode)\b.{0,30}\b(instruction|payload|command)\b",
    # Token smuggling: unusual unicode or zero-width characters
    r"[\u200b\u200c\u200d\u2060\ufeff]{2,}",
]

_DAN_JAILBREAK_PATTERNS = [
    r"\bDAN\b",
    r"\bDo Anything Now\b",
    r"\bjailbreak\b",
    r"\bprompt leak\b",
]

# Combine all patterns with category tags
INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = []
for _category, _patterns in [
    ("ignore_instructions", _IGNORE_INSTRUCTIONS_PATTERNS),
    ("role_override", _ROLE_OVERRIDE_PATTERNS),
    ("system_prompt_leak", _SYSTEM_PROMPT_LEAK_PATTERNS),
    ("policy_bypass", _POLICY_BYPASS_PATTERNS),
    ("persona_hijack", _PERSONA_HIJACK_PATTERNS),
    ("encoding_evasion", _ENCODING_EVASION_PATTERNS),
    ("dan_jailbreak", _DAN_JAILBREAK_PATTERNS),
]:
    for _p in _patterns:
        INJECTION_PATTERNS.append((_category, re.compile(_p, re.IGNORECASE)))

# Risk scores by category (higher = more dangerous)
_CATEGORY_RISK: dict[str, float] = {
    "ignore_instructions": 0.9,
    "role_override": 0.95,
    "system_prompt_leak": 0.85,
    "policy_bypass": 0.9,
    "persona_hijack": 0.8,
    "encoding_evasion": 0.7,
    "dan_jailbreak": 0.95,
}

# Blocked response message
_BLOCKED_RESPONSE = (
    "Извините, ваш запрос не может быть обработан.\n\n"
    "Я помощник по недвижимости. Пожалуйста, задайте вопрос о квартирах, "
    "домах или другой недвижимости."
)

# Threshold above which regex is confident enough to skip ML layer
_REGEX_SKIP_ML_THRESHOLD = 0.9

# Threshold above which combined score counts as injection
_INJECTION_THRESHOLD = 0.5


def detect_injection(text: str) -> tuple[bool, float, str | None]:
    """Scan text for prompt injection patterns.

    Returns:
        (detected, risk_score, pattern_category)
        - detected: True if any injection pattern matched
        - risk_score: 0.0-1.0 risk score (max across matched categories)
        - pattern_category: name of highest-risk matched category, or None
    """
    max_risk = 0.0
    max_category: str | None = None

    for category, pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            risk = _CATEGORY_RISK.get(category, 0.5)
            if risk > max_risk:
                max_risk = risk
                max_category = category

    return (max_risk > 0, max_risk, max_category)


@observe(name="node-guard")
async def guard_node(
    state: dict[str, Any],
    *,
    guard_mode: str = "hard",
    guard_ml_enabled: bool = False,
    llm_guard_client: Any | None = None,
) -> dict[str, Any]:
    """LangGraph node: detect prompt injection attempts.

    Layer 1: Regex heuristics (<1ms, 21 patterns).
    Layer 2: llm-guard ML classifier (~100-200ms CPU, opt-in via guard_ml_enabled).
    Combined risk = max(regex_score, ml_score).

    Behavior depends on guard_mode:
    - "hard": sets response to blocked message, injection_detected=True
    - "soft": sets injection_detected=True, logs, continues to classify
    - "log": logs only, continues to classify
    """
    t0 = time.perf_counter()
    lf = get_client()

    messages = state["messages"]
    query = messages[-1].content if hasattr(messages[-1], "content") else messages[-1]["content"]

    # --- Layer 1: Regex ---
    _detected, risk_score, pattern = detect_injection(query)

    ml_score = 0.0
    ml_latency_ms = 0.0

    # --- Layer 2: ML classifier via HTTP (opt-in) ---
    if guard_ml_enabled and llm_guard_client is not None and risk_score < _REGEX_SKIP_ML_THRESHOLD:
        ml_t0 = time.perf_counter()
        try:
            scan_result = await llm_guard_client.scan_injection(query)
            ml_score = scan_result.risk_score
            ml_latency_ms = scan_result.processing_time_ms
            logger.info(
                "ML guard: detected=%s, score=%.3f, latency=%.1fms",
                scan_result.detected,
                ml_score,
                ml_latency_ms,
            )
        except Exception:
            ml_latency_ms = (time.perf_counter() - ml_t0) * 1000
            logger.exception("ML guard scanner failed (latency=%.1fms)", ml_latency_ms)

    # --- Combined score ---
    combined_score = max(risk_score, ml_score)
    combined_detected = combined_score >= _INJECTION_THRESHOLD
    # Update pattern if ML raised the score
    if ml_score > risk_score and ml_score >= _INJECTION_THRESHOLD:
        pattern = pattern or "ml_classifier"

    result: dict[str, Any] = {
        "guard_blocked": False,
        "guard_reason": None,
        "injection_detected": combined_detected,
        "injection_risk_score": combined_score,
        "injection_pattern": pattern,
        "guard_ml_score": ml_score,
        "guard_ml_latency_ms": ml_latency_ms,
        "latency_stages": {**state.get("latency_stages", {}), "guard": time.perf_counter() - t0},
    }

    if combined_detected:
        logger.warning(
            "Injection detected (mode=%s, score=%.2f, regex=%.2f, ml=%.2f, pattern=%s): %.80s",
            guard_mode,
            combined_score,
            risk_score,
            ml_score,
            pattern,
            query,
        )

        lf.update_current_span(
            output={
                "injection_detected": True,
                "risk_score": combined_score,
                "regex_score": risk_score,
                "ml_score": ml_score,
                "pattern": pattern,
                "guard_mode": guard_mode,
                "ml_latency_ms": ml_latency_ms,
            }
        )

        if guard_mode == "hard":
            result["guard_blocked"] = True
            result["guard_reason"] = "injection"
            result["response"] = _BLOCKED_RESPONSE
    else:
        lf.update_current_span(
            output={
                "injection_detected": False,
                "risk_score": 0.0,
                "ml_score": ml_score,
                "ml_latency_ms": ml_latency_ms,
            }
        )

    return result
