"""Contract-style prompt templates with explicit output constraints.

Based on best practices 2025-2026:
- Contract-style prompts > vague adjectives ("be concise" doesn't work)
- Dynamic token budgets based on style + difficulty (LASER-D pattern)

Issue: #129
"""

from __future__ import annotations

from telegram_bot.integrations.prompt_manager import get_prompt
from telegram_bot.services.response_style_detector import ResponseStyle


CONTRACT_PROMPTS: dict[ResponseStyle, str] = {
    "short": (
        "Ты — ассистент по {domain}.\n\n"
        "OUTPUT CONTRACT (NON-NEGOTIABLE):\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        '1. First line = direct answer (no preambles like "Based on context...")\n'
        "2. Maximum {word_limit} words total\n"
        "3. No disclaimers unless missing critical info\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "MICRO-RULES:\n"
        "- Lead with fact/number, not explanation\n"
        '- For prices: "X€ in City (size m²)" format\n'
        "- For lists: use bullets ONLY if >=3 items\n"
        '- No "Here are options..." hedging\n'
        '- No "I hope this helps" closers'
    ),
    "balanced": (
        "Ты — ассистент по {domain}.\n\n"
        "OUTPUT CONTRACT:\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "- Structured answer ({word_limit} words max)\n"
        "- 1-2 concrete examples with key parameters\n"
        "- Brief summary or recommendation\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "STYLE:\n"
        "- Start with direct answer, then context\n"
        "- Use tables for comparing 2+ items\n"
        "- Use bullets for lists"
    ),
    "detailed": (
        "Ты — ассистент по {domain}.\n\n"
        "DETAILED MODE ENABLED:\n"
        "- Comprehensive answer with analysis\n"
        "- Compare options if applicable\n"
        "- Use tables/structure for readability\n"
        "- Include pros/cons if requested"
    ),
}

# LASER-D inspired token budgets: (style, difficulty) -> max_tokens
TOKEN_LIMITS: dict[tuple[ResponseStyle, str], int] = {
    ("short", "easy"): 50,
    ("short", "medium"): 80,
    ("short", "hard"): 100,
    ("balanced", "easy"): 100,
    ("balanced", "medium"): 150,
    ("balanced", "hard"): 200,
    ("detailed", "easy"): 200,
    ("detailed", "medium"): 250,
    ("detailed", "hard"): 350,
}

_DEFAULT_TOKEN_LIMIT = 150


def get_token_limit(style: ResponseStyle, difficulty: str) -> int:
    """Get dynamic token budget based on style + difficulty."""
    return TOKEN_LIMITS.get((style, difficulty), _DEFAULT_TOKEN_LIMIT)


def get_word_limit(style: ResponseStyle, difficulty: str) -> int:
    """Approximate word limit from token budget (tokens / 1.3)."""
    return int(get_token_limit(style, difficulty) / 1.3)


def build_system_prompt(
    style: ResponseStyle,
    difficulty: str,
    domain: str,
) -> str:
    """Build contract-style system prompt with dynamic constraints."""
    template = CONTRACT_PROMPTS[style]
    word_limit = get_word_limit(style, difficulty)
    return template.format(domain=domain, word_limit=word_limit)


def build_system_prompt_with_manager(
    style: ResponseStyle,
    difficulty: str,
    domain: str,
) -> str:
    """Build system prompt via Langfuse prompt manager with contract fallback.

    Routes through get_prompt() to allow remote prompt overrides and A/B experiments.
    The fallback template has word_limit pre-rendered, domain passed as {{domain}}
    for Langfuse variable substitution.
    """
    word_limit = get_word_limit(style, difficulty)
    # Pre-render word_limit (dynamic), keep {{domain}} for Langfuse substitution
    fallback = CONTRACT_PROMPTS[style].replace("{word_limit}", str(word_limit))
    fallback = fallback.replace("{domain}", "{{domain}}")
    prompt_name = f"generate_{style}"
    return get_prompt(prompt_name, fallback=fallback, variables={"domain": domain})
