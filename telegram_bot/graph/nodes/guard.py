"""guard_node — content filtering for the RAG pipeline.

Lightweight input validation using regex patterns and keyword blocklists.
Blocks toxic queries, prompt injection attempts, and prohibited topics
before they reach the retrieval pipeline.

Configurable via CONTENT_FILTER_ENABLED env var (default: true).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


# --- Toxicity patterns (RU + EN) ---

TOXICITY_PATTERNS = [
    # Threats / violence (RU)
    r"\b(убью|убить|зарежу|взорву|застрелю|расстреляю|сожгу)\b",
    r"\b(угрож|изнасил|покалеч|растерза)\w*\b",
    # Threats / violence (EN)
    r"\b(kill\s+you|murder|shoot|stab|bomb|blow\s+up)\b",
    r"\b(i('ll|\s+will)\s+(kill|murder|shoot|stab|burn))\b",
    # Hate speech / slurs (RU) — common patterns
    r"\b(нигер|хач|чурк|жид|пидор|хохл)\w*\b",
    # Hate speech (EN) — common patterns
    r"\b(nigger|kike|faggot|chink|spic|wetback)\w*\b",
    # Self-harm
    r"\b(суицид|повеш|покончить\s+с\s+собой|самоубийств)\w*\b",
    r"\b(suicide|self[- ]?harm|kill\s+myself)\b",
]

# --- Prompt injection patterns ---

INJECTION_PATTERNS = [
    # Direct instruction override
    r"(ignore|forget|disregard)\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|prompts?)",
    r"(игнорируй|забудь|отбрось)\s+(все\s+)?(предыдущие|прошлые)\s+(инструкции|правила|указания)",
    # System prompt extraction
    r"(show|print|reveal|output|display)\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?)",
    r"(покажи|выведи|раскрой)\s+(свой|свои)\s+(системный\s+)?(промпт|инструкции|правила)",
    # Role play jailbreak
    r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be|from\s+now\s+on\s+you)\b",
    r"(ты\s+теперь|притворись|веди\s+себя\s+как|отныне\s+ты)\b",
    # DAN / jailbreak patterns
    r"\bDAN\b.*\b(mode|jailbreak|bypass)\b",
    r"\b(jailbreak|bypass|override)\s+(mode|filter|safety)\b",
    # Delimiter injection
    r"(```|<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\])",
]

# --- Prohibited topic patterns ---

PROHIBITED_TOPIC_PATTERNS = [
    # Illegal activities
    r"\b(как\s+)?(купить|достать|найти)\s+(наркотик|оружие|взрывчатк|порох)\w*\b",
    r"\b(how\s+to\s+)?(buy|get|find|make)\s+(drugs?|weapons?|explosives?|bombs?)\b",
    # Fraud / scam
    r"\b(как\s+)?(обмануть|кинуть|развести|мошенничеств)\w*\b",
    r"\b(how\s+to\s+)?(scam|fraud|deceive|trick)\s+(people|someone|them)\b",
    # Hacking
    r"\b(взломать|хакнуть|брутфорс)\w*\b",
    r"\b(hack|crack|bruteforce)\s+(password|account|system)\b",
]


# Pre-compile all patterns
_TOXICITY_COMPILED = [re.compile(p, re.IGNORECASE) for p in TOXICITY_PATTERNS]
_INJECTION_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
_PROHIBITED_COMPILED = [re.compile(p, re.IGNORECASE) for p in PROHIBITED_TOPIC_PATTERNS]


# --- Blocked response messages ---

BLOCKED_RESPONSES = {
    "toxicity": (
        "Ваш запрос содержит недопустимый контент. "
        "Пожалуйста, переформулируйте вопрос в уважительной форме."
    ),
    "injection": (
        "Извините, я не могу обработать этот запрос. Пожалуйста, задайте вопрос о недвижимости."
    ),
    "prohibited_topic": (
        "Этот запрос выходит за рамки допустимых тем. "
        "Я могу помочь только с вопросами о недвижимости."
    ),
}


def _match_any(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def check_content(query: str) -> tuple[bool, str | None]:
    """Check query for prohibited content.

    Returns:
        Tuple of (blocked: bool, reason: str | None).
        If blocked is True, reason indicates the category.
    """
    text = query.strip()
    if not text:
        return False, None

    if _match_any(_TOXICITY_COMPILED, text):
        return True, "toxicity"

    if _match_any(_INJECTION_COMPILED, text):
        return True, "injection"

    if _match_any(_PROHIBITED_COMPILED, text):
        return True, "prohibited_topic"

    return False, None


@observe(name="node-guard")
async def guard_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: content filtering guard.

    Checks user query for toxicity, prompt injection, and prohibited topics.
    If content is blocked, sets guard_blocked=True and a canned response.

    Returns partial state update with guard_blocked, guard_reason,
    response (if blocked), and latency_stages["guard"].
    """
    t0 = time.perf_counter()

    messages = state["messages"]
    query = messages[-1].content if hasattr(messages[-1], "content") else messages[-1]["content"]

    blocked, reason = check_content(query)

    result: dict[str, Any] = {
        "guard_blocked": blocked,
        "guard_reason": reason,
        "latency_stages": {**state.get("latency_stages", {}), "guard": time.perf_counter() - t0},
    }

    if blocked and reason is not None:
        logger.warning("Content blocked (%s): %.80s", reason, query)
        result["response"] = BLOCKED_RESPONSES.get(reason, BLOCKED_RESPONSES["toxicity"])

    return result
