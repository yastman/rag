# Contingency A/B: reasoning_effort + Split Models — Implementation Plan

**Issue:** #102 — perf: contingency — A/B benchmark, reasoning_effort, split models
**Tracking:** #97 | Parent: #58
**Trigger:** Только если Gate 1 (#101) fails (p90 всё ещё > 8s)
**Goal:** Снизить latency генерации через: A/B benchmark proxy vs direct, reasoning_effort=low для rewrite, split models (лёгкая модель для rewrite + тяжёлая для generate)

## Current State

### LLM Routing (LiteLLM config)
- Primary: `cerebras/gpt-oss-120b` (reasoning model, merge_reasoning_content)
- Fallback chain: `gpt-oss-120b` → `zai-glm-4.7` → `groq/llama-3.1-70b` → `openai/gpt-4o-mini`
- Все вызовы проходят через LiteLLM proxy (:4000)

### GraphConfig (config.py:14-24)
- `llm_model` = `gpt-4o-mini` (env: `LLM_MODEL`) — для generate
- `rewrite_model` = `gpt-4o-mini` (env: `REWRITE_MODEL`, fallback: `LLM_MODEL`) — уже поддержан отдельный
- `rewrite_max_tokens` = 64 (env: `REWRITE_MAX_TOKENS`)
- `generate_max_tokens` = 2048 (env: `GENERATE_MAX_TOKENS`)

### generate_node (generate.py:189-310)
- Использует `config.llm_model` для всех LLM вызовов (строки 143, 256, 283, 293)
- Streaming и non-streaming paths
- Не передаёт `reasoning_effort` — только `model`, `temperature`, `max_tokens`

### rewrite_node (rewrite.py:30-100)
- Использует `config.rewrite_model` (строка 66)
- `temperature=0.3`, `max_tokens=config.rewrite_max_tokens` (64)
- Не передаёт `reasoning_effort`

## MCP Research Findings

### reasoning_effort
- OpenAI API параметр: `reasoning_effort` = `"low"` | `"medium"` | `"high"`
- Работает для reasoning models (o1, o3-mini, GPT-5, gpt-oss-120b)
- `low` — быстрее, дешевле, но менее детальное reasoning
- LiteLLM поддерживает `reasoning_effort` в `litellm_params` как default:

      - model_name: gpt-4o-mini-low
        litellm_params:
          model: cerebras/gpt-oss-120b
          reasoning_effort: low

- Также можно передать per-request через `extra_body` или прямо в `create()` kwargs
- **Bug в LiteLLM v1.75.5:** `reasoning_effort` не поддерживался для GPT-5 (issue #13699, fixed)
- Текущая версия v1.81.3 — исправлено

### Split Models via LiteLLM
- LiteLLM позволяет определить несколько model_name aliases
- `REWRITE_MODEL` уже поддержан в GraphConfig (строка 23, 70)
- Можно задать `REWRITE_MODEL=gpt-4o-mini-fast` и добавить лёгкую модель в config.yaml
- Auto-Router (semantic-based) — overkill, не нужен для 2 фиксированных путей

### Direct vs Proxy
- LiteLLM proxy добавляет overhead: ~20-50ms p50, ~100ms p99 (benchmark docs)
- Direct: бот вызывает Cerebras API напрямую через OpenAI SDK
- Proxy: бот → LiteLLM → Cerebras (доп. hop + JSON parsing + logging)
- Для измерения: нужен A/B с Langfuse latency spans

## Options

### Option A: reasoning_effort=low для rewrite

**Гипотеза:** rewrite не требует глубокого reasoning — `low` effort ускорит на 30-50%

**Изменения:**

#### Шаг A1: Добавить REWRITE_REASONING_EFFORT в GraphConfig (2 мин)

Файл: `telegram_bot/graph/config.py`
- Строка 24: добавить поле `rewrite_reasoning_effort: str = "medium"`
- Строка 71: добавить чтение env:

      rewrite_reasoning_effort=os.getenv("REWRITE_REASONING_EFFORT", "medium"),

#### Шаг A2: Передать reasoning_effort в rewrite_node (2 мин)

Файл: `telegram_bot/graph/nodes/rewrite.py`
- Строки 65-71: добавить `extra_body` с reasoning_effort в create():

      response = await llm.chat.completions.create(
          model=config.rewrite_model,
          messages=[{"role": "user", "content": prompt}],
          temperature=0.3,
          max_tokens=config.rewrite_max_tokens,
          extra_body={"reasoning_effort": config.rewrite_reasoning_effort},
          name="rewrite-query",
      )

#### Шаг A3: Добавить env в docker-compose.dev.yml (1 мин)

Файл: `docker-compose.dev.yml`
- Строка ~550 (bot service environment): добавить:

      REWRITE_REASONING_EFFORT: "${REWRITE_REASONING_EFFORT:-low}"

#### Шаг A4: Unit test (3 мин)

Файл: `tests/unit/graph/test_rewrite_node.py`
- Добавить тест `test_rewrite_passes_reasoning_effort`: mock LLM, проверить что `extra_body` содержит `reasoning_effort`

### Option B: Split Models (лёгкая для rewrite)

**Гипотеза:** лёгкая модель (zai-glm-4.7 или groq/llama-3.1-70b) быстрее для rewrite

**Изменения:**

#### Шаг B1: Добавить лёгкую модель в LiteLLM config (2 мин)

Файл: `docker/litellm/config.yaml`
- После строки 34, добавить:

      # Lightweight model for rewrite (fast, no reasoning overhead)
      - model_name: gpt-4o-mini-fast
        litellm_params:
          model: openai/zai-glm-4.7
          api_base: https://api.cerebras.ai/v1
          api_key: os.environ/CEREBRAS_API_KEY
          max_tokens: 200

#### Шаг B2: Задать REWRITE_MODEL в docker-compose.dev.yml (1 мин)

Файл: `docker-compose.dev.yml`
- Строка ~550 (bot service environment): изменить/добавить:

      REWRITE_MODEL: "${REWRITE_MODEL:-gpt-4o-mini-fast}"

- **Код не нужно менять** — GraphConfig уже читает `REWRITE_MODEL` (config.py:70)
- rewrite_node уже использует `config.rewrite_model` (rewrite.py:66)

#### Шаг B3: Добавить fallback для fast модели (1 мин)

Файл: `docker/litellm/config.yaml`
- В `router_settings.fallbacks` (строка 58): добавить:

      - gpt-4o-mini-fast: [gpt-4o-mini-fallback]

#### Шаг B4: Smoke test (2 мин)

    docker compose -f docker-compose.dev.yml restart litellm
    curl -s http://localhost:4000/v1/chat/completions \
      -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
      -H "Content-Type: application/json" \
      -d '{"model":"gpt-4o-mini-fast","messages":[{"role":"user","content":"test"}]}'

### Option C: A/B Proxy vs Direct (benchmarking)

**Гипотеза:** LiteLLM proxy добавляет measurable latency (20-100ms)

**Изменения:**

#### Шаг C1: Добавить GENERATE_LLM_BASE_URL в GraphConfig (2 мин)

Файл: `telegram_bot/graph/config.py`
- Строка 17: добавить `generate_llm_base_url: str = "http://litellm:4000"`
- Строка 65: добавить:

      generate_llm_base_url=os.getenv("GENERATE_LLM_BASE_URL", os.getenv("LLM_BASE_URL", "http://litellm:4000")),

#### Шаг C2: Создать отдельный LLM client для generate (3 мин)

Файл: `telegram_bot/graph/config.py`
- После `create_llm()` (строка 87): добавить метод:

      def create_generate_llm(self) -> Any:
          from langfuse.openai import AsyncOpenAI
          return AsyncOpenAI(
              api_key=self.llm_api_key or "no-key",
              base_url=self.generate_llm_base_url,
              max_retries=2,
              timeout=60.0,
          )

#### Шаг C3: Использовать в generate_node (2 мин)

Файл: `telegram_bot/graph/nodes/generate.py`
- Строка 242: заменить `config.create_llm()` на `config.create_generate_llm()`
- Это позволит задать direct URL: `GENERATE_LLM_BASE_URL=https://api.cerebras.ai/v1`

#### Шаг C4: Benchmark скрипт (5 мин)

Файл: `scripts/benchmark_proxy_vs_direct.py` (новый)
- 10 запросов через proxy, 10 напрямую
- Замер p50/p90/p99 TTFT и total latency
- Вывод таблицы сравнения

## Recommended Execution Order

1. **Option A** (reasoning_effort) — самый быстрый, минимум изменений, сразу измеримый эффект
2. **Option B** (split models) — если A не даёт достаточного улучшения
3. **Option C** (proxy vs direct) — benchmark для принятия решения о архитектуре

Options A и B можно комбинировать: лёгкая модель + low reasoning для rewrite.

## Test Strategy

| Test | Command | Expected |
|------|---------|----------|
| Unit: reasoning_effort passed | `uv run pytest tests/unit/graph/test_rewrite_node.py -k reasoning_effort -v` | extra_body contains reasoning_effort |
| Unit: split model config | `uv run pytest tests/unit/graph/test_config.py -v` | rewrite_model != llm_model when env set |
| Integration: graph paths | `uv run pytest tests/integration/test_graph_paths.py -v` | All 6 paths pass |
| Smoke: LiteLLM fast model | curl to localhost:4000 with `gpt-4o-mini-fast` | 200 OK |
| E2E: latency comparison | `make validate-traces-fast` | p90 generate < baseline |

## Acceptance Criteria

1. `REWRITE_REASONING_EFFORT=low` снижает latency rewrite_node на >= 20%
2. `REWRITE_MODEL=gpt-4o-mini-fast` позволяет использовать лёгкую модель без code changes
3. Langfuse traces показывают отдельные модели для rewrite vs generate
4. Все существующие тесты проходят (`make test-unit`)
5. Fallback chain работает для новой модели

## Effort Estimate

| Option | Effort | Risk |
|--------|--------|------|
| A: reasoning_effort | 10 мин | Low — параметр уже поддержан LiteLLM v1.81 |
| B: Split models | 5 мин | Low — GraphConfig.rewrite_model уже есть |
| C: Proxy vs Direct | 15 мин | Medium — нужен benchmark, может потерять fallbacks |
| **Total (A+B)** | **15 мин** | **Low** |
| **Total (A+B+C)** | **30 мин** | **Medium** |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| reasoning_effort не поддержан cerebras/gpt-oss-120b | Проверить через curl; fallback — ignore параметр |
| Лёгкая модель даёт плохие rewrites | A/B сравнение качества rewrite через Langfuse |
| Direct API теряет fallback chain | Оставить proxy для generate, direct только для benchmark |
| LiteLLM v1.81.3 bug с reasoning_effort | Проверить перед deploy; fallback — обновить LiteLLM |
