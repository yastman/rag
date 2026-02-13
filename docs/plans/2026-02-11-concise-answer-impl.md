# Concise Answer UX — TDD Implementation Plan

> **For Codex/Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce verbose answers for short queries by adding adaptive response length control (contract-style prompts + dynamic token budgets) to the generate_node.

**Architecture:** A pure-Python `ResponseStyleDetector` classifies queries as short/balanced/detailed with difficulty level. The `generate_node` uses this to select a contract-style prompt and a dynamic `max_tokens` budget (LASER-inspired dynamic budgeting). Four new Langfuse scores track effectiveness.

**Tech Stack:** Python 3.12, LangGraph, Langfuse SDK v3, pytest

**Issue:** [#129](https://github.com/yastman/rag/issues/129)

---

## Plan Audit Delta (2026-02-11)

This plan was reviewed against issue [#129](https://github.com/yastman/rag/issues/129), current repository state, and official docs (OpenAI + Langfuse). Apply the following mandatory adjustments while executing tasks below:

1. Keep Langfuse Prompt Management in the loop. Do not bypass `telegram_bot/integrations/prompt_manager.py`; contract templates should remain fallback text, while prompt names are loaded via `get_prompt(...)`.
2. Add rollout safety flags in `GraphConfig`: `RESPONSE_STYLE_ENABLED` and `RESPONSE_STYLE_SHADOW_MODE` (default `false`), so production can collect metrics before enforcing concise policy.
3. Cap dynamic token budgets by env config: `effective_max_tokens = min(style_budget, config.generate_max_tokens)`. Never exceed existing global `GENERATE_MAX_TOKENS`.
4. Update tests beyond `test_bot_handlers.py`. `tests/unit/test_bot_scores.py` has strict score name/count assertions and must be updated explicitly.
5. Align acceptance criteria with issue #129 outcomes (ratio targets + no quality/latency regression), not only unit-test pass.
6. Keep LASER-D reference as inspiration only (arXiv preprint/repo). Do not state accepted ICLR result as a fact without verification.
7. Use short-mode token budgets as safety margin (soft cap), while strict brevity is enforced by prompt contract ("at most X words").
8. Keep broad-query clarifying behavior (`is_broad` + one follow-up question) as post-MVP Phase 2, not a blocker for Phase 1 rollout.

Reference links used for these adjustments:
- OpenAI, "Controlling the length of OpenAI model responses" (updated 2026-01-13): https://help.openai.com/en/articles/5072518-controlling-the-length-of-openai-model-responses
- OpenAI, "Best practices for prompt engineering with the OpenAI API" (updated 2025-11): https://help.openai.com/en/articles/6654000-best-practices-for-prompt-engineering-with-openai-api
- Langfuse FAQ, trace/observation updates and score enrichment (2025-09): https://langfuse.com/faq/all/tracing-data-updates
- LASER / LASER-D repository + paper (preprint evidence): https://github.com/MorningStarTM/LASER and https://arxiv.org/abs/2505.22722

---

## Task 1: ResponseStyleDetector service

**Files:**
- Create: `telegram_bot/services/response_style_detector.py`
- Create: `tests/unit/services/test_response_style_detector.py`

**Step 1: Write failing tests**

Create `tests/unit/services/test_response_style_detector.py`:

```python
"""Tests for ResponseStyleDetector — C+ scoring classifier."""

from __future__ import annotations

import pytest

from telegram_bot.services.response_style_detector import ResponseStyleDetector, StyleInfo


class TestExplicitTriggers:
    """Explicit keywords override length heuristics."""

    def test_short_trigger_skolko_stoit(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("сколько стоит студия")
        assert result.style == "short"
        assert result.reasoning == "explicit_short_trigger"

    def test_short_trigger_kakaya_tsena(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("какая цена на квартиру в Несебре")
        assert result.style == "short"
        assert result.reasoning == "explicit_short_trigger"

    def test_detailed_trigger_sravni(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("сравни цены Несебр vs Равда")
        assert result.style == "detailed"
        assert result.reasoning == "explicit_detailed_trigger"

    def test_detailed_trigger_podrobno(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("расскажи подробно про рассрочку")
        assert result.style == "detailed"
        assert result.reasoning == "explicit_detailed_trigger"

    def test_detailed_overrides_short_query_length(self) -> None:
        """Even a 3-word query triggers detailed if keyword present."""
        detector = ResponseStyleDetector()
        result = detector.detect("сравни два варианта")
        assert result.style == "detailed"


class TestTransactionalIntents:
    """Domain-specific transactional patterns → short."""

    def test_price_range_query(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("квартира до 50000 евро с мебелью")
        assert result.style == "short"
        assert result.reasoning == "transactional_intent"

    def test_minimalnaya_rassrochka(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("минимальная рассрочка на покупку квартиры")
        assert result.style == "short"
        assert result.reasoning == "explicit_short_trigger"


class TestLengthHeuristics:
    """Fallback when no triggers match."""

    def test_short_query_fallback(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("привет как дела")
        assert result.style == "short"
        assert result.reasoning == "short_query"

    def test_medium_query_fallback(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect(
            "мне нужна информация о процессе покупки недвижимости иностранцем"
        )
        assert result.style == "balanced"
        assert result.reasoning == "medium_query"

    def test_long_query_fallback(self) -> None:
        detector = ResponseStyleDetector()
        words = " ".join(["слово"] * 25)
        result = detector.detect(words)
        assert result.style == "detailed"
        assert result.reasoning == "long_query"


class TestDifficultyDetection:
    """Difficulty affects token budget."""

    def test_easy_short_query(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("цена студии")
        assert result.difficulty == "easy"

    def test_hard_comparison_query(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("сравни плюсы и минусы покупки")
        assert result.difficulty == "hard"

    def test_medium_default(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("расскажи о процессе покупки недвижимости в Болгарии")
        assert result.difficulty == "medium"


class TestStyleInfoDataclass:
    """StyleInfo has all required fields."""

    def test_fields_present(self) -> None:
        info = StyleInfo(style="short", difficulty="easy", reasoning="test", word_count=3)
        assert info.style == "short"
        assert info.difficulty == "easy"
        assert info.reasoning == "test"
        assert info.word_count == 3
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_response_style_detector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telegram_bot.services.response_style_detector'`

**Step 3: Write the implementation**

Create `telegram_bot/services/response_style_detector.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_response_style_detector.py -v`
Expected: 14 PASSED

**Step 5: Commit**

```bash
git add telegram_bot/services/response_style_detector.py tests/unit/services/test_response_style_detector.py
git commit -m "feat(services): add ResponseStyleDetector with C+ scoring (#129)"
```

---

## Task 2: Contract-style prompt templates

**Files:**
- Create: `telegram_bot/integrations/prompt_templates.py`
- Create: `tests/unit/integrations/test_prompt_templates.py`
- Modify: `telegram_bot/integrations/prompt_manager.py` (style-aware prompt names + fallback wiring)
- Modify: `tests/unit/integrations/test_prompt_manager.py` (fallback and style prompt coverage)

**Step 1: Write failing tests**

Create `tests/unit/integrations/test_prompt_templates.py`:

```python
"""Tests for contract-style prompt templates."""

from __future__ import annotations

from telegram_bot.integrations.prompt_templates import (
    CONTRACT_PROMPTS,
    TOKEN_LIMITS,
    build_system_prompt,
    get_token_limit,
    get_word_limit,
)


class TestTokenLimits:
    """LASER-D inspired token budgets."""

    def test_short_easy_is_most_aggressive(self) -> None:
        assert get_token_limit("short", "easy") == 100

    def test_detailed_hard_is_most_generous(self) -> None:
        assert get_token_limit("detailed", "hard") == 350

    def test_balanced_medium_middle_ground(self) -> None:
        assert get_token_limit("balanced", "medium") == 150

    def test_unknown_combo_returns_default(self) -> None:
        assert get_token_limit("short", "unknown") == 150  # type: ignore[arg-type]

    def test_word_limit_approximation(self) -> None:
        wl = get_word_limit("short", "easy")
        assert 70 <= wl <= 90  # 100 tokens / 1.3 ≈ 76


class TestContractPrompts:
    """All three styles have contract prompts."""

    def test_all_styles_exist(self) -> None:
        assert "short" in CONTRACT_PROMPTS
        assert "balanced" in CONTRACT_PROMPTS
        assert "detailed" in CONTRACT_PROMPTS

    def test_short_prompt_has_contract(self) -> None:
        assert "OUTPUT CONTRACT" in CONTRACT_PROMPTS["short"]
        assert "{word_limit}" in CONTRACT_PROMPTS["short"]

    def test_balanced_prompt_has_contract(self) -> None:
        assert "OUTPUT CONTRACT" in CONTRACT_PROMPTS["balanced"]


class TestBuildSystemPrompt:
    """build_system_prompt renders templates correctly."""

    def test_short_prompt_renders_domain(self) -> None:
        prompt = build_system_prompt("short", "easy", "недвижимость")
        assert "недвижимость" in prompt
        assert "OUTPUT CONTRACT" in prompt

    def test_short_prompt_has_word_limit(self) -> None:
        prompt = build_system_prompt("short", "easy", "недвижимость")
        # word_limit for short/easy = 100/1.3 ≈ 76
        assert "76" in prompt or "word" in prompt.lower()

    def test_balanced_prompt_renders(self) -> None:
        prompt = build_system_prompt("balanced", "medium", "недвижимость")
        assert "недвижимость" in prompt

    def test_detailed_prompt_renders(self) -> None:
        prompt = build_system_prompt("detailed", "hard", "недвижимость")
        assert "недвижимость" in prompt
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/integrations/test_prompt_templates.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `telegram_bot/integrations/prompt_templates.py`:

```python
"""Contract-style prompt templates with explicit output constraints.

Based on best practices 2026:
- Contract-style prompts > vague adjectives ("be concise" doesn't work)
- Dynamic token budgets based on style + difficulty (LASER-D pattern)

Issue: #129
"""

from __future__ import annotations

from typing import Literal

ResponseStyle = Literal["short", "balanced", "detailed"]

CONTRACT_PROMPTS: dict[ResponseStyle, str] = {
    "short": (
        "Ты — ассистент по {domain}.\n\n"
        "OUTPUT CONTRACT (NON-NEGOTIABLE):\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1. First line = direct answer (no preambles like \"Based on context...\")\n"
        "2. Maximum {word_limit} words total\n"
        "3. No disclaimers unless missing critical info\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "MICRO-RULES:\n"
        "- Lead with fact/number, not explanation\n"
        "- For prices: \"X€ in City (size m²)\" format\n"
        "- For lists: use bullets ONLY if >=3 items\n"
        "- No \"Here are options...\" hedging\n"
        "- No \"I hope this helps\" closers"
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
    ("short", "easy"): 100,
    ("short", "medium"): 130,
    ("short", "hard"): 150,
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
```

**Step 3b: Keep prompt-manager compatibility (required)**

In `telegram_bot/integrations/prompt_templates.py`, add a wrapper that routes style prompts through `get_prompt(...)` with template fallback:

```python
from telegram_bot.integrations.prompt_manager import get_prompt

def build_system_prompt_with_manager(style: ResponseStyle, difficulty: str, domain: str) -> str:
    fallback = build_system_prompt(style, difficulty, domain)
    prompt_name = f"generate_{style}"  # generate_short / generate_balanced / generate_detailed
    return get_prompt(prompt_name, fallback=fallback, variables={"domain": domain})
```

This preserves remote prompt overrides and A/B prompt experiments in Langfuse.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/integrations/test_prompt_templates.py -v`
Expected: 10 PASSED

**Step 5: Commit**

```bash
git add telegram_bot/integrations/prompt_templates.py tests/unit/integrations/test_prompt_templates.py telegram_bot/integrations/prompt_manager.py tests/unit/integrations/test_prompt_manager.py
git commit -m "feat(integrations): add contract-style prompt templates (#129)"
```

---

## Task 3: Add response style fields to RAGState

**Files:**
- Modify: `telegram_bot/graph/state.py:13-51` (add 6 fields)
- Modify: `telegram_bot/graph/state.py:54-93` (add defaults to make_initial_state)

**Step 1: Add fields to RAGState TypedDict**

In `telegram_bot/graph/state.py`, after line 51 (`streaming_enabled: bool`), add:

```python
    # Response length control (#129)
    response_style: str
    response_difficulty: str
    response_style_reasoning: str
    answer_words: int
    answer_chars: int
    answer_to_question_ratio: float
```

**Step 2: Add defaults to make_initial_state**

In `telegram_bot/graph/state.py`, before the closing `}` of `make_initial_state` (line 93), add:

```python
        # Response length control (#129)
        "response_style": "",
        "response_difficulty": "",
        "response_style_reasoning": "",
        "answer_words": 0,
        "answer_chars": 0,
        "answer_to_question_ratio": 0.0,
```

**Step 3: Verify import works**

Run: `uv run python -c "from telegram_bot.graph.state import RAGState, make_initial_state; s = make_initial_state(0, 's', 'q'); print(s.get('response_style', 'MISSING'))"`
Expected: prints empty string (not "MISSING")

**Step 4: Commit**

```bash
git add telegram_bot/graph/state.py
git commit -m "feat(state): add response style fields to RAGState (#129)"
```

---

## Task 3.5: Add rollout flags to GraphConfig

**Files:**
- Modify: `telegram_bot/graph/config.py` (new env flags)
- Modify: `tests/unit/graph/test_config.py` (defaults + env parsing tests)

**Step 1: Add config fields**

In `GraphConfig` dataclass:

```python
response_style_enabled: bool = False
response_style_shadow_mode: bool = False
```

In `from_env()`:

```python
response_style_enabled=os.getenv("RESPONSE_STYLE_ENABLED", "false").lower() == "true",
response_style_shadow_mode=os.getenv("RESPONSE_STYLE_SHADOW_MODE", "false").lower() == "true",
```

**Step 2: Add unit tests**

- default values are `False`
- env `true` enables each flag independently

Run: `uv run pytest tests/unit/graph/test_config.py -v`

**Step 3: Commit**

```bash
git add telegram_bot/graph/config.py tests/unit/graph/test_config.py
git commit -m "feat(config): add response style rollout flags (#129)"
```

---

## Task 4: Integrate adaptive length into generate_node

**Files:**
- Modify: `telegram_bot/graph/nodes/generate.py`
- Modify: `tests/unit/graph/test_generate_node.py` (add 2 tests)
- Modify: `tests/unit/graph/test_observe_payloads.py` (if prompt/metadata payload shape changes)

**Step 1: Write 2 new failing tests**

Add to `tests/unit/graph/test_generate_node.py` at the end:

```python
class TestGenerateNodeResponseStyle:
    """Test adaptive response length control (#129)."""

    @pytest.mark.asyncio
    async def test_short_query_sets_response_style(self) -> None:
        """Short factoid query → response_style='short', metrics present."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("73,000€ в Солнечном берегу.")
        state = _make_state_with_docs(query="сколько стоит студия")

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response_style"] == "short"
        assert result["response_difficulty"] == "easy"
        assert result["response_style_reasoning"] == "explicit_short_trigger"
        assert result["answer_words"] > 0
        assert result["answer_chars"] > 0
        assert result["answer_to_question_ratio"] > 0

    @pytest.mark.asyncio
    async def test_detailed_query_sets_response_style(self) -> None:
        """Comparison query → response_style='detailed'."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config(
            "Несебр дешевле, но Равда ближе к пляжу. Вот таблица сравнения..."
        )
        state = _make_state_with_docs(query="сравни цены Несебр vs Равда подробно")

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response_style"] == "detailed"
        assert result["answer_words"] > 0
        assert result["answer_to_question_ratio"] > 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/graph/test_generate_node.py::TestGenerateNodeResponseStyle -v`
Expected: FAIL with `KeyError: 'response_style'`

**Step 3: Modify generate_node**

In `telegram_bot/graph/nodes/generate.py`:

3a. Add imports after line 21 (`from telegram_bot.observability import get_client, observe`):

```python
from telegram_bot.integrations.prompt_templates import (
    build_system_prompt_with_manager,
    get_token_limit,
)
from telegram_bot.services.response_style_detector import ResponseStyleDetector
```

3b. Add singleton detector after line 38 (`_STREAM_PLACEHOLDER = ...`):

```python
_detector = ResponseStyleDetector()
```

3c. In `_generate_streaming` signature (line 114-118), add `max_tokens: int` parameter and use it instead of `config.generate_max_tokens`:

Change line 114-118:
```python
async def _generate_streaming(
    llm: Any,
    config: Any,
    llm_messages: list[dict[str, str]],
    message: Any,
    max_tokens: int,
) -> tuple[str, str, float, int | None]:
```

Change line 150 (`max_tokens=config.generate_max_tokens,`) to:
```python
        max_tokens=max_tokens,
```

3d. In `generate_node`, move query extraction BEFORE system prompt building. Replace lines 226-228:

```python
    config = _get_config()
    context = _format_context(documents)
    system_prompt = _build_system_prompt(config.domain)
```

With:

```python
    config = _get_config()
    context = _format_context(documents)

    # Extract current query (needed for style detection before prompt building)
    last_msg = messages[-1] if messages else None
    query = ""
    if last_msg:
        query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )

    # Detect response style (C+ scoring, no LLM call, ~0ms)
    # Rollout-safe behavior:
    # - disabled: keep legacy behavior
    # - shadow mode: compute style + metrics, but keep legacy prompt/token budget
    style_info = _detector.detect(query)
    style_enabled = bool(getattr(config, "response_style_enabled", False))
    shadow_mode = bool(getattr(config, "response_style_shadow_mode", False))

    legacy_system_prompt = _build_system_prompt(config.domain)
    legacy_max_tokens = int(config.generate_max_tokens)

    style_system_prompt = build_system_prompt_with_manager(
        style=style_info.style,
        difficulty=style_info.difficulty,
        domain=config.domain,
    )
    style_budget = get_token_limit(style_info.style, style_info.difficulty)
    effective_style_budget = min(style_budget, legacy_max_tokens)

    use_style = style_enabled and not shadow_mode
    system_prompt = style_system_prompt if use_style else legacy_system_prompt
    max_tokens = effective_style_budget if use_style else legacy_max_tokens
```

3e. Remove the duplicate query extraction block (the old lines 242-250 that extract `query` again — they're now above).

3f. Replace all remaining `config.generate_max_tokens` with `max_tokens` in the function body (lines 301, 336, 348). Keep the legacy cap semantics via `min(style_budget, config.generate_max_tokens)`.

3g. Update the `_generate_streaming` call (around line 283) to pass `max_tokens`:

```python
                answer, actual_model, ttft_ms, completion_tokens = await _generate_streaming(
                    llm,
                    config,
                    llm_messages,
                    message,
                    max_tokens,
                )
```

3h. Before the final `return` dict, add response metrics:

```python
    # Response length metrics (#129)
    answer_words = len(answer.split())
    answer_chars = len(answer)
    question_words = style_info.word_count
    ratio = answer_words / max(question_words, 1)
```

3h.1. Add rollout metadata for observability:

```python
    response_policy_mode = "enforced" if use_style else ("shadow" if shadow_mode else "disabled")
```

3i. Add 7 new keys to the return dict (after `"streaming_enabled": streaming_was_enabled,`):

```python
        # Response length control (#129)
        "response_style": style_info.style,
        "response_difficulty": style_info.difficulty,
        "response_style_reasoning": style_info.reasoning,
        "answer_words": answer_words,
        "answer_chars": answer_chars,
        "answer_to_question_ratio": ratio,
        "response_policy_mode": response_policy_mode,
```

**Step 4: Run ALL generate_node tests**

Run: `uv run pytest tests/unit/graph/test_generate_node.py -v`
Expected: All PASSED

Note: Some existing tests mock `generate_max_tokens` on config. Those code paths now use the detector's `max_tokens` instead, but the tests should still pass because the LLM mock doesn't validate max_tokens values. If any test fails because `generate_max_tokens` is no longer read from config in the main path, update the test: the `test_respects_generate_max_tokens` test will need updating — it should verify that the detector-derived max_tokens is passed to the LLM call instead. See step 5.

**Step 5: Update max-token test semantics**

The test at line 281 (`test_respects_generate_max_tokens`) sets `mock_config.generate_max_tokens = 512` and asserts the LLM receives 512. After our change, generate_node uses detector-derived `max_tokens` instead of `config.generate_max_tokens`. Update this test:

```python
    @pytest.mark.asyncio
    async def test_uses_style_budget_capped_by_generate_max_tokens(self) -> None:
        """Budget must be detector-derived but never exceed config.generate_max_tokens."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config("Short answer.")
        mock_config.response_style_enabled = True
        mock_config.response_style_shadow_mode = False
        mock_config.generate_max_tokens = 40
        # Query "сколько стоит" -> short/easy baseline budget=100, capped to 40
        state = _make_state_with_docs(query="сколько стоит студия")

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("max_tokens") == 40
```

Also add one explicit shadow-mode test:
- style fields/metrics are emitted
- prompt + max_tokens remain legacy (`_build_system_prompt` + `config.generate_max_tokens`)

**Step 6: Commit**

```bash
git add telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py
git commit -m "feat(generate): integrate adaptive response length control (#129)"
```

---

## Task 5: Add Langfuse scores for response length metrics

**Files:**
- Modify: `telegram_bot/bot.py:39-104` (`_write_langfuse_scores`)
- Modify: `telegram_bot/bot.py:309-320` (`handle_query` metadata)

**Step 1: Add 4 new scores to _write_langfuse_scores**

In `telegram_bot/bot.py`, at the end of `_write_langfuse_scores` (after line 104, the `llm_queue_unavailable` block), add:

```python
    # --- Response length control (#129) ---
    if "answer_words" in result:
        lf.score_current_trace(name="answer_words", value=float(result["answer_words"]))
    if "answer_chars" in result:
        lf.score_current_trace(name="answer_chars", value=float(result["answer_chars"]))
    if "answer_to_question_ratio" in result:
        lf.score_current_trace(
            name="answer_to_question_ratio",
            value=float(result["answer_to_question_ratio"]),
        )
    if "response_style" in result:
        style_map = {"short": 0, "balanced": 1, "detailed": 2}
        lf.score_current_trace(
            name="response_style_applied",
            value=float(style_map.get(result["response_style"], 1)),
        )
```

**Step 2: Update docstring**

Change line 40 from:
```python
    """Write Langfuse scores (14 original + up to 10 latency breakdown) from graph result state.
```
To:
```python
    """Write Langfuse scores (14 + latency breakdown + 4 response length) from graph result state.
```

**Step 3: Add response style metadata to trace**

In `handle_query`, update the `metadata` dict (around line 312-319). Add after `"llm_ttft_ms"`:

```python
                    "response_style": result.get("response_style"),
                    "response_difficulty": result.get("response_difficulty"),
                    "response_style_reasoning": result.get("response_style_reasoning"),
                    "response_policy_mode": result.get("response_policy_mode"),
                    "answer_words": result.get("answer_words"),
                    "answer_to_question_ratio": result.get("answer_to_question_ratio"),
```

**Step 4: Run affected bot score tests**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py -v
uv run pytest tests/unit/test_bot_scores.py -v
uv run pytest tests/unit/test_latency_units.py -v
```

Expected:
- handler tests pass
- score-name assertions updated and pass
- latency-unit tests still pass

**Step 5: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "feat(bot): write response style metrics to Langfuse (#129)"
```

---

## Task 6: Lint + full test suite

**Step 1: Run linter and type checker**

Run: `make check`
Expected: No errors. If ruff reports unused imports or mypy reports type issues in new files, fix them.

**Step 2: Run unit tests (parallel)**

Run: `uv run pytest tests/unit/ -n auto --timeout=30`
Expected: All PASSED

**Step 3: Run graph path integration tests**

Run: `uv run pytest tests/integration/test_graph_paths.py -v`
Expected: 6 PASSED (no Docker required, verifies pipeline routing is unaffected)

**Step 4: Fix any failures**

If any test fails, read the error, fix the code, re-run.

**Step 5: Commit fixes if needed**

```bash
git add -u
git commit -m "fix: address lint/test issues from response length control (#129)"
```

---

## Task 7: Validation against issue #129 metrics

**Step 1: Run trace validation report**

Run:

```bash
uv run python scripts/validate_traces.py --collection gdrive_documents_bge --report
```

Capture:
- short-query `answer_to_question_ratio` p50/p95
- latency p95 (cold path)

**Step 2: Compare against baseline issue (#110)**

Document before/after in a short table:
- ratio p50/p95 (short queries)
- latency p95
- faithfulness/quality proxy (if RAGAS batch is available in environment)

**Step 3: Manual review (10 traces)**

Sample 10 short transactional queries and mark pass/fail for:
- direct answer first line
- no verbose preamble
- factual correctness preserved

Target: at least 8/10 satisfactory traces.

**Step 4: Rollout decision**

- If metrics are good: enable `RESPONSE_STYLE_ENABLED=true`, keep shadow mode off.
- If ratio improves but quality regresses: keep `RESPONSE_STYLE_SHADOW_MODE=true` and tune triggers/prompts.
- If regression is severe: disable both flags and rollback commit range.

---

## Task 8 (Phase 2, post-MVP): Broad-query clarifying question flow

**Goal:** For vague user intent, return a short overview plus one concrete follow-up question instead of long generic text.

**Files:**
- Modify: `telegram_bot/services/response_style_detector.py` (`is_broad` flag in `StyleInfo`)
- Modify: `tests/unit/services/test_response_style_detector.py` (broad vs specific edge cases)
- Modify: `telegram_bot/integrations/prompt_templates.py` (broad-mode contract template branch)
- Modify: `telegram_bot/graph/nodes/generate.py` (route to broad-mode prompt contract when `is_broad=True`)

**Behavior contract:**
- broad query: 1-2 short sentences with key numbers/facts
- then exactly 1 clarifying question (budget/city/rooms/etc.)
- still respect word cap and token cap

**Examples:**
- `"расскажи про недвижимость"` -> brief overview + `"Что важнее: бюджет, город или тип объекта?"`
- `"какие варианты есть"` -> brief overview + `"Уточни бюджет и город?"`
- `"какие варианты до 50000 евро в Несебре"` -> `is_broad=False` (already specific)

**Validation:**
- new unit tests for broad/non-broad boundary
- 10 manual traces with vague queries, target >=8/10 satisfactory

---

## Task 9 (Phase 3 experiment): Countdown markers A/B

**Goal:** Test whether countdown markers increase strict word-limit compliance for short mode.

**Scope:** Experiment only (feature-flagged prompt variant), not default rollout.

**Prompt variant example:**

```text
[REMAINING: ~30 words]
Ответь кратко и сразу по делу.
```

**Measurement:**
- compare compliance rate to word-limit contract baseline
- monitor any quality drop (faithfulness/manual review)

**Decision rule:**
- adopt only if compliance improves with no measurable quality regression

---

## Summary

| Task | Files | Tests | Key change |
|------|-------|-------|------------|
| 1 | +2 new | 14 | ResponseStyleDetector service |
| 2 | +2 new, 2 modified | 10 + prompt-manager tests | Contract-style templates + Langfuse prompt-manager compatibility |
| 3 | 1 modified | 0 (import check) | RAGState + make_initial_state |
| 3.5 | 1 modified | +2 | GraphConfig rollout/shadow flags |
| 4 | 2-3 modified | +3 (incl. shadow mode + cap test) | generate_node integration with rollout safety + capped budgets |
| 5 | 1 modified | bot score suite | Langfuse scores + metadata + strict score test updates |
| 6 | — | Full suite | Lint + integration validation |
| 7 | — | validation script + manual review | Metric gates for issue #129 |
| 8 | 3-4 modified | broad-edge tests + manual review | broad query -> short overview + one clarifying question |
| 9 | 1 modified | A/B experiment traces | countdown markers compliance experiment |
| **Total** | **4 new, 8-10 modified** | **~35 new/updated** | |

## Acceptance Criteria

- `uv run pytest tests/unit/ -n auto` — all pass
- `uv run pytest tests/integration/test_graph_paths.py -v` — 6 pass
- `make check` — clean
- Langfuse traces show: `answer_words`, `answer_chars`, `answer_to_question_ratio`, `response_style_applied`
- rollout flags exist and are respected: `RESPONSE_STYLE_ENABLED`, `RESPONSE_STYLE_SHADOW_MODE`
- short safety budgets are applied in plan: `short/easy=100`, `short/medium=130`, `short/hard=150`
- short query policy enforced mode: detector budget is capped by `GENERATE_MAX_TOKENS` (never exceeds config cap)
- short-query ratio targets from issue #129 are met:
  - p50 `answer_to_question_ratio` <= 8
  - p95 `answer_to_question_ratio` <= 12
- no regression guardrails from issue #129:
  - faithfulness proxy / RAGAS >= 0.8 (or no measurable downgrade vs baseline)
  - cold-path latency p95 <= 3s (or no measurable increase vs baseline)
- Phase 2/3 tasks (broad clarifying + countdown) are explicitly post-MVP and do not block Phase 1 rollout
