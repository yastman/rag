"""ResponseStyleDetector — scoring-based classifier for response length control.

Determines response style (short/balanced/detailed) and difficulty (easy/medium/hard)
using regex patterns and length heuristics. Zero LLM calls, ~0ms latency.

Issue: #129
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


ResponseStyle = Literal["short", "balanced", "detailed"]
Difficulty = Literal["easy", "medium", "hard"]


@dataclass
class StyleInfo:
    """Response style detection result."""

    style: ResponseStyle
    difficulty: Difficulty
    reasoning: str
    word_count: int


class ResponseStyleDetector:
    """Detect response style using C+ scoring heuristics."""

    def __init__(self) -> None:
        self._detailed_triggers = re.compile(
            r"(подробно|детально|пошагово|объясни|почему|развернуто|"
            r"все варианты|с примерами|сравни|плюсы и минусы|что лучше|"
            r"расскажи про|как работает|в чем разница)",
            re.IGNORECASE,
        )
        self._short_triggers = re.compile(
            r"(кратко|только ответ|без деталей|одним предложением|"
            r"да или нет|есть ли|сколько стоит|какая цена|минимальная|"
            r"максимальная|когда|где находится|адрес|часы работы)",
            re.IGNORECASE,
        )
        self._transactional_patterns = [
            re.compile(r"сколько.*стои", re.IGNORECASE),
            re.compile(r"какая.*цена", re.IGNORECASE),
            re.compile(r"(минимальн|максимальн).*рассрочк", re.IGNORECASE),
            re.compile(r"какие виды", re.IGNORECASE),
            re.compile(r"есть.*наличии", re.IGNORECASE),
            re.compile(r"до.*евро", re.IGNORECASE),
        ]

    def detect(self, query: str) -> StyleInfo:
        """Detect response style from query text.

        Priority:
        1. Explicit detailed triggers -> "detailed"
        2. Explicit short triggers -> "short"
        3. Transactional domain intents -> "short"
        4. Length heuristics (fallback)
        """
        query_lower = query.lower()
        words = query.split()
        word_count = len(words)

        # 1. Explicit detailed triggers (highest priority)
        if self._detailed_triggers.search(query_lower):
            return StyleInfo(
                style="detailed",
                difficulty=self._detect_difficulty(query_lower, word_count),
                reasoning="explicit_detailed_trigger",
                word_count=word_count,
            )

        # 2. Explicit short triggers
        if self._short_triggers.search(query_lower):
            return StyleInfo(
                style="short",
                difficulty="easy",
                reasoning="explicit_short_trigger",
                word_count=word_count,
            )

        # 3. Transactional domain intents
        if any(p.search(query_lower) for p in self._transactional_patterns):
            return StyleInfo(
                style="short",
                difficulty="easy",
                reasoning="transactional_intent",
                word_count=word_count,
            )

        # 4. Length heuristics (fallback)
        if word_count <= 8:
            style: ResponseStyle = "short"
            reasoning = "short_query"
        elif word_count <= 20:
            style = "balanced"
            reasoning = "medium_query"
        else:
            style = "detailed"
            reasoning = "long_query"

        return StyleInfo(
            style=style,
            difficulty=self._detect_difficulty(query_lower, word_count),
            reasoning=reasoning,
            word_count=word_count,
        )

    def _detect_difficulty(self, query_lower: str, word_count: int) -> Difficulty:
        """Detect query difficulty for token budget allocation."""
        if any(kw in query_lower for kw in ("сравни", "что лучше", "плюсы и минусы")):
            return "hard"
        if word_count <= 5:
            return "easy"
        return "medium"
