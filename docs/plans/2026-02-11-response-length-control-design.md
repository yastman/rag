# Response Length Control Design Plan

**Issue:** #129 - Reduce verbose answers for short queries
**Goal:** Adaptive response length policy (short-first) с сохранением точности
**Date:** 2026-02-11
**Status:** Design (Ready for implementation)

---

## Executive Summary

Текущая проблема: Ответы RAG-бота избыточно длинные для коротких вопросов (ratio до 27x слов). Пользователи ожидают короткий ответ на "минимальная рассрочка какая?" (2-3 слова), но получают 30+ слов с таблицами и деталями.

**Решение:** Hybrid (C+) detector + contract-style prompts + dynamic token budgets

**Best Practices 2026** (источники: Lakera, Claude Guides, OpenAI Docs, ICLR 2026):
- Default short-first для транзакционных запросов
- Structured output > vague adjectives ("be concise" не работает)
- Contract-style prompts с явными constraints
- Dynamic token budget на основе style + difficulty (LASER-D pattern)

---

## Architecture Overview

```
User Query
    ↓
classify_node (existing)
    ↓
[NEW] response_style_detector (Python function, not LLM call)
    ↓
    → style: "short" | "balanced" | "detailed"
    → difficulty: "easy" | "medium" | "hard"
    ↓
generate_node (modified)
    ↓
    → Select prompt template (contract-style)
    → Set dynamic max_tokens
    → Add style metadata to state
    ↓
LLM call (langfuse.openai.AsyncOpenAI)
    ↓
[NEW] post_validation (optional, logging only)
    ↓
Langfuse trace
    → scores: answer_words, answer_to_question_ratio, response_style_applied
```

---

## Component Design

### 1. Response Style Detector (Service Layer)

**File:** `telegram_bot/services/response_style_detector.py`

**Purpose:** Scoring-based classifier для определения response_style БЕЗ LLM call (+0ms latency)

**Interface:**
```python
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
    """Detect response style using scoring heuristics (C+ pattern)."""

    def __init__(self):
        # Precompiled regex patterns for performance
        self._detailed_triggers = re.compile(
            r"(подробно|детально|пошагово|объясни|почему|развернуто|"
            r"все варианты|с примерами|сравни|плюсы и минусы|что лучше|"
            r"расскажи про|как работает|в чем разница)",
            re.IGNORECASE
        )
        self._short_triggers = re.compile(
            r"(кратко|только ответ|без деталей|одним предложением|"
            r"да или нет|есть ли|сколько стоит|какая цена|минимальная|"
            r"максимальная|когда|где находится|адрес|часы работы)",
            re.IGNORECASE
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
        """Detect response style using C+ scoring with domain intents.

        Priority:
        1. Explicit detailed triggers → "detailed"
        2. Explicit short triggers → "short"
        3. Transactional domain intents → "short" (even if 10-20 words)
        4. Length heuristics (fallback)

        Returns:
            StyleInfo with style, difficulty, reasoning, word_count
        """
        query_lower = query.lower()
        words = query.split()
        word_count = len(words)

        # 1. Explicit detailed triggers (highest priority)
        if self._detailed_triggers.search(query_lower):
            return StyleInfo(
                style="detailed",
                difficulty=self._detect_difficulty(query, word_count),
                reasoning="explicit_detailed_trigger",
                word_count=word_count,
            )

        # 2. Explicit short triggers
        if self._short_triggers.search(query_lower):
            return StyleInfo(
                style="short",
                difficulty="easy",  # short triggers imply easy
                reasoning="explicit_short_trigger",
                word_count=word_count,
            )

        # 3. Transactional domain intents (short-first even if 10-20 words)
        if any(pattern.search(query_lower) for pattern in self._transactional_patterns):
            return StyleInfo(
                style="short",
                difficulty="easy",
                reasoning="transactional_intent",
                word_count=word_count,
            )

        # 4. Length heuristics (fallback)
        if word_count <= 8:
            style = "short"
            reasoning = "short_query"
        elif word_count <= 20:
            style = "balanced"
            reasoning = "medium_query"
        else:
            style = "detailed"
            reasoning = "long_query"

        return StyleInfo(
            style=style,
            difficulty=self._detect_difficulty(query, word_count),
            reasoning=reasoning,
            word_count=word_count,
        )

    def _detect_difficulty(self, query: str, word_count: int) -> Difficulty:
        """Detect query difficulty for token budget allocation."""
        # Comparison/analysis keywords → hard
        if any(kw in query.lower() for kw in ["сравни", "что лучше", "плюсы и минусы"]):
            return "hard"

        # Simple factoid/transactional → easy
        if word_count <= 5:
            return "easy"

        # Default: medium
        return "medium"
```

**Dependencies:** `re`, `dataclasses`, `typing`

**Tests:** `tests/unit/services/test_response_style_detector.py`

---

### 2. Contract-Style Prompt Templates (Integration Layer)

**File:** `telegram_bot/integrations/prompt_templates.py`

**Purpose:** Явные constraints для каждого response_style (Contract-style prompts)

**Implementation:**
```python
"""Contract-style prompt templates with explicit output constraints.

Based on best practices 2026:
- Lakera Prompt Engineering Guide
- Claude Prompt Engineering Best Practices
- OpenAI GPT-5 Documentation
"""

from typing import Literal

ResponseStyle = Literal["short", "balanced", "detailed"]

# Contract-style prompts with EXPLICIT constraints (not vague adjectives)
CONTRACT_PROMPTS: dict[ResponseStyle, str] = {
    "short": """Ты — ассистент по {domain}.

OUTPUT CONTRACT (NON-NEGOTIABLE):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. First line = direct answer (no preambles like "Based on context...")
2. Maximum {word_limit} words total
3. Structure: **Answer** [optional: "Want details?"]
4. No disclaimers unless missing critical info
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MICRO-RULES:
- Lead with fact/number, not explanation
- For prices: "X€ in City (size m²)" format
- For lists: use bullets ONLY if ≥3 items
- No "Here are options..." hedging
- No "I hope this helps" closers

EXAMPLES:
Q: "Сколько стоит студия?"
A: **73,000€ в Солнечном берегу (49 м²)**. Ещё варианты?

Q: "Минимальная рассрочка?"
A: **2 года минимум**. Скажи бюджет — найду варианты.

Контекст:
{context}

Вопрос: {query}

Ответ:""",

    "balanced": """Ты — ассистент по {domain}.

OUTPUT CONTRACT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Structured answer ({word_limit} words max)
- Format: {format}
- 1-2 concrete examples with key parameters
- Brief summary or recommendation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STYLE:
- Start with direct answer, then context
- Use tables for comparing 2+ items
- Use bullets for lists

Контекст:
{context}

Вопрос: {query}

Ответ:""",

    "detailed": """Ты — ассистент по {domain}.

DETAILED MODE ENABLED:
- Comprehensive answer with analysis
- Compare options if applicable
- Use tables/structure for readability
- Include pros/cons if requested

Контекст:
{context}

Вопрос: {query}

Ответ:"""
}

# LASER-D inspired token budgets (difficulty-aware)
TOKEN_LIMITS: dict[tuple[ResponseStyle, str], int] = {
    ("short", "easy"): 50,        # Factoid queries: aggressive limit
    ("short", "medium"): 80,
    ("short", "hard"): 100,
    ("balanced", "easy"): 100,
    ("balanced", "medium"): 150,
    ("balanced", "hard"): 200,
    ("detailed", "easy"): 200,
    ("detailed", "medium"): 250,
    ("detailed", "hard"): 350,
}

def get_token_limit(style: ResponseStyle, difficulty: str) -> int:
    """Get dynamic token budget based on style + difficulty."""
    return TOKEN_LIMITS.get((style, difficulty), 150)

def get_word_limit(style: ResponseStyle, difficulty: str) -> int:
    """Approximate word limit from token budget."""
    tokens = get_token_limit(style, difficulty)
    return int(tokens / 1.3)  # tokens → words approximation

def build_system_prompt(
    style: ResponseStyle,
    difficulty: str,
    domain: str,
    format: str = "bullets"
) -> str:
    """Build contract-style system prompt with dynamic constraints."""
    template = CONTRACT_PROMPTS[style]
    word_limit = get_word_limit(style, difficulty)

    return template.format(
        domain=domain,
        word_limit=word_limit,
        format=format
    )
```

**Tests:** `tests/unit/integrations/test_prompt_templates.py`

---

### 3. Modified generate_node (LangGraph Node)

**File:** `telegram_bot/graph/nodes/generate.py`

**Changes:**
1. Import `ResponseStyleDetector` и `prompt_templates`
2. Detect style BEFORE building prompt
3. Use contract-style prompt + dynamic max_tokens
4. Add style metadata to state
5. Record metrics для Langfuse

**Implementation:**
```python
"""generate_node — LLM answer generation with adaptive response length.

MODIFIED: 2026-02-11 (#129)
- Added response style detection (short/balanced/detailed)
- Contract-style prompts with explicit constraints
- Dynamic token budgets based on style + difficulty
- Langfuse metadata: response_style, word_count, ratio
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from telegram_bot.graph.state import RAGState
from telegram_bot.integrations.prompt_manager import get_prompt
from telegram_bot.integrations.prompt_templates import (
    build_system_prompt,
    get_token_limit,
)
from telegram_bot.services.response_style_detector import ResponseStyleDetector
from telegram_bot.observability import observe

logger = logging.getLogger(__name__)

_MAX_CONTEXT_DOCS = 5
_STREAM_EDIT_INTERVAL = 0.3
_STREAM_PLACEHOLDER = "⏳ Генерирую ответ..."

# Singleton detector (compiled regex patterns)
_detector = ResponseStyleDetector()


def _get_config() -> Any:
    """Get GraphConfig from environment."""
    from telegram_bot.graph.config import GraphConfig
    return GraphConfig.from_env()


def _format_context(documents: list[dict[str, Any]], max_docs: int = _MAX_CONTEXT_DOCS) -> str:
    """Format top-N retrieved documents into LLM context string."""
    if not documents:
        return "Релевантной информации не найдено."

    parts: list[str] = []
    for i, doc in enumerate(documents[:max_docs], 1):
        text = doc.get("text", "")
        metadata = doc.get("metadata", {})
        score = doc.get("score", 0)

        meta_str = ""
        if "title" in metadata:
            meta_str += f"Название: {metadata['title']}\n"
        if "city" in metadata:
            meta_str += f"Город: {metadata['city']}\n"
        if "price" in metadata:
            meta_str += f"Цена: {metadata['price']:,}€\n"

        parts.append(f"[Объект {i}] (релевантность: {score:.2f})\n{meta_str}{text}")

    return "\n\n---\n\n".join(parts)


def _build_fallback_response(documents: list[dict[str, Any]]) -> str:
    """Build fallback response from retrieved documents when LLM fails."""
    if not documents:
        return "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."

    fallback = "⚠️ Сервис генерации ответов временно недоступен.\n\n"
    fallback += "Вот найденные объекты по вашему запросу:\n\n"

    for i, doc in enumerate(documents[:3], 1):
        meta = doc.get("metadata", {})
        fallback += f"{i}. "
        if "title" in meta:
            fallback += f"{meta['title']}\n"
        if "price" in meta:
            price = meta["price"]
            if isinstance(price, int | float):
                fallback += f"   Цена: {price:,}€\n"
            else:
                fallback += f"   Цена: {price}€\n"
        if "city" in meta:
            fallback += f"   Город: {meta['city']}\n"
        fallback += "\n"

    fallback += "Пожалуйста, попробуйте повторить запрос позже для получения детального ответа."
    return fallback


async def _generate_streaming(
    llm: Any,
    config: Any,
    llm_messages: list[dict[str, str]],
    message: Any,
    max_tokens: int,
) -> str:
    """Stream LLM response directly to Telegram via message editing.

    Args:
        llm: AsyncOpenAI client instance.
        config: GraphConfig with model parameters.
        llm_messages: OpenAI-format message list.
        message: aiogram Message object for Telegram delivery.
        max_tokens: Dynamic token limit based on style.

    Returns:
        Complete response text.

    Raises:
        Exception: On any streaming failure (caller handles fallback).
    """
    sent_msg = await message.answer(_STREAM_PLACEHOLDER)

    accumulated = ""
    last_edit = 0.0

    stream = await llm.chat.completions.create(
        model=config.llm_model,
        messages=llm_messages,
        temperature=config.llm_temperature,
        max_tokens=max_tokens,  # Dynamic based on style
        stream=True,
        name="generate-answer",  # type: ignore[call-overload]
    )

    try:
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                accumulated += delta.content
                now = time.monotonic()
                if now - last_edit >= _STREAM_EDIT_INTERVAL:
                    with contextlib.suppress(Exception):
                        await sent_msg.edit_text(accumulated)
                    last_edit = now
    except Exception:
        if accumulated:
            raise StreamingPartialDeliveryError(sent_msg, accumulated) from None
        with contextlib.suppress(Exception):
            await sent_msg.delete()
        raise

    if not accumulated:
        with contextlib.suppress(Exception):
            await sent_msg.delete()
        raise ValueError("Streaming produced empty response")

    # Final edit with Markdown formatting
    try:
        await sent_msg.edit_text(accumulated, parse_mode="Markdown")
    except Exception:
        try:
            await sent_msg.edit_text(accumulated)
        except Exception:
            logger.warning("Failed to finalize streaming message")

    return accumulated


class StreamingPartialDeliveryError(Exception):
    """Raised when streaming delivered partial content to user then failed."""
    def __init__(self, sent_msg: Any, partial_text: str):
        self.sent_msg = sent_msg
        self.partial_text = partial_text
        super().__init__(f"Streaming failed after delivering {len(partial_text)} chars")


@observe(name="node-generate")
async def generate_node(state: RAGState, *, message: Any | None = None) -> dict[str, Any]:
    """Generate an answer from retrieved documents using LLM.

    ADAPTIVE RESPONSE LENGTH (#129):
    1. Detect response style (short/balanced/detailed) from query
    2. Select contract-style prompt with explicit constraints
    3. Set dynamic max_tokens based on style + difficulty
    4. Record metrics: response_style, answer_words, ratio

    When message is provided and streaming is enabled, streams the response
    directly to Telegram via edit_text. Falls back to non-streaming on error.

    Returns partial state update with response, response_sent flag, latency,
    and response style metadata.
    """
    t0 = time.monotonic()

    documents = state.get("documents", [])
    messages = state.get("messages", [])

    config = _get_config()
    context = _format_context(documents)

    # Extract current query
    last_msg = messages[-1] if messages else None
    query = ""
    if last_msg:
        query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )

    # 🆕 STEP 1: Detect response style (C+ scoring, no LLM call)
    style_info = _detector.detect(query)

    logger.info(
        "Response style detected: %s (difficulty=%s, reasoning=%s, words=%d)",
        style_info.style,
        style_info.difficulty,
        style_info.reasoning,
        style_info.word_count,
    )

    # 🆕 STEP 2: Build contract-style system prompt
    system_prompt = build_system_prompt(
        style=style_info.style,
        difficulty=style_info.difficulty,
        domain=config.domain,
    )

    # 🆕 STEP 3: Get dynamic token budget (LASER-D inspired)
    max_tokens = get_token_limit(style_info.style, style_info.difficulty)

    # Build OpenAI-format messages
    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Add conversation history (all messages except the last user message)
    for msg in messages[:-1]:
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role in ("user", "human"):
            llm_messages.append({"role": "user", "content": str(content)})
        elif role in ("assistant", "ai"):
            llm_messages.append({"role": "assistant", "content": str(content)})

    # Add current query with context
    user_content = (
        f"Контекст:\n{context}\n\nВопрос: {query}\n\nОтветь на вопрос на основе контекста выше."
    )
    llm_messages.append({"role": "user", "content": user_content})

    response_sent = False

    try:
        llm = config.create_llm()

        # Streaming path: deliver directly to Telegram
        if message is not None and config.streaming_enabled:
            try:
                answer = await _generate_streaming(llm, config, llm_messages, message, max_tokens)
                response_sent = True
            except StreamingPartialDeliveryError as e:
                logger.warning(
                    "Streaming failed after partial delivery (%d chars), "
                    "falling back to non-streaming with edit",
                    len(e.partial_text),
                    exc_info=True,
                )
                response = await llm.chat.completions.create(
                    model=config.llm_model,
                    messages=llm_messages,
                    temperature=config.llm_temperature,
                    max_tokens=max_tokens,
                    name="generate-answer",  # type: ignore[call-overload]
                )
                answer = response.choices[0].message.content or ""
                # Edit existing message with fallback answer
                delivered = False
                try:
                    await e.sent_msg.edit_text(answer, parse_mode="Markdown")
                    delivered = True
                except Exception:
                    try:
                        await e.sent_msg.edit_text(answer)
                        delivered = True
                    except Exception:
                        logger.warning(
                            "Failed to deliver fallback edit after partial stream; "
                            "respond_node will send final answer",
                            exc_info=True,
                        )
                response_sent = delivered
            except Exception:
                logger.warning("Streaming failed, falling back to non-streaming", exc_info=True)
                response = await llm.chat.completions.create(
                    model=config.llm_model,
                    messages=llm_messages,
                    temperature=config.llm_temperature,
                    max_tokens=max_tokens,
                    name="generate-answer",  # type: ignore[call-overload]
                )
                answer = response.choices[0].message.content or ""
        else:
            # Non-streaming path
            response = await llm.chat.completions.create(
                model=config.llm_model,
                messages=llm_messages,
                temperature=config.llm_temperature,
                max_tokens=max_tokens,
                name="generate-answer",  # type: ignore[call-overload]
            )
            answer = response.choices[0].message.content or ""
    except Exception:
        logger.exception("generate_node: LLM call failed, using fallback")
        answer = _build_fallback_response(documents)

    # 🆕 STEP 4: Calculate response metrics
    answer_words = len(answer.split())
    answer_chars = len(answer)
    question_words = style_info.word_count
    ratio = answer_words / max(question_words, 1)

    # 🆕 STEP 5: Post-validation logging (non-blocking)
    expected_word_limit = int(max_tokens / 1.3)
    if style_info.style == "short" and answer_words > expected_word_limit * 1.5:
        logger.warning(
            "Response longer than expected for short mode: %d words (expected ~%d, ratio %.1fx)",
            answer_words,
            expected_word_limit,
            ratio,
        )

    elapsed = time.monotonic() - t0

    return {
        "response": answer,
        "response_sent": response_sent,
        "latency_stages": {**state.get("latency_stages", {}), "generate": elapsed},
        # 🆕 Response style metadata
        "response_style": style_info.style,
        "response_difficulty": style_info.difficulty,
        "response_style_reasoning": style_info.reasoning,
        "answer_words": answer_words,
        "answer_chars": answer_chars,
        "answer_to_question_ratio": ratio,
    }
```

**Tests:** `tests/unit/graph/test_generate_node.py` (update existing)

---

### 4. Langfuse Scores Integration (Bot Layer)

**File:** `telegram_bot/bot.py`

**Changes:** Update `_write_langfuse_scores()` to include new response length metrics

**Implementation:**
```python
def _write_langfuse_scores(lf: Any, state: dict[str, Any]) -> None:
    """Write Langfuse scores from final state.

    MODIFIED: 2026-02-11 (#129)
    - Added: answer_words, answer_chars, answer_to_question_ratio
    - Added: response_style_applied
    """
    # ... existing scores (latency_total_ms, cache_hit, etc.) ...

    # 🆕 Response length metrics (#129)
    if "answer_words" in state:
        lf.score(name="answer_words", value=state["answer_words"])

    if "answer_chars" in state:
        lf.score(name="answer_chars", value=state["answer_chars"])

    if "answer_to_question_ratio" in state:
        lf.score(name="answer_to_question_ratio", value=state["answer_to_question_ratio"])

    if "response_style" in state:
        # Convert style to numeric for aggregation: short=0, balanced=1, detailed=2
        style_map = {"short": 0, "balanced": 1, "detailed": 2}
        lf.score(
            name="response_style_applied",
            value=style_map.get(state["response_style"], 1),
            comment=f"{state['response_style']} ({state.get('response_difficulty', 'unknown')})",
        )
```

**Also update:** `update_current_trace()` metadata в `handle_query()`

```python
# In PropertyBot.handle_query()
lf.update_current_trace(
    input={"query": query},
    output={"response": result.get("response", "")[:200]},
    metadata={
        # ... existing metadata ...
        "response_style": result.get("response_style"),
        "response_difficulty": result.get("response_difficulty"),
        "response_style_reasoning": result.get("response_style_reasoning"),
        "answer_words": result.get("answer_words"),
        "answer_to_question_ratio": result.get("answer_to_question_ratio"),
    },
)
```

---

### 5. State Updates (LangGraph State)

**File:** `telegram_bot/graph/state.py`

**Changes:** Add response style fields to `RAGState` TypedDict

```python
class RAGState(TypedDict, total=False):
    # ... existing fields ...

    # 🆕 Response length control (#129)
    response_style: str  # "short" | "balanced" | "detailed"
    response_difficulty: str  # "easy" | "medium" | "hard"
    response_style_reasoning: str  # e.g., "explicit_short_trigger"
    answer_words: int
    answer_chars: int
    answer_to_question_ratio: float
```

---

## Implementation Plan

### Phase 1: Core Implementation (MVP - 1-2 days)

**Goal:** Минимальный working prototype с contract prompts + dynamic max_tokens

**Tasks:**
1. ✅ Create `ResponseStyleDetector` service
   - File: `telegram_bot/services/response_style_detector.py`
   - Tests: `tests/unit/services/test_response_style_detector.py`
   - Coverage: 90%+

2. ✅ Create contract-style prompt templates
   - File: `telegram_bot/integrations/prompt_templates.py`
   - Tests: `tests/unit/integrations/test_prompt_templates.py`
   - Validate: All 3 prompts render correctly

3. ✅ Modify `generate_node`
   - File: `telegram_bot/graph/nodes/generate.py`
   - Changes: Import detector, detect style, use templates, dynamic max_tokens
   - Tests: Update existing `test_generate_node.py` with new scenarios

4. ✅ Update `RAGState`
   - File: `telegram_bot/graph/state.py`
   - Add: response_style, difficulty, metrics fields

5. ✅ Update Langfuse scores
   - File: `telegram_bot/bot.py`
   - Function: `_write_langfuse_scores()`
   - Add: answer_words, answer_chars, ratio, response_style_applied

**Validation:**
```bash
# Unit tests
uv run pytest tests/unit/services/test_response_style_detector.py -v
uv run pytest tests/unit/integrations/test_prompt_templates.py -v
uv run pytest tests/unit/graph/test_generate_node.py -v

# Integration test (single query)
uv run python -m scripts.test_single_query \
    --query "минимальная рассрочка какая?" \
    --collection gdrive_documents_bge

# Check Langfuse trace
# → Look for: response_style=short, answer_words<40, ratio<8x
```

---

### Phase 2: Validation & Measurement (2-3 days)

**Goal:** A/B test + baseline comparison

**Tasks:**
6. ✅ Run validation script (cold + cache)
   ```bash
   uv run python scripts/validate_traces.py \
       --collection gdrive_documents_bge \
       --report
   ```

7. ✅ Baseline comparison (#110 goldset)
   - Compare answer_to_question_ratio p50/p95: before vs after
   - Target: p50 ratio ≤ 8x для short queries (сейчас ~11x)

8. ✅ Manual review (10 traces)
   - Short queries: Are answers concise? No preambles?
   - Balanced queries: 1-2 examples present?
   - Detailed queries: No degradation in quality?

9. ✅ Add monitoring dashboard (Langfuse)
   - Chart: answer_to_question_ratio over time
   - Chart: response_style_applied distribution
   - Alert: если p95 ratio > 15x для short queries

**Success Criteria:**
- ✅ p50 ratio для short queries снизился с 11x до ≤8x
- ✅ Accuracy не ухудшилась (RAGAS faithfulness >= 0.8)
- ✅ Latency не выросла (cold p95 <= 3s)

---

### Phase 3: Refinement (optional, 1-2 days)

**Goal:** Fine-tuning на основе production data

**Tasks:**
10. ⚠️ Collect edge cases
    - Queries где style detection ошибается
    - Queries где ответ всё равно длинный

11. ⚠️ Tune regex patterns
    - Add missed triggers в `_detailed_triggers` / `_short_triggers`
    - Adjust transactional patterns

12. ⚠️ Tune token limits
    - Если short queries всё равно > 40 words → снизить limits
    - Если detailed queries обрезаются → увеличить limits

13. ⚠️ A/B test промт wording
    - Variant A: "Maximum {word_limit} words"
    - Variant B: "Reply in 1-2 sentences (15-40 words)"
    - Measure: compliance rate

---

## Testing Strategy

### Unit Tests

**Coverage targets:** 90%+

```python
# tests/unit/services/test_response_style_detector.py
def test_detect_short_explicit_trigger():
    detector = ResponseStyleDetector()
    result = detector.detect("сколько стоит студия")
    assert result.style == "short"
    assert result.reasoning == "explicit_short_trigger"

def test_detect_transactional_intent():
    detector = ResponseStyleDetector()
    result = detector.detect("квартира до 50000 евро с мебелью")
    assert result.style == "short"
    assert result.reasoning == "transactional_intent"

def test_detect_detailed_explicit_trigger():
    detector = ResponseStyleDetector()
    result = detector.detect("сравни цены Несебр vs Равда")
    assert result.style == "detailed"
    assert result.reasoning == "explicit_detailed_trigger"

def test_length_heuristic_fallback():
    detector = ResponseStyleDetector()
    result = detector.detect("random text with more than twenty words here to test fallback")
    assert result.style == "detailed"
    assert result.reasoning == "long_query"

# tests/unit/integrations/test_prompt_templates.py
def test_build_short_prompt():
    prompt = build_system_prompt("short", "easy", "недвижимость")
    assert "OUTPUT CONTRACT" in prompt
    assert "words max" in prompt.lower()
    assert "недвижимость" in prompt

def test_token_limit_laser_d():
    assert get_token_limit("short", "easy") == 50
    assert get_token_limit("detailed", "hard") == 350

# tests/unit/graph/test_generate_node.py
@pytest.mark.asyncio
async def test_generate_node_short_style(mock_llm, mock_config):
    state = {
        "messages": [{"role": "user", "content": "сколько стоит студия"}],
        "documents": [{"text": "Студия 73,000€", "metadata": {"city": "Несебр"}}],
    }
    result = await generate_node(state)

    assert result["response_style"] == "short"
    assert result["response_difficulty"] == "easy"
    assert result["answer_words"] < 50  # contract enforced
    assert result["answer_to_question_ratio"] < 15  # improved ratio
```

### Integration Tests

**File:** `tests/integration/test_response_length_control.py`

```python
@pytest.mark.asyncio
async def test_short_query_produces_short_answer():
    """Short query should trigger short style and produce concise answer."""
    query = "минимальная рассрочка какая?"

    # Run through full pipeline
    state = make_initial_state(user_id=0, session_id="test", query=query)
    graph = build_graph(...)
    result = await graph.ainvoke(state)

    # Assertions
    assert result["response_style"] == "short"
    assert result["answer_words"] <= 50
    assert result["answer_to_question_ratio"] < 10
    assert not result["response"].startswith("На основании")  # no preamble

@pytest.mark.asyncio
async def test_detailed_query_produces_detailed_answer():
    """Detailed query should trigger detailed style and produce comprehensive answer."""
    query = "сравни цены Солнечный берег vs Святой Влас 2024"

    state = make_initial_state(user_id=0, session_id="test", query=query)
    graph = build_graph(...)
    result = await graph.ainvoke(state)

    assert result["response_style"] == "detailed"
    assert result["answer_words"] > 100
```

---

## Monitoring & Observability

### Langfuse Dashboards

**New Charts:**
1. **Answer Length Trend** (line chart)
   - X: timestamp
   - Y: answer_words (p50, p95)
   - Group by: response_style

2. **Ratio Distribution** (histogram)
   - X: answer_to_question_ratio bins (0-5, 5-10, 10-15, 15-20, 20+)
   - Y: count
   - Filter: response_style=short

3. **Style Application** (pie chart)
   - Segments: short, balanced, detailed
   - Values: count

### Alerts (Langfuse or Grafana)

```yaml
alerts:
  - name: "Excessive Verbosity for Short Queries"
    condition: p95(answer_to_question_ratio WHERE response_style=short) > 15
    severity: warning
    channel: slack

  - name: "Style Detection Failure"
    condition: rate(response_style=null) > 0.05
    severity: error
    channel: slack
```

---

## Rollback Plan

Если после deploy метрики ухудшились:

1. **Immediate rollback** (< 5 min)
   ```bash
   git revert <commit-hash>
   docker compose build --no-cache bot
   docker compose up -d --force-recreate bot
   ```

2. **Feature flag** (если доступен)
   ```python
   # In generate_node
   USE_ADAPTIVE_LENGTH = os.getenv("ADAPTIVE_LENGTH_ENABLED", "false") == "true"

   if USE_ADAPTIVE_LENGTH:
       style_info = _detector.detect(query)
       ...
   else:
       # Old behavior: use fallback prompt
       system_prompt = get_prompt("generate", fallback=_GENERATE_FALLBACK)
   ```

3. **Gradual rollout** (production)
   ```python
   # Route 10% traffic to new behavior
   if hash(session_id) % 10 == 0:
       # New adaptive length
   else:
       # Old behavior
   ```

---

## Dependencies

**New:**
- None (pure Python, uses existing stack)

**Modified:**
- `telegram_bot/graph/nodes/generate.py`
- `telegram_bot/graph/state.py`
- `telegram_bot/bot.py`

**Added:**
- `telegram_bot/services/response_style_detector.py`
- `telegram_bot/integrations/prompt_templates.py`
- `tests/unit/services/test_response_style_detector.py`
- `tests/unit/integrations/test_prompt_templates.py`
- `tests/integration/test_response_length_control.py`

---

## Success Metrics

| Metric | Current (baseline) | Target | Measurement |
|--------|-------------------|--------|-------------|
| p50 ratio (short queries) | 11.3x | ≤ 8x | Langfuse validation script |
| p95 ratio (short queries) | 15x | ≤ 12x | Langfuse validation script |
| Accuracy (RAGAS faithfulness) | 0.85 | ≥ 0.80 | `make eval-rag` |
| Cold path p95 latency | 2.5s | ≤ 3s | Langfuse traces |
| User satisfaction (manual review) | N/A | 8/10 | Manual review (10 traces) |

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Style detection errors | Medium | Low | Extensive unit tests + manual review |
| LLM ignores constraints | High | Medium | Contract-style prompts + post-validation |
| Accuracy degradation | High | Low | RAGAS eval + manual review |
| Latency increase | Medium | Very Low | Detector is pure Python (no LLM call) |
| Token budget too aggressive | Medium | Medium | Conservative limits + Phase 3 tuning |

---

## References

**Best Practices 2026:**
- Lakera Prompt Engineering Guide (https://www.lakera.ai/blog/prompt-engineering-guide)
- Claude Prompt Engineering Best Practices (https://promptbuilder.cc/blog/claude-prompt-engineering-best-practices-2026)
- OpenAI GPT-5 Documentation (https://help.openai.com/en/articles/5072518-controlling-the-length-of-openai-model-responses)
- LASER-D: Learn to Reason Efficiently with Adaptive Length-based Reward Shaping (ICLR 2026)

**Context7 Documentation:**
- Langfuse Python SDK: `/langfuse/langfuse-docs`
- LangGraph: `/websites/langchain_oss_python_langgraph`
- OpenAI Python: `/openai/openai-python`

**Internal Docs:**
- `.claude/rules/observability.md` — Langfuse patterns
- `.claude/rules/features/telegram-bot.md` — LangGraph pipeline
- `.claude/rules/features/llm-integration.md` — LLM service patterns

---

## Next Steps

1. Review design plan with team
2. Create GitHub issue #129 subtasks from Phase 1
3. Implement Phase 1 (MVP)
4. Run validation (Phase 2)
5. Iterate based on metrics (Phase 3)

**Estimated Timeline:** 5-7 days (Phase 1: 2d, Phase 2: 2-3d, Phase 3: 1-2d optional)

---

*Design approved: [Pending]*
*Implementation start: [TBD]*
