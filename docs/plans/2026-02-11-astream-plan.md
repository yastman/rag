# LangGraph astream for Telegram UX — Implementation Plan

**Issue:** [#75 feat: add LangGraph streaming (astream) for Telegram UX](https://github.com/yastman/rag/issues/75)
**Priority:** P0 | **Effort:** Medium | **Milestone:** Deferred: Post-Baseline

## Goal

Заменить `graph.ainvoke()` на `graph.astream()` в bot.py для:
1. Прогресс-индикаторов по шагам пайплайна ("Ищу...", "Анализирую...", "Генерирую...")
2. Декаплинга стриминга из generate_node — логика стриминга переезжает в bot.py
3. Более чистой архитектуры — ноды не нуждаются в инъекции `message` для стриминга

## Текущее состояние

Стриминг УЖЕ работает, но реализован ВНУТРИ generate_node:

    # bot.py:262 — блокирующий вызов
    result = await graph.ainvoke(state)

    # generate.py:245-248 — стриминг через OpenAI SDK внутри ноды
    if message is not None and config.streaming_enabled:
        answer = await _generate_streaming(llm, config, llm_messages, message)
        response_sent = True

    # generate.py:137-186 — _generate_streaming()
    # Отправляет placeholder, стримит через edit_text с 300ms throttle
    # Финализирует с Markdown parse_mode

    # respond.py:36 — пропускает отправку если response_sent=True
    if state.get("response_sent", False):
        return ...

**Проблемы текущего подхода:**
- generate_node принимает `message` (aiogram) — нарушает SRP, нода знает о Telegram
- graph.py:160-170 — `_make_generate_node(message)` — boilerplate для инъекции
- Нет прогресс-индикаторов для пользователя во время retrieve/grade/rerank (5-15 секунд тишины)
- Стриминг нельзя переиспользовать вне Telegram (API, тесты)

## Streaming Architecture (target)

    Пользователь отправляет сообщение
    │
    ▼
    bot.py: handle_query()
    │
    ├── placeholder = await message.answer("⏳ Обрабатываю запрос...")
    │
    ├── async for mode, chunk in graph.astream(state, stream_mode=["updates", "custom"]):
    │       │
    │       ├── mode == "updates":
    │       │     ├── node == "classify"  → edit "🔍 Классифицирую запрос..."
    │       │     ├── node == "retrieve"  → edit "📚 Ищу документы..."
    │       │     ├── node == "rerank"    → edit "⚖️ Ранжирую результаты..."
    │       │     └── node == "generate"  → (финальный ответ в state["response"])
    │       │
    │       └── mode == "custom":
    │             └── token chunk → edit accumulated text (throttled 300ms)
    │
    └── Финализация: edit_text(final_response, parse_mode="Markdown")

**Ключевой механизм:** `stream_mode=["updates", "custom"]`
- `updates` — даёт node-level state updates для прогресс-индикаторов
- `custom` — через `StreamWriter` в generate_node, стримит LLM токены

## LangGraph API Reference

    # astream с несколькими режимами
    async for mode, chunk in graph.astream(state, stream_mode=["updates", "custom"]):
        if mode == "updates":
            # chunk = {"node_name": {"key": "value", ...}}
        elif mode == "custom":
            # chunk = arbitrary data emitted by StreamWriter

    # StreamWriter в ноде — inject через параметр
    from langgraph.config import get_stream_writer

    async def generate_node(state, *, writer=None):
        writer = writer or get_stream_writer()
        async for chunk in stream:
            writer({"token": chunk.content})  # emits to custom stream

    # Или через injection в сигнатуру ноды:
    def my_node(state: RAGState, writer: StreamWriter):
        writer({"progress": 0.5})

## Шаги реализации

### Step 1: Добавить StreamWriter в generate_node (~5 мин)

**Файл:** `telegram_bot/graph/nodes/generate.py`

1.1. Импортировать StreamWriter:

    # generate.py:1 (добавить импорт)
    from langgraph.config import get_stream_writer

1.2. Заменить `_generate_streaming()` на версию с StreamWriter:

    # generate.py:113-186 — заменить _generate_streaming()
    async def _generate_streaming_via_writer(
        llm, config, llm_messages, writer
    ) -> str:
        accumulated = ""
        stream = await llm.chat.completions.create(
            model=config.llm_model,
            messages=llm_messages,
            temperature=config.llm_temperature,
            max_tokens=config.generate_max_tokens,
            stream=True,
            name="generate-answer",
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                accumulated += delta.content
                writer({"type": "token", "content": delta.content})
        return accumulated

1.3. Обновить `generate_node` — убрать параметр `message`, добавить `writer`:

    # generate.py:190 — изменить сигнатуру
    @observe(name="node-generate")
    async def generate_node(state: RAGState) -> dict[str, Any]:
        # Получить writer через LangGraph injection
        writer = get_stream_writer()
        ...
        # Streaming path (заменить блок :245-290)
        if config.streaming_enabled:
            try:
                answer = await _generate_streaming_via_writer(
                    llm, config, llm_messages, writer
                )
            except Exception:
                # Fallback to non-streaming
                response = await llm.chat.completions.create(...)
                answer = response.choices[0].message.content or ""
        else:
            response = await llm.chat.completions.create(...)
            answer = response.choices[0].message.content or ""

1.4. Убрать `response_sent` из return — стриминг теперь в bot.py:

    # generate.py — return dict
    return {
        "response": answer,
        "latency_stages": {..., "generate": elapsed},
    }

### Step 2: Убрать инъекцию message в generate_node (~3 мин)

**Файл:** `telegram_bot/graph/graph.py`

2.1. Удалить `_make_generate_node()` (строки 160-170):

    # graph.py:160-170 — УДАЛИТЬ целиком
    # def _make_generate_node(message):
    #     ...

2.2. Заменить использование в build_graph (строка 78-81):

    # graph.py:78-81 — было:
    workflow.add_node("generate", _make_generate_node(message))

    # Стало:
    from telegram_bot.graph.nodes.generate import generate_node
    workflow.add_node("generate", generate_node)

2.3. Убрать параметр `message` из `build_graph()` сигнатуры:
**НЕТ** — `message` всё ещё нужен для `_make_respond_node(message)`.
Но можно убрать его из generate_node wiring.

### Step 3: Заменить ainvoke на astream в bot.py (~10 мин)

**Файл:** `telegram_bot/bot.py`

3.1. Создать helper для streaming delivery:

    # bot.py — новая функция (после _write_langfuse_scores)
    _PROGRESS_MESSAGES = {
        "classify": "🔍 Классифицирую запрос...",
        "cache_check": "💾 Проверяю кеш...",
        "retrieve": "📚 Ищу документы...",
        "grade": "📊 Оцениваю релевантность...",
        "rerank": "⚖️ Ранжирую результаты...",
        "generate": "✍️ Генерирую ответ...",
    }
    _STREAM_EDIT_INTERVAL = 0.3  # 300ms throttle

3.2. Заменить блок ainvoke (bot.py:261-262):

    # bot.py:261-262 — было:
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        result = await graph.ainvoke(state)

    # Стало:
    import time as _time

    placeholder = await message.answer("⏳ Обрабатываю запрос...")
    accumulated_tokens = ""
    last_edit = 0.0
    result = {}

    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        async for mode, chunk in graph.astream(
            state, stream_mode=["updates", "custom"]
        ):
            if mode == "updates":
                # chunk = {"node_name": {state_update}}
                node_name = next(iter(chunk), "")
                result.update(chunk.get(node_name, {}))

                # Прогресс-индикатор (только до generate)
                if node_name in _PROGRESS_MESSAGES and not accumulated_tokens:
                    with contextlib.suppress(Exception):
                        await placeholder.edit_text(
                            _PROGRESS_MESSAGES[node_name]
                        )

            elif mode == "custom":
                # Token streaming от generate_node
                if isinstance(chunk, dict) and chunk.get("type") == "token":
                    accumulated_tokens += chunk["content"]
                    now = _time.monotonic()
                    if now - last_edit >= _STREAM_EDIT_INTERVAL:
                        with contextlib.suppress(Exception):
                            await placeholder.edit_text(accumulated_tokens)
                        last_edit = now

    # Финализация
    final_response = result.get("response", accumulated_tokens)
    if final_response:
        try:
            await placeholder.edit_text(final_response, parse_mode="Markdown")
        except Exception:
            with contextlib.suppress(Exception):
                await placeholder.edit_text(final_response)

3.3. Добавить fallback при ошибке стриминга:

    # bot.py — обернуть весь astream блок в try/except
    try:
        # ... astream loop ...
    except Exception:
        logger.warning("astream failed, falling back to ainvoke", exc_info=True)
        result = await graph.ainvoke(state)
        await message.answer(result.get("response", "Ошибка"))

### Step 4: Обновить respond_node — убрать дублирование (~3 мин)

**Файл:** `telegram_bot/graph/nodes/respond.py`

4.1. respond_node больше НЕ отправляет сообщение при стриминге:

    # respond.py — стриминг-кейс: response уже доставлен через bot.py
    # Нода остаётся как fallback для non-streaming (тесты, API)
    # Добавить проверку: если streaming enabled, просто return latency

Вариант: оставить respond_node КАК ЕСТЬ. При streaming из bot.py,
`response_sent` больше не нужен — bot.py управляет отправкой.
Но respond_node всё равно попытается отправить через `message.answer()`.

**Решение:** Добавить новое поле `streaming_handled` в state,
которое bot.py выставляет... Нет, это overengineering.

**Лучшее решение:** При streaming в bot.py, не передавать `message` в graph.
Тогда respond_node (строка 42: `if message is not None`) не отправит.
А bot.py сам управляет Telegram delivery.

    # bot.py — при streaming НЕ передавать message:
    graph = build_graph(
        ...,
        message=None if config.streaming_enabled else message,
    )

### Step 5: Обновить RAGState — убрать response_sent (~2 мин)

**Файл:** `telegram_bot/graph/state.py`

5.1. Поле `response_sent` больше не нужно в streaming архитектуре:

    # state.py:35 — можно оставить для backward compatibility
    # или удалить если все тесты обновлены
    # РЕШЕНИЕ: оставить, deprecate в следующем PR

### Step 6: Обновить тесты (~10 мин)

**Файлы:**
- `tests/unit/graph/test_generate_node.py` — убрать тесты с `message=` параметром
- `tests/integration/test_graph_paths.py` — использовать `graph.astream()` вместо `ainvoke()`
- `tests/unit/test_bot_handlers.py` — мокать `graph.astream()` вместо `ainvoke()`

6.1. generate_node тесты:

    # Убрать тесты streaming через message injection
    # Добавить тест: generate_node emits tokens через StreamWriter
    # Mock get_stream_writer() → собрать emitted events

6.2. bot handler тесты:

    # Мокать graph.astream() — возвращать async generator
    # Проверить что placeholder создаётся и edit_text вызывается

6.3. graph path тесты:

    # Можно оставить ainvoke() — оба API работают
    # Добавить 1 тест с astream для smoke

### Step 7: Feature flag + config (~2 мин)

**Файл:** `telegram_bot/graph/config.py`

7.1. `streaming_enabled` (строка 41) уже существует — переиспользовать.

7.2. Добавить `streaming_progress` flag для прогресс-индикаторов:

    # config.py — опционально
    streaming_progress: bool = True  # показывать шаги пайплайна

    # bot.py — проверять перед edit прогресса
    if config.streaming_progress and node_name in _PROGRESS_MESSAGES:
        ...

## Результат astream loop (сборка result)

При `stream_mode="updates"` каждый node emit:

    {"classify": {"query_type": "STRUCTURED", ...}}
    {"cache_check": {"cache_hit": False, ...}}
    {"retrieve": {"documents": [...], ...}}
    ...

bot.py собирает result через `result.update(chunk[node_name])`.
После завершения astream, `result` содержит все поля как при ainvoke.

## Диаграмма потока данных

    User sends message
         │
         ▼
    bot.py: placeholder = message.answer("⏳")
         │
         ▼
    graph.astream(state, stream_mode=["updates", "custom"])
         │
         ├── updates: classify  → edit placeholder "🔍 Классифицирую..."
         ├── updates: cache_check → edit "💾 Проверяю кеш..."
         ├── updates: retrieve → edit "📚 Ищу документы..."
         ├── updates: grade → edit "📊 Оцениваю..."
         ├── updates: rerank → edit "⚖️ Ранжирую..."
         ├── custom: {type: token, content: "Вот"} → edit accumulated
         ├── custom: {type: token, content: " найденные"} → edit accumulated (throttled)
         ├── ...
         ├── updates: generate → result["response"] = full answer
         ├── updates: cache_store → (no UI update)
         └── updates: respond → (no-op, message=None)
         │
         ▼
    bot.py: placeholder.edit_text(final_response, parse_mode="Markdown")
         │
         ▼
    _write_langfuse_scores(lf, result)

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| astream API change в LangGraph | Pinned version в pyproject.toml, тесты |
| Telegram rate limit на edit_text | 300ms throttle (уже есть), catch TelegramBadRequest |
| StreamWriter не работает с @observe | Проверить совместимость langfuse + StreamWriter |
| result сборка из updates неполная | Fallback: после astream, вызвать graph.get_state() |
| Прогресс-эмодзи мелькают слишком быстро | Показывать только если node > 200ms |

## Test Strategy

1. **Unit:** generate_node emits tokens через mock StreamWriter
2. **Unit:** bot.py astream loop собирает result корректно (mock graph)
3. **Integration:** graph path tests — astream vs ainvoke дают одинаковый result
4. **Smoke:** E2E с docker — placeholder → progress → streaming → final answer
5. **Regression:** STREAMING_ENABLED=false — fallback на ainvoke работает

## Acceptance Criteria

- [ ] `graph.ainvoke()` заменён на `graph.astream()` в bot.py handle_query
- [ ] Пользователь видит прогресс-индикаторы ("Ищу...", "Генерирую...")
- [ ] LLM токены стримятся через StreamWriter + custom stream_mode
- [ ] Fallback на ainvoke при ошибке astream
- [ ] Все существующие тесты проходят (graph paths, bot handlers)
- [ ] `STREAMING_ENABLED=false` работает как раньше
- [ ] Langfuse scores пишутся корректно после astream
- [ ] respond_node не дублирует отправку при streaming

## Effort Estimate

| Шаг | Время |
|-----|-------|
| Step 1: StreamWriter в generate_node | 5 мин |
| Step 2: Убрать message injection | 3 мин |
| Step 3: astream в bot.py | 10 мин |
| Step 4: respond_node update | 3 мин |
| Step 5: RAGState cleanup | 2 мин |
| Step 6: Тесты | 10 мин |
| Step 7: Feature flag | 2 мин |
| **Итого** | **~35 мин** |
