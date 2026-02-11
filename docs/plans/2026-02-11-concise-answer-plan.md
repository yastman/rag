# Concise Answer UX — Implementation Plan

**Goal:** Снизить многословность ответов бота на короткие запросы через adaptive response length (contract-style prompts + dynamic token budgets)

**Issue:** [#129](https://github.com/yastman/rag/issues/129) | **Milestone:** Stream-E: Quality-Eval

**Связанные документы:**
- Design: `docs/plans/2026-02-11-response-length-control-design.md`
- Implementation (детальный): `docs/plans/2026-02-11-response-length-control-implementation.md`

---

## Текущее состояние

### System Prompt (generate_node)

Файл `telegram_bot/graph/nodes/generate.py:47-54`:

    _GENERATE_FALLBACK = (
        "Ты — ассистент по {{domain}}.\n\n"
        "Отвечай на вопросы пользователя на основе предоставленного контекста.\n"
        "Если информации недостаточно, честно скажи об этом.\n"
        "Всегда указывай цены в евро и расстояния в метрах.\n"
        "Будь вежливым и полезным.\n\n"
        "Форматируй ответ с Markdown: используй **жирный** для важного, • для списков."
    )

**Проблемы:**
- Нет length constraints — LLM пишет развёрнуто по умолчанию
- `max_tokens=2048` (env `GENERATE_MAX_TOKENS`) одинаковый для всех запросов
- Промт загружается через `get_prompt("generate", fallback=_GENERATE_FALLBACK)` — строка 59
- Langfuse prompt (если создан) тоже не содержит length constraints

### Prompt Construction Flow

Файл `telegram_bot/graph/nodes/generate.py:189-310`:

    generate_node(state):
        1. config = GraphConfig.from_env()                      # config.py:62
        2. context = _format_context(documents[:5])             # generate.py:62
        3. system_prompt = _build_system_prompt(config.domain)  # generate.py:57-59
        4. user_content = f"Контекст:\n{context}\n\nВопрос: {query}\n\nОтветь..."  # :234-236
        5. LLM call: max_tokens=config.generate_max_tokens (2048)                # :297
        6. return {"response": answer, "response_sent": ..., "latency_stages": ...}

### Query Classification (classify_node)

Файл `telegram_bot/graph/nodes/classify.py:244-261`:

    classify_query(query) → 6 типов:
        CHITCHAT > OFF_TOPIC > STRUCTURED > FAQ > ENTITY > GENERAL

**Нет short/long distinction** — все типы кроме CHITCHAT/OFF_TOPIC идут через полный RAG pipeline с одинаковым промтом.

### RAGState

Файл `telegram_bot/graph/state.py:13-40`:

    20 полей, НЕТ полей для response style/metrics

### Langfuse Scores (bot.py)

Файл `telegram_bot/bot.py:39-66`:

    12 scores пишутся в `_write_langfuse_scores()`
    Нет: answer_words, answer_to_question_ratio, response_style

---

## Стратегия

### Архитектура решения

    Query → ResponseStyleDetector (0ms, pure Python)
         → style: short | balanced | detailed
         → difficulty: easy | medium | hard
         → Contract-style prompt + dynamic max_tokens (LASER-D)
         → LLM call → metrics (answer_words, ratio)
         → Langfuse scores (4 новых)

### Как определять short query

**ResponseStyleDetector** — scoring-based classifier без LLM call:

1. **Explicit detailed triggers** (приоритет 1): "подробно", "сравни", "что лучше", "плюсы и минусы" → `detailed`
2. **Explicit short triggers** (приоритет 2): "сколько стоит", "какая цена", "минимальная", "где находится" → `short`
3. **Transactional domain intents** (приоритет 3): regex паттерны "до.*евро", "какая.*цена", "есть.*наличии" → `short` (даже если 10-20 слов)
4. **Length heuristics** (fallback): ≤8 слов → `short`, ≤20 → `balanced`, >20 → `detailed`

### Как менять prompt

**Contract-style prompts** вместо vague adjectives ("be concise" не работает):

- **Short mode:** "OUTPUT CONTRACT (NON-NEGOTIABLE): Maximum {word_limit} words total. First line = direct answer."
- **Balanced mode:** "Structured answer ({word_limit} words max). 1-2 concrete examples."
- **Detailed mode:** "Comprehensive answer with analysis. Compare options."

**Dynamic token budgets** (LASER-D inspired):

    | Style     | Easy | Medium | Hard |
    |-----------|------|--------|------|
    | Short     | 50   | 80     | 100  |
    | Balanced  | 100  | 150    | 200  |
    | Detailed  | 200  | 250    | 350  |

---

## Шаги реализации

### Шаг 1. Создать ResponseStyleDetector (service)

**Файлы:**
- Создать: `telegram_bot/services/response_style_detector.py`
- Создать: `tests/unit/services/test_response_style_detector.py`

**Что делать:**
- Класс `ResponseStyleDetector` с методом `detect(query) → StyleInfo`
- Dataclass `StyleInfo`: style, difficulty, reasoning, word_count
- Precompiled regex patterns для detailed_triggers, short_triggers, transactional_patterns
- 8 unit тестов: explicit short/detailed triggers, transactional intent, length heuristics, difficulty detection

**Проверка:**

    uv run pytest tests/unit/services/test_response_style_detector.py -v
    # Expected: 8 PASSED

**Коммит:** `feat(services): add ResponseStyleDetector with C+ scoring (#129)`

---

### Шаг 2. Создать Contract-Style Prompt Templates

**Файлы:**
- Создать: `telegram_bot/integrations/prompt_templates.py`
- Создать: `tests/unit/integrations/test_prompt_templates.py`

**Что делать:**
- Dict `CONTRACT_PROMPTS` с 3 шаблонами (short/balanced/detailed)
- Dict `TOKEN_LIMITS` — (style, difficulty) → int
- Функции: `get_token_limit()`, `get_word_limit()`, `build_system_prompt()`
- Шаблоны используют placeholders: `{domain}`, `{word_limit}`, `{format}`, `{context}`, `{query}`
- 8 unit тестов: prompts exist, token limits, word limit approx, build each style, context placeholders

**Проверка:**

    uv run pytest tests/unit/integrations/test_prompt_templates.py -v
    # Expected: 8 PASSED

**Коммит:** `feat(integrations): add contract-style prompt templates (#129)`

---

### Шаг 3. Добавить поля в RAGState

**Файл:** `telegram_bot/graph/state.py:13-40`

**Что менять:** Добавить после `retrieval_error_type` (строка 39):

    # Response length control (#129)
    response_style: str
    response_difficulty: str
    response_style_reasoning: str
    answer_words: int
    answer_chars: int
    answer_to_question_ratio: float

**Проверка:**

    uv run python -c "from telegram_bot.graph.state import RAGState; print('OK')"

**Коммит:** `feat(state): add response style fields to RAGState (#129)`

---

### Шаг 4. Модифицировать generate_node

**Файлы:**
- Изменить: `telegram_bot/graph/nodes/generate.py`
- Добавить тесты: `tests/unit/graph/test_generate_node.py`

**Что менять в generate.py:**

1. **Импорты** (после строки 20):

        from telegram_bot.integrations.prompt_templates import build_system_prompt, get_token_limit
        from telegram_bot.services.response_style_detector import ResponseStyleDetector

2. **Singleton detector** (после строки 24):

        _detector = ResponseStyleDetector()

3. **В `generate_node()`** — заменить построение промта (строки 208-210):
   - Перенести извлечение query ДО построения промта (строки 225-232 → перед 209)
   - Вместо `system_prompt = _build_system_prompt(config.domain)`:

         style_info = _detector.detect(query)
         system_prompt = build_system_prompt(
             style=style_info.style,
             difficulty=style_info.difficulty,
             domain=config.domain,
         )
         max_tokens = get_token_limit(style_info.style, style_info.difficulty)

4. **Заменить `config.generate_max_tokens` → `max_tokens`** — 4 места (строки 146, 259, 283, 297)

5. **Обновить `_generate_streaming` signature** — добавить параметр `max_tokens: int` (строка 113)

6. **Удалить** `_build_system_prompt()` и `_GENERATE_FALLBACK` (строки 47-59) — больше не нужны

7. **Добавить метрики** перед return (перед строкой 306):

        answer_words = len(answer.split())
        answer_chars = len(answer)
        ratio = answer_words / max(style_info.word_count, 1)

8. **Расширить return dict** (строки 306-310):

        "response_style": style_info.style,
        "response_difficulty": style_info.difficulty,
        "response_style_reasoning": style_info.reasoning,
        "answer_words": answer_words,
        "answer_chars": answer_chars,
        "answer_to_question_ratio": ratio,

**Новые тесты** (добавить в test_generate_node.py):
- `test_generate_node_short_style_detection` — short query → response_style="short"
- `test_generate_node_detailed_style_detection` — detailed query → response_style="detailed"

**Проверка:**

    uv run pytest tests/unit/graph/test_generate_node.py -v
    # Expected: все PASSED (existing + 2 new)

**Коммит:** `feat(generate): integrate adaptive response length control (#129)`

---

### Шаг 5. Обновить Langfuse Scores в bot.py

**Файл:** `telegram_bot/bot.py`

**Что менять:**

1. **`_write_langfuse_scores()`** (после строки 64) — добавить 4 новых score:

        if "answer_words" in result:
            lf.score_current_trace(name="answer_words", value=float(result["answer_words"]))
        if "answer_chars" in result:
            lf.score_current_trace(name="answer_chars", value=float(result["answer_chars"]))
        if "answer_to_question_ratio" in result:
            lf.score_current_trace(name="answer_to_question_ratio",
                                   value=result["answer_to_question_ratio"])
        if "response_style" in result:
            style_map = {"short": 0, "balanced": 1, "detailed": 2}
            lf.score_current_trace(
                name="response_style_applied",
                value=float(style_map.get(result["response_style"], 1)),
            )

2. **Docstring** строка 40: "Write 12 Langfuse scores" → "Write 16 Langfuse scores"

3. **`update_current_trace()` metadata** (строки 272-277) — добавить:

        "response_style": result.get("response_style"),
        "response_difficulty": result.get("response_difficulty"),
        "response_style_reasoning": result.get("response_style_reasoning"),
        "answer_words": result.get("answer_words"),
        "answer_to_question_ratio": result.get("answer_to_question_ratio"),

**Проверка:**

    uv run pytest tests/unit/test_bot_handlers.py -v

**Коммит:** `feat(bot): write response style metrics to Langfuse (#129)`

---

### Шаг 6. Integration Tests

**Файл:** Создать `tests/integration/test_response_length_control.py`

**Что делать:**
- 3 теста через `build_graph()` с mocked services:
  - `test_short_query_produces_short_answer` — "сколько стоит студия" → style=short, answer_words≤60
  - `test_detailed_query_produces_detailed_answer` — "сравни цены..." → style=detailed
  - `test_transactional_query_short_style` — "квартира до 50000 евро" → style=short, reasoning=transactional_intent

**Проверка:**

    uv run pytest tests/integration/test_response_length_control.py -v
    # Expected: 3 PASSED

**Коммит:** `test(integration): add E2E tests for response length control (#129)`

---

### Шаг 7. Lint + Full Test Suite + Documentation

**Что делать:**

1. Lint & types:

        make check

2. Full unit tests:

        make test-unit

3. Graph path tests (проверить что ничего не сломали):

        uv run pytest tests/integration/test_graph_paths.py -v

4. Обновить `.claude/rules/features/telegram-bot.md`:
   - Добавить секцию "Response Length Control (#129)" с архитектурой и метриками

**Коммит:** `docs: document response length control feature (#129)`

---

## Test Strategy

| Уровень | Файл | Тестов | Покрытие |
|---------|------|--------|----------|
| Unit: Detector | `tests/unit/services/test_response_style_detector.py` | 8 | Все triggers + heuristics + difficulty |
| Unit: Templates | `tests/unit/integrations/test_prompt_templates.py` | 8 | Prompts exist, limits, build |
| Unit: generate_node | `tests/unit/graph/test_generate_node.py` | +2 | Style detection + metrics |
| Integration | `tests/integration/test_response_length_control.py` | 3 | E2E через build_graph |
| Smoke | Manual Telegram test | 1 | Проверить Langfuse scores |
| **Итого** | | **~22** | |

Команды для запуска:

    uv run pytest tests/unit/services/test_response_style_detector.py -v
    uv run pytest tests/unit/integrations/test_prompt_templates.py -v
    uv run pytest tests/unit/graph/test_generate_node.py -v
    uv run pytest tests/integration/test_response_length_control.py -v
    make check && make test-unit

---

## Acceptance Criteria

| Метрика | До | Цель | Как измерять |
|---------|-----|------|-------------|
| p50 ratio (short queries) | 11.3x | ≤ 8x | `make validate-traces-fast` |
| p95 ratio (short queries) | 15x | ≤ 12x | `make validate-traces-fast` |
| RAGAS faithfulness | 0.85 | ≥ 0.80 | `make eval-rag` |
| Cold path p95 latency | 2.5s | ≤ 3s | Langfuse traces |
| New Langfuse scores | 0 | 4 | answer_words, answer_chars, ratio, style |
| Unit tests passing | — | 22+ | `make test-unit` |
| Manual review | — | 8/10 | 10 traces review |

---

## Effort Estimate

| Шаг | Описание | Файлы |
|-----|----------|-------|
| 1 | ResponseStyleDetector | +2 файла (~80+50 LOC) |
| 2 | Prompt Templates | +2 файла (~90+50 LOC) |
| 3 | RAGState fields | state.py +6 строк |
| 4 | generate_node integration | generate.py ~30 LOC delta, +2 теста |
| 5 | Langfuse scores | bot.py ~20 LOC delta |
| 6 | Integration tests | +1 файл (~60 LOC) |
| 7 | Lint + docs | telegram-bot.md update |

**Итого:** 2 новых файла, 3 модифицированных, ~22 новых тестов

---

## Rollback Plan

    git revert <commit-range>
    docker compose build --no-cache bot
    docker compose up -d --force-recreate bot

Или env flag (если добавить):

    ADAPTIVE_LENGTH_ENABLED=false  # в generate_node

---

## Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| LLM игнорирует word limit | Средняя | Contract-style prompts + post-validation logging |
| Style detection ошибается | Низкая | 8 unit тестов + Phase 3 tuning |
| Token budget слишком жёсткий | Средняя | Conservative limits, Phase 3 tuning |
| Accuracy degradation | Низкая | RAGAS eval ≥ 0.80 + manual review |
| Latency increase | Очень низкая | Detector — pure Python (0ms) |
