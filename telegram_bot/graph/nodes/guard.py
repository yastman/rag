"""guard_node — prompt injection detection for the RAG pipeline.

Phase 1: Regex heuristics (~21 patterns, EN+RU) with configurable guard mode.

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

from langgraph.runtime import Runtime

from telegram_bot.graph.context import GraphContext
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

# Threshold above which score counts as injection
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
    runtime: Runtime[GraphContext],
) -> dict[str, Any]:
    """LangGraph node: detect prompt injection attempts.

    Regex heuristics (<1ms, 21 patterns, EN+RU).

    Behavior depends on guard_mode:
    - "hard": sets response to blocked message, injection_detected=True
    - "soft": sets injection_detected=True, logs, continues to classify
    - "log": logs only, continues to classify
    """
    guard_mode: str = runtime.context.get("guard_mode", "hard")  # type: ignore[assignment]
    t0 = time.perf_counter()
    lf = get_client()

    messages = state["messages"]
    query = messages[-1].content if hasattr(messages[-1], "content") else messages[-1]["content"]

    # --- Regex detection ---
    _detected, risk_score, pattern = detect_injection(query)
    detected = risk_score >= _INJECTION_THRESHOLD

    result: dict[str, Any] = {
        "guard_blocked": False,
        "guard_reason": None,
        "injection_detected": detected,
        "injection_risk_score": risk_score,
        "injection_pattern": pattern,
        "latency_stages": {**state.get("latency_stages", {}), "guard": time.perf_counter() - t0},
    }

    if detected:
        logger.warning(
            "Injection detected (mode=%s, score=%.2f, pattern=%s): %.80s",
            guard_mode,
            risk_score,
            pattern,
            query,
        )

        lf.update_current_span(
            output={
                "injection_detected": True,
                "risk_score": risk_score,
                "pattern": pattern,
                "guard_mode": guard_mode,
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
            }
        )

    return result
