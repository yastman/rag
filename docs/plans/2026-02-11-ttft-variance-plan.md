# TTFT Variance Investigation + Provider Metadata — Implementation Plan

**Goal:** Записать provider/model metadata в Langfuse traces для каждого LLM-вызова, чтобы диагностировать 28x variance в generate-answer latency (839ms–23,393ms) и определить, какой provider из LiteLLM fallback chain (Cerebras → Cerebras GLM → Groq → OpenAI) вызывает tail latency.

**Issue:** https://github.com/yastman/rag/issues/124

**Milestone:** Stream-A: Latency-LLM+Embed

## Architecture

Затрагиваемые модули:

    Bot → AsyncOpenAI → LiteLLM Proxy (:4000) → Cerebras/Groq/OpenAI
                                    ↓
                        x-litellm-model-id (response header)
                        x-litellm-response-duration-ms
                        x-litellm-overhead-duration-ms

| Модуль | Файл | Что меняем |
|--------|------|-----------|
| LLM генерация | `telegram_bot/graph/nodes/generate.py` | Извлечение provider metadata из response |
| Rewrite | `telegram_bot/graph/nodes/rewrite.py` | Извлечение provider metadata из response |
| State | `telegram_bot/graph/state.py` | Новые поля для provider metadata |
| Scores | `telegram_bot/bot.py` | Новые Langfuse scores для provider/TTFT |
| Observability | `telegram_bot/observability.py` | Без изменений (уже работает) |

## Tech Stack

| Компонент | Версия | Роль |
|-----------|--------|------|
| LiteLLM Proxy | v1.81.0 | Возвращает response headers с provider metadata |
| langfuse.openai.AsyncOpenAI | SDK v3 | Drop-in OpenAI клиент, auto-tracing |
| OpenAI Python SDK | >=1.0 | `response._headers` содержит HTTP заголовки |

## Текущее состояние

| Файл | Строки | Текущее значение |
|------|--------|-----------------|
| `generate.py:293-300` | Non-streaming LLM call | `response = await llm.chat.completions.create(...)` — response object доступен, headers не извлекаются |
| `generate.py:142-149` | Streaming LLM call | `stream = await llm.chat.completions.create(stream=True, ...)` — stream object, нет response headers |
| `generate.py:306-310` | Return dict | Возвращает `response`, `response_sent`, `latency_stages` — нет provider info |
| `rewrite.py:65-72` | Rewrite LLM call | `response = await llm.chat.completions.create(...)` — headers не извлекаются |
| `rewrite.py:93-100` | Return dict | Возвращает `messages`, `rewrite_count`, `latency_stages` — нет provider info |
| `state.py:13-39` | RAGState TypedDict | 20 полей, нет `llm_provider`, `llm_model_id`, `llm_ttft_ms` |
| `bot.py:39-66` | `_write_langfuse_scores` | 12 scores, нет provider/TTFT scores |
| `bot.py:269-278` | `update_current_trace` metadata | 4 поля: query_type, cache_hit, search_results_count, rerank_applied — нет provider |

## Исследование: Как получить provider metadata

### Вариант A: Response Headers от LiteLLM Proxy (РЕКОМЕНДУЕТСЯ)

LiteLLM Proxy добавляет заголовки в HTTP response:

    x-litellm-response-duration-ms: 2500     # полный latency через proxy
    x-litellm-overhead-duration-ms: 15       # overhead самого proxy
    x-litellm-model-id: <deployment-hash>    # ID модели в config
    x-litellm-attempted-retries: 1           # кол-во retry

OpenAI SDK хранит raw response headers в `response._headers` (httpx.Headers):

    response = await client.chat.completions.create(...)
    headers = response._headers  # httpx.Headers dict-like
    provider_duration = headers.get("x-litellm-response-duration-ms")

**Проблема со streaming:** При `stream=True` OpenAI SDK возвращает `AsyncStream`, а не `ChatCompletion`. У stream object НЕТ `_headers`. Headers доступны только через httpx response (не экспонируется SDK).

### Вариант B: LiteLLM response metadata (model field)

OpenAI SDK response object содержит поле `response.model` — LiteLLM заполняет его ФАКТИЧЕСКИМ именем модели (напр. `cerebras/gpt-oss-120b`), а не alias (`gpt-4o-mini`).

    response = await client.chat.completions.create(model="gpt-4o-mini", ...)
    actual_model = response.model  # "cerebras/gpt-oss-120b" или "groq/llama-3.1-70b"

Для streaming: последний chunk также содержит `chunk.model`.

### Вариант C: TTFT из streaming chunks

Для streaming path можно замерить время до первого chunk:

    t_start = time.monotonic()
    stream = await llm.chat.completions.create(stream=True, ...)
    async for chunk in stream:
        if ttft is None:
            ttft = (time.monotonic() - t_start) * 1000  # ms
        ...

### Решение: комбинация B + C

- **Provider/model:** `response.model` (non-streaming) и `chunk.model` (streaming) — ВСЕГДА доступно
- **TTFT:** замер `time.monotonic()` от начала create() до первого chunk (streaming) или до получения response (non-streaming)
- **Response headers:** извлечь из non-streaming `response._headers` для `x-litellm-model-id` (bonus, не критично)

## Шаги реализации

### Шаг 1: Добавить поля в RAGState (2 мин)

**Файл:** `telegram_bot/graph/state.py:13-39`

Добавить 3 новых поля в `RAGState` TypedDict:

    llm_provider_model: str          # Фактическая модель (из response.model)
    llm_ttft_ms: float               # Time to first token (ms)
    llm_response_duration_ms: float  # Полный LLM response duration (ms)

Добавить в `make_initial_state()` (строки 42-69):

    "llm_provider_model": "",
    "llm_ttft_ms": 0.0,
    "llm_response_duration_ms": 0.0,

### Шаг 2: Извлечь provider metadata в generate_node — non-streaming path (5 мин)

**Файл:** `telegram_bot/graph/nodes/generate.py:291-300`

Текущий код:

    response = await llm.chat.completions.create(
        model=config.llm_model,
        messages=llm_messages,
        temperature=config.llm_temperature,
        max_tokens=config.generate_max_tokens,
        name="generate-answer",
    )
    answer = response.choices[0].message.content or ""

Новый код (после response = ...):

    answer = response.choices[0].message.content or ""
    actual_model = getattr(response, "model", config.llm_model) or config.llm_model

Сохранить `actual_model` и добавить в return dict (строка 306-310):

    return {
        "response": answer,
        "response_sent": response_sent,
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms,
        "llm_response_duration_ms": elapsed * 1000,
        "latency_stages": {..., "generate": elapsed},
    }

### Шаг 3: Извлечь TTFT в generate_node — streaming path (5 мин)

**Файл:** `telegram_bot/graph/nodes/generate.py:113-186` (`_generate_streaming`)

Добавить TTFT замер в `_generate_streaming`. Изменить сигнатуру:

    async def _generate_streaming(
        llm, config, llm_messages, message,
    ) -> tuple[str, str, float]:  # (answer, actual_model, ttft_ms)

В теле функции, перед циклом `async for chunk in stream:` (строка 152):

    ttft_ms = 0.0
    actual_model = config.llm_model

В цикле (строка 152-162), после `if delta and delta.content:`:

    if ttft_ms == 0.0:
        ttft_ms = (time.monotonic() - t_stream_start) * 1000
    if hasattr(chunk, "model") and chunk.model:
        actual_model = chunk.model

Добавить `t_stream_start = time.monotonic()` перед `async for` (после строки 149).

Обновить return:

    return accumulated, actual_model, ttft_ms

В `generate_node` (строка 247) обновить вызов:

    answer, actual_model, ttft_ms = await _generate_streaming(llm, config, llm_messages, message)

### Шаг 4: Обработать все fallback пути в generate_node (3 мин)

**Файл:** `telegram_bot/graph/nodes/generate.py`

В каждом except-блоке (строки 249-279, 280-290):
- При `StreamingPartialDeliveryError` fallback к non-streaming: извлечь `response.model`
- При Exception fallback: извлечь `response.model` из non-streaming response
- При полном failure (строка 301-303): `actual_model = "fallback"`, `ttft_ms = 0.0`

Добавить переменные `actual_model = config.llm_model` и `ttft_ms = 0.0` в начало try-блока (строка 241).

### Шаг 5: Извлечь provider metadata в rewrite_node (3 мин)

**Файл:** `telegram_bot/graph/nodes/rewrite.py:65-72`

После response = await ... (строка 72):

    actual_model = getattr(response, "model", config.rewrite_model) or config.rewrite_model

Добавить timing для TTFT (non-streaming — это просто elapsed):

    rewrite_ttft_ms = (time.perf_counter() - t0) * 1000

В return dict (строка 93-100) добавить:

    "rewrite_provider_model": actual_model,

НЕ перезаписывать `llm_provider_model` — это для generate. Rewrite metadata записать в `latency_stages` или отдельным полем trace metadata.

### Шаг 6: Добавить Langfuse scores для provider metadata (3 мин)

**Файл:** `telegram_bot/bot.py:39-66` (`_write_langfuse_scores`)

Добавить 2 новых score в словарь `scores`:

    "llm_ttft_ms": result.get("llm_ttft_ms", 0.0),
    "llm_response_duration_ms": result.get("llm_response_duration_ms", 0.0),

### Шаг 7: Добавить provider в trace metadata (2 мин)

**Файл:** `telegram_bot/bot.py:269-278` (`update_current_trace`)

Расширить metadata dict:

    metadata={
        "query_type": result.get("query_type", ""),
        "cache_hit": result.get("cache_hit", False),
        "search_results_count": result.get("search_results_count", 0),
        "rerank_applied": result.get("rerank_applied", False),
        "llm_provider_model": result.get("llm_provider_model", ""),
        "llm_ttft_ms": result.get("llm_ttft_ms", 0.0),
    },

### Шаг 8: Обновить observability.md scores таблицу (2 мин)

**Файл:** `.claude/rules/observability.md`

Добавить 2 новых score в таблицу "Langfuse Scores":

    | `llm_ttft_ms` | float | Time to first token (ms) |
    | `llm_response_duration_ms` | float | Full LLM response time (ms) |

Обновить счётчик: "14 scores" вместо "12 scores".

## Test Strategy

### Unit тесты

**Файл:** `tests/unit/graph/test_generate_node.py`

1. `test_generate_non_streaming_captures_provider_model` — проверить что `response.model` попадает в state
2. `test_generate_streaming_captures_ttft` — мок streaming chunks с задержкой, проверить ttft_ms > 0
3. `test_generate_streaming_captures_model_from_chunk` — chunk.model записывается в llm_provider_model
4. `test_generate_fallback_sets_fallback_model` — при exception, llm_provider_model = "fallback"

Mock pattern (существующий в test_generate_node.py):

    mock_config, mock_client = _make_mock_config()
    mock_response = MagicMock()
    mock_response.model = "cerebras/gpt-oss-120b"  # добавить model attr
    mock_response.choices[0].message.content = "Ответ."

**Файл:** `tests/unit/graph/test_rewrite_node.py` (если есть) или новый тест

5. `test_rewrite_captures_provider_model` — response.model записывается

**Файл:** `tests/unit/test_bot_handlers.py`

6. `test_write_langfuse_scores_includes_ttft` — проверить что llm_ttft_ms записывается в scores

### Integration тесты

**Файл:** `tests/integration/test_graph_paths.py`

7. Обновить `test_path_happy_retrieve_rerank_generate` — проверить что result содержит `llm_provider_model` != ""

## Acceptance Criteria

| # | Критерий | Метрика |
|---|---------|---------|
| 1 | `llm_provider_model` записывается в trace metadata | Langfuse UI: metadata содержит "cerebras/gpt-oss-120b" или аналог |
| 2 | `llm_ttft_ms` score записывается для каждого LLM call | Langfuse UI: score `llm_ttft_ms` > 0 для всех traces с generate |
| 3 | `llm_response_duration_ms` score записывается | Langfuse UI: score `llm_response_duration_ms` > 0 |
| 4 | Streaming path корректно извлекает model из chunks | Unit test проходит |
| 5 | Non-streaming path извлекает model из response | Unit test проходит |
| 6 | Fallback path не ломает pipeline | `llm_provider_model = "fallback"` при ошибке |
| 7 | Отчёт: какой provider вызывает tail latency | Langfuse UI фильтр по metadata `llm_provider_model` → группировка по latency |

## Диагностический отчёт (после деплоя)

После накопления ~50 traces, выполнить Langfuse API запрос:

    GET /api/public/traces?tags=telegram&limit=100

Группировка по `metadata.llm_provider_model`:
- p50/p95 `llm_ttft_ms` per provider
- Процент fallback traces
- Корреляция tail latency с конкретным provider

## Рассмотреть (out of scope, future)

- **reasoning_effort** для reasoning-моделей (gpt-oss-120b) — может снизить latency
- **Split models:** быстрая модель для rewrite (Groq), сильная для generate (Cerebras)
- **stream_timeout** в LiteLLM config — ограничить TTFT на уровне proxy
- **LiteLLM Prometheus metrics** (`litellm_llm_api_time_to_first_token_metric`) — для dashboards

## Effort Estimate

**Size:** S (Small)
**Время:** ~1.5 часа

| Шаг | Время |
|-----|-------|
| State + generate_node non-streaming | 10 мин |
| generate_node streaming + TTFT | 15 мин |
| Fallback paths | 10 мин |
| rewrite_node | 5 мин |
| bot.py scores + metadata | 5 мин |
| Tests (7 тестов) | 30 мин |
| Docs update | 5 мин |
| Smoke test + verify in Langfuse | 10 мин |
