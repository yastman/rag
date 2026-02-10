# #120 Umbrella: P0 Fixes → Local Validation → P1/P2

**Goal:** Закрыть все дефекты из аудита PR #111, провести локальную валидацию бота, собрать Langfuse трейсы, выполнить глубокий аудит Qdrant/Redis/BGE-M3 latency и принять Go/No-Go по ONNX migration spike.

**Architecture:** 7 фаз: подготовка → P0 фиксы (4 issues) → gate → docker rebuild + traces → deep audit (Qdrant/Redis/BGE/ONNX) → P1/P2 фиксы (4 issues) → final gate. Исполнение: 1 issue = 1 branch = 1 PR (без прямых коммитов в `main`). TDD для #114 и #117.

**Tech Stack:** pytest, ruff, mypy, monkeypatch, Docker Compose, Langfuse SDK, Qdrant Python SDK, RedisVL SDK, Sentence-Transformers/Optimum + ONNX Runtime (ONNX spike), gh CLI, Context7, Exa MCP

---

## Phase 0: Подготовка

### Task 0.1: Обновить #120 checklist

**Files:**
- N/A (GitHub API only)

**Step 1: Добавить checklist подзадач в #120**

```bash
gh issue edit 120 --body "$(gh issue view 120 --json body -q '.body')

## Execution Checklist

### P0 (blockers)
- [ ] #115 cross-test pollution (sys.modules)
- [ ] #112 test_bot_handlers (legacy API patch)
- [ ] #113 test_graph_paths (GraphConfig mocks)
- [ ] #114 streaming fallback duplicate response

### P0 Gate
- [ ] All P0 target tests green
- [ ] ruff check clean

### Local Validation
- [ ] docker-bot-up healthy
- [ ] Telegram smoke: /start, RAG, /stats
- [ ] Langfuse traces captured
- [ ] E2E dry run (scenario 1.1)
- [ ] Full E2E (25 scenarios)
- [ ] Go/No-Go decision

### Deep Audit (Qdrant/Redis/BGE/ONNX)
- [ ] Trace-level latency breakdown documented (incl. `c2b95d86aa1f643b79016dd611c4691f`)
- [ ] BGE endpoint benchmark (dense/sparse/hybrid, p50/p95)
- [ ] Qdrant benchmark (query_points RRF, p50/p95)
- [ ] Redis benchmark + eviction/hit-rate snapshot
- [ ] ONNX spike decision (dense-only vs full BGE-M3 tri-vector parity)

### P1/P2
- [ ] #116 sync rewrite_max_tokens
- [ ] #118 test_redis_cache legacy imports
- [ ] #117 qdrant error vs no-results
- [ ] #119 mypy duplicate module

### Final Gate
- [ ] Full lint/type/test suite green
- [ ] Merged PRs listed
- [ ] Trace IDs documented
"
```

Expected: #120 body обновлён, checklist виден в UI.

---

### Task 0.2: SDK-first правило (Context7 + Exa)

**Step 1: Зафиксировать policy в #120 и PR descriptions**

Принцип:
- Использовать официальные SDK, не raw HTTP, где есть стабильный клиент.
- Для tracing/LLM вызовов: `langfuse-python` (`/langfuse/langfuse-python` в Context7), в т.ч. `from langfuse.openai import AsyncOpenAI`, `@observe`, `update_current_trace`, `score_current_trace`.
- Для векторного поиска: `qdrant-client` (`/qdrant/qdrant-client` в Context7), в т.ч. `AsyncQdrantClient` + `query_points` (`prefetch` dense+sparse + fusion `RRF` в одном вызове).
- Для semantic cache: `redis-vl-python` (`/redis/redis-vl-python` в Context7), в т.ч. `SemanticCache(redis_url=...)`, TTL, tags/filters, threshold tuning (`CacheThresholdOptimizer`).
- Для ONNX spike: `sentence-transformers` (`/huggingface/sentence-transformers`) + `optimum` + `onnxruntime` (официальные гайды оптимизации/quantization), без ad-hoc кастомных рантаймов на первом шаге.

**Step 1.1: Источники истины для review**

- Primary only: official docs/model cards (`qdrant.tech`, `redis.io`, `langfuse.com`, `onnxruntime.ai`, `huggingface.co/BAAI/bge-m3`).
- Context7 используется как основной источник API-контракта.
- Exa MCP используется для проверки свежести и cross-check ссылок/изменений в 2026.
- Блоги/Medium/DEV допустимы только как гипотеза, но не как база для архитектурного решения.

**Step 2: Проверять в code review каждого PR**

Acceptance:
- Нет новых `requests/httpx` вызовов к Langfuse/Qdrant там, где есть SDK-эквивалент.
- В PR описано, какой SDK использован и почему.
- Для retrieval path не допускаются два отдельных сетевых вызова dense+sparse там, где доступен единый hybrid encode/query.
- В PR есть ссылки на минимум 1 официальный источник (через Context7/Exa).

---

## Phase 1: P0 Fixes (blockers)

### Task 1.1: #115 — Cross-test pollution (sys.modules["redisvl"])

**Files:**
- Edit: `tests/unit/test_redis_semantic_cache.py:1-18`
- Verify: `tests/unit/test_vectorizers.py`

**Step 1: Убрать cross-test pollution, сохранив изоляцию импорта**

В `tests/unit/test_redis_semantic_cache.py` использовать `sys.modules` mock только на время импорта `RedisSemanticCache`, затем сразу восстановить исходные модули.

Рабочий шаблон:

```python
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MOCKED_MODULES = [
    "redis", "redis.asyncio",
    "opentelemetry", "opentelemetry.trace",
    "redisvl", "redisvl.extensions.message_history",
    "redisvl.query.filter", "redisvl.utils.vectorize",
]
_saved = {name: sys.modules.get(name) for name in _MOCKED_MODULES}
for name in _MOCKED_MODULES:
    sys.modules[name] = MagicMock()

from src.cache.redis_semantic_cache import RedisSemanticCache

for name in _MOCKED_MODULES:
    if _saved[name] is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = _saved[name]

del _saved
```

Ключевой принцип: мок нужен только в момент импорта тестируемого модуля.

**Step 2: Run target tests**

```bash
uv run pytest tests/unit/test_redis_semantic_cache.py tests/unit/test_vectorizers.py -q
```

Expected: both green, no collection errors.

**Step 3: Lint**

```bash
uv run ruff check tests/unit/test_redis_semantic_cache.py --output-format=concise
```

Expected: clean.

**Step 4: Commit**

```bash
git add tests/unit/test_redis_semantic_cache.py
git commit -m "fix(tests): restore sys.modules after redisvl mock import

Mock modules only during RedisSemanticCache import, then immediately
restore. Prevents cross-test pollution in test_vectorizers.

Closes #115"
```

---

### Task 1.2: #112 — test_bot_handlers под новый Langfuse API

**Files:**
- Edit: `tests/unit/test_bot_handlers.py:241-305`
- Read: `telegram_bot/bot.py:226-274` (current handle_query contract)

The current `handle_query` (bot.py:226-274):
1. Calls `build_graph()` → `graph.ainvoke(state)`
2. Calls `get_client().update_current_trace(input=..., output=..., metadata=...)`
3. Calls `_write_langfuse_scores(lf, result)`
4. NO `create_langfuse_handler` — removed

Two broken tests:
- `test_handle_query_passes_langfuse_handler` (line 241): patches `telegram_bot.bot.create_langfuse_handler`
- `test_handle_query_no_langfuse` (line 275): patches `telegram_bot.bot.create_langfuse_handler`

**Step 1: Replace test_handle_query_passes_langfuse_handler**

Replace the test at lines 241-272 with:

```python
    @pytest.mark.asyncio
    async def test_handle_query_writes_langfuse_trace(self, mock_config):
        """Test that handle_query updates Langfuse trace and writes scores."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"response": "ok", "query_type": "GENERAL", "latency_stages": {}}
        )
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot._write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = MagicMock()
            message.text = "test"
            message.from_user = MagicMock()
            message.from_user.id = 12345
            message.chat = MagicMock()
            message.chat.id = 12345
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_query(message)

            mock_lf.update_current_trace.assert_called_once()
            mock_write_scores.assert_called_once_with(mock_lf, mock_graph.ainvoke.return_value)
```

**Step 2: Replace test_handle_query_no_langfuse**

Replace lines 274-305 with:

```python
    @pytest.mark.asyncio
    async def test_handle_query_passes_state_to_graph(self, mock_config):
        """Test that handle_query passes correct initial state to graph."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"response": "ok", "query_type": "GENERAL", "latency_stages": {}}
        )

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot._write_langfuse_scores"),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = MagicMock()
            message.text = "квартиры"
            message.from_user = MagicMock()
            message.from_user.id = 12345
            message.chat = MagicMock()
            message.chat.id = 12345
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_query(message)

            state_arg = mock_graph.ainvoke.call_args[0][0]
            assert state_arg["user_id"] == 12345
            assert "квартиры" in str(state_arg["messages"])
```

**Step 3: Run tests**

```bash
uv run pytest tests/unit/test_bot_handlers.py -q
```

Expected: all green, no `create_langfuse_handler` references.

**Step 4: Verify no leftover references**

```bash
grep -r "create_langfuse_handler" tests/
```

Expected: no output.

**Step 5: Lint + commit**

```bash
uv run ruff check tests/unit/test_bot_handlers.py --output-format=concise
git add tests/unit/test_bot_handlers.py
git commit -m "fix(tests): update bot handler tests to current Langfuse API

Replace create_langfuse_handler patches with get_client/update_current_trace
and _write_langfuse_scores mocks matching current bot.py contract.

Closes #112"
```

---

### Task 1.3: #113 — test_graph_paths (GraphConfig mocks)

**Files:**
- Edit: `tests/integration/test_graph_paths.py:125-135`

The problem: `_make_mock_graph_config()` returns a `MagicMock` without typed fields. `grade_node` (grade.py:48-51) calls `GraphConfig.from_env()` and reads `config.skip_rerank_threshold` — but the test patches `GraphConfig.from_env` to return this mock, so it gets `MagicMock()` instead of `float`.

**Step 1: Add missing typed fields to _make_mock_graph_config**

Replace `_make_mock_graph_config` function (lines 125-135):

```python
def _make_mock_graph_config(llm_mock: MagicMock) -> MagicMock:
    """Create a mock GraphConfig with all required typed fields."""
    gc = MagicMock()
    gc.domain = "недвижимость"
    gc.llm_model = "test-model"
    gc.llm_temperature = 0.7
    gc.llm_max_tokens = 4096
    gc.generate_max_tokens = 2048
    gc.rewrite_model = "test-model"
    gc.rewrite_max_tokens = 64
    gc.skip_rerank_threshold = 0.85
    gc.streaming_enabled = False
    gc.create_llm.return_value = llm_mock
    return gc
```

Changes: added `gc.generate_max_tokens = 2048`, `gc.skip_rerank_threshold = 0.85`, `gc.streaming_enabled = False`.

**Step 2: Run tests**

```bash
uv run pytest tests/integration/test_graph_paths.py -v
```

Expected: all 6 path tests green, no TypeError.

**Step 3: Lint + commit**

```bash
uv run ruff check tests/integration/test_graph_paths.py --output-format=concise
git add tests/integration/test_graph_paths.py
git commit -m "fix(tests): add typed fields to GraphConfig mock in path tests

Add skip_rerank_threshold, generate_max_tokens, streaming_enabled to
_make_mock_graph_config. Prevents TypeError in grade_node comparisons.

Closes #113"
```

---

### Task 1.4: #114 — Streaming fallback duplicate response

**Files:**
- Edit: `telegram_bot/graph/nodes/generate.py:221-261`
- Read: `telegram_bot/graph/nodes/respond.py` (already handles `response_sent`)
- Edit: `tests/unit/graph/test_generate_node.py`

**Analysis of the bug:**

In `generate.py:221-241`:
```python
response_sent = False
try:
    if message is not None and config.streaming_enabled:
        try:
            answer = await _generate_streaming(...)
            response_sent = True        # ← only set on SUCCESS
        except Exception:
            # Falls back to non-streaming LLM call
            response = await llm.chat.completions.create(...)
            answer = response.choices[0].message.content or ""
            # response_sent stays False → respond_node will send again!
```

The bug: if `_generate_streaming` sent partial chunks (placeholder + some edits) but then raised, `response_sent` stays `False`. The fallback generates a new answer, and `respond_node` sends it as a NEW message. User sees: partial streamed text + full new message = duplicate.

**Important correction:** нельзя просто выставлять `response_sent=True` на любой streaming-error. Если стрим упал до первого user-visible chunk, пользователь может остаться только с placeholder.

**Step 1: Add/adjust tests in existing suite**

В `tests/unit/graph/test_generate_node.py` добавить 2 явных кейса:
- `stream_error_before_visible_output` -> `response_sent=False` (final send делает `respond_node`);
- `stream_error_after_visible_output` -> fallback редактирует уже отправленное сообщение и `response_sent=True`.

**Step 2: Run tests in red state**

```bash
uv run pytest tests/unit/graph/test_generate_node.py -k "streaming_fallback or stream_error" -v
```

Expected: минимум один тест падает до фикса.

**Step 3: Fix generate_node streaming fallback safely**

В `telegram_bot/graph/nodes/generate.py`:
- Ввести явный сигнал частичной пользовательской доставки из `_generate_streaming` (например custom exception `StreamingPartialDeliveryError`, содержащий ссылку на `sent_msg`).
- В `generate_node` на fallback:
  - если partial delivery уже была -> отдать fallback через `edit_text` того же сообщения и поставить `response_sent=True`;
  - если partial delivery не было -> оставить `response_sent=False`, чтобы `respond_node` отправил ответ.
- Не ломать текущий контракт non-streaming пути.

**Step 4: Run tests to green**

```bash
uv run pytest tests/unit/graph/test_generate_node.py -k "streaming_fallback or stream_error" -v
```

Expected: новые/обновлённые кейсы зелёные.

**Step 5: Run graph integration tests (regression)**

```bash
uv run pytest tests/integration/test_graph_paths.py -v
uv run pytest tests/unit/graph/ -q
```

Expected: all green (path tests use `streaming_enabled=False`).

**Step 6: Lint + commit**

```bash
uv run ruff check telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py --output-format=concise
git add telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py
git commit -m "fix(graph): prevent duplicate response on streaming fallback

Track partial streaming delivery and route fallback safely:
edit existing message when partial output was visible, otherwise let
respond_node deliver final answer.

Closes #114"
```

---

## Phase 2: P0 Gate

### Task 2.1: Verify all P0 fixes together

**Files:**
- N/A (verification only)

**Step 1: Run all target tests**

```bash
uv run pytest tests/unit/test_redis_semantic_cache.py tests/unit/test_vectorizers.py -q
uv run pytest tests/unit/test_bot_handlers.py -q
uv run pytest tests/integration/test_graph_paths.py -q
uv run pytest tests/unit/graph -q
```

Expected: all green.

**Step 2: Run lint**

```bash
uv run ruff check src telegram_bot tests services --output-format=concise
```

Expected: clean.

**Step 3: STOP if any red. Fix before proceeding.**

---

## Phase 3: Local Validation (rebuild + traces)

> Full steps in `docs/plans/2026-02-10-local-validation-design.md`.
> This phase is largely manual (Telegram interaction + Langfuse UI).

### Task 3.1: Docker bot rebuild

**Step 1: Start bot stack**

```bash
make docker-bot-up
```

**Step 2: Wait for healthy**

```bash
docker compose -f docker-compose.dev.yml ps
```

Expected: postgres, redis, qdrant, bge-m3, litellm, bot all healthy/running.

**Step 3: Check bot logs**

```bash
docker logs --tail 30 dev-bot
```

Expected: `Preflight checks passed`, no errors.

### Task 3.2: Telegram smoke test (manual)

Send to bot in Telegram:
1. `/start` → expect greeting with domain
2. `Какие квартиры в Несебре?` → expect streaming response (text appears in chunks)
3. `/stats` → expect cache stats

### Task 3.3: Langfuse traces (manual)

Open Langfuse UI. Find traces from smoke test. Check:
- Node spans: node-classify, node-cache-check, node-retrieve, node-grade, node-generate, node-respond
- Scores: latency_total_ms, semantic_cache_hit, search_results_count, rerank_applied
- `response_sent` проверяется как поле state/output в trace metadata/span (не как score, если отдельно не добавлено)

Record trace IDs.

### Task 3.4: E2E dry run

```bash
uv run python scripts/e2e/runner.py --scenario 1.1
```

Expected: PASS.

### Task 3.5: Full E2E (25 scenarios)

```bash
make e2e-test
```

Expected: pass rate >= 80%.

### Task 3.6: Go/No-Go

Compare with problem trace `c2b95d86aa1f643b79016dd611c4691f` from #105. Post results to #120.

---

## Phase 3.7: Deep Audit (Qdrant + Redis + BGE-M3 + ONNX)

### Task 3.7.1: Trace-first baseline (Langfuse SDK)

**Step 1: Зафиксировать baseline по проблемному trace**

Снять из trace:
- total latency
- суммарный вклад `node-retrieve`, `bge-m3-dense-embed`, `bge-m3-sparse-embed`, `qdrant-hybrid-search-rrf`
- число rewrite-итераций

Expected: подтверждено, где compute bottleneck (BGE/LLM/Qdrant/looping).

**Step 2: Нормализовать методологию latency-анализа**

- E2E latency считать по wall-clock trace duration.
- Не суммировать вложенные/параллельные spans как total (иначе double-count).
- Для каждой стадии фиксировать: count, p50, p95, max, error-rate.

### Task 3.7.2: BGE-M3 bottleneck isolation

**Step 1: Benchmark `/encode/dense`, `/encode/sparse`, `/encode/hybrid` (p50/p95)**

Expected:
- `hybrid` не хуже суммы `dense+sparse` (обычно существенно лучше двух последовательных вызовов).
- зафиксировать tail latency при concurrency 1/2/4/8.
- Если `hybrid` стабильно быстрее, зафиксировать как target API path для production (dense+sparse в один inference pass).

**Step 2: Проверить runtime-конфиг BGE**

Проверить:
- `workers`, `limit-concurrency`
- `OMP_NUM_THREADS`, `MKL_NUM_THREADS`
- модельные лимиты (`max_length`, batch)
- фактический `tokenizer_max_length` и среднюю длину query (чтобы не переплачивать за длинный контекст)

Expected: задокументирован план тюнинга без регресса стабильности.

**Step 3: Подготовить ONNX baseline для fair сравнения**

- Один и тот же набор запросов, одинаковые batch/concurrency.
- Сравнить PyTorch vs ONNX Runtime: p50/p95/CPU utilization/качество retrieval.
- До ONNX-спайка сначала закрыть low-hanging fruit: единый `/encode/hybrid` path.

### Task 3.7.3: Qdrant deep check (SDK-only)

**Step 1: Benchmark `query_points` RRF (dense+sparse prefetch в одном query)**

Expected: p50/p95 и доля в E2E latency.

**Step 2: Проверить collection config**

Проверить:
- `quantization_config`
- `optimizer_status`
- `segments_count`, `indexed_vectors_count`
- наличие payload indexes для фильтров
- что `prefetch.limit >= main limit + offset` (во избежание пустых ответов)

Expected: решение по quantization/optimizer для текущего датасета.

### Task 3.7.4: Redis deep check

**Step 1: Snapshot метрик Redis**

Проверить:
- `keyspace_hits/misses`
- `evicted_keys`
- `used_memory/maxmemory`
- policy (`volatile-lfu`)

**Step 2: Micro-benchmark GET/SET**

Expected: Redis latency << BGE/LLM latency; если нет — отдельный issue на Redis.

**Step 3: Semantic cache threshold tuning (RedisVL)**

- Прогнать `CacheThresholdOptimizer` на отложенном наборе QA.
- Зафиксировать рекомендованный `distance_threshold` + TTL для прода.
- Снять trade-off: hit-rate vs false-positive cache hits.

### Task 3.7.5: ONNX migration spike (decision gate)

**Scope:**
- Spike only for dense embedding path first (не сразу весь tri-vector pipeline).
- Проверить качество/совместимость и throughput.
- ONNX запускать только после фикса single-pass hybrid path, иначе оценка будет искажена двумя отдельными вызовами.

**Decision rule:**
- Если ONNX даёт >=20-30% выигрыш на dense path без заметной quality деградации (Recall@k/NDCG@k), открыть implementation issue.
- Если нет стабильного выигрыша/паритета для BGE-M3 tri-vector, оставить PyTorch для sparse/colbert и использовать гибридную схему.

Deliverable:
- комментарий в #120 с таблицей baseline vs candidate (p50/p95/quality/cost CPU).
- отдельный issue (если Go) со ссылкой на таблицу и критерии приёмки.

---

## Phase 4: P1/P2 Fixes

### Task 4.1: #116 — Sync rewrite_max_tokens default

**Files:**
- Edit: `telegram_bot/graph/config.py:70`

**Step 1: Fix the mismatch**

In `telegram_bot/graph/config.py`, line 70:

```python
# Before:
            rewrite_max_tokens=int(os.getenv("REWRITE_MAX_TOKENS", "200")),
# After:
            rewrite_max_tokens=int(os.getenv("REWRITE_MAX_TOKENS", "64")),
```

**Step 2: Run config tests**

```bash
uv run pytest tests/ -k "config" -q
```

Expected: green.

**Step 3: Verify consistency**

```bash
grep -n "rewrite_max_tokens" telegram_bot/graph/config.py
```

Expected: line 24 shows `rewrite_max_tokens: int = 64`, line 70 shows fallback `"64"`.

**Step 4: Lint + commit**

```bash
uv run ruff check telegram_bot/graph/config.py --output-format=concise
git add telegram_bot/graph/config.py
git commit -m "fix(config): sync rewrite_max_tokens env fallback to 64

Dataclass default is 64, but from_env fallback was '200'. Now consistent.

Closes #116"
```

---

### Task 4.2: #118 — test_redis_cache legacy imports

**Files:**
- Edit: `tests/integration/test_redis_cache.py`

**Analysis:** This file (163 lines) is a standalone script (`__name__ == "__main__"`), not a pytest test module. It uses `sys.path.insert` to import `src.cache.redis_semantic_cache` directly. It requires a live Redis connection. It should be marked as legacy and excluded from pytest collection.

**Step 1: Add legacy_api marker and skip**

Add at the top of `tests/integration/test_redis_cache.py` (after the docstring, before imports):

Replace lines 1-13:

```python
#!/usr/bin/env python3
"""Test Redis semantic cache connectivity and basic operations.

Legacy integration test — requires live Redis. Run manually:
    python tests/integration/test_redis_cache.py

Excluded from CI via @pytest.mark.legacy_api marker.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Mark entire module as legacy (skipped in CI: -m "not legacy_api")
pytestmark = pytest.mark.legacy_api

# Add src to path for legacy import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from cache.redis_semantic_cache import RedisSemanticCache  # noqa: E402
```

**Step 2: Verify collection works**

```bash
uv run pytest tests/integration/test_redis_cache.py --collect-only
```

Expected: collected (with legacy_api marker), no import error during collection.

**Step 3: Verify it's excluded in CI mode**

```bash
uv run pytest tests/integration/test_redis_cache.py -m "not legacy_api" --collect-only || true
```

Expected: 0 tests collected.

**Step 4: Lint + commit**

```bash
uv run ruff check tests/integration/test_redis_cache.py --output-format=concise
git add tests/integration/test_redis_cache.py
git commit -m "fix(tests): mark test_redis_cache as legacy_api

Add pytestmark so CI skips it (-m 'not legacy_api'). Fix sys.path
to use correct relative path.

Closes #118"
```

---

### Task 4.3: #117 — Qdrant error vs no-results (без shared mutable state)

**Files:**
- Edit: `telegram_bot/services/qdrant.py`
- Edit: `telegram_bot/graph/nodes/retrieve.py`
- Edit: `telegram_bot/graph/state.py`
- Create: `tests/unit/test_qdrant_error_signal.py`

**Step 1: Write failing tests (service + retrieve node)**

Покрыть два сценария:
- backend exception -> `backend_error=True` + `error_type` заполнен;
- genuine empty results -> `backend_error=False`.

Примечание: следуем SDK-first (Context7): используем `AsyncQdrantClient` и его вызовы/исключения, без raw HTTP.

**Step 2: Run tests in red state**

```bash
uv run pytest tests/unit/test_qdrant_error_signal.py -v
```

Expected: FAIL (сигнал backend_error ещё не реализован).

**Step 3: Add per-call meta signal**

В `telegram_bot/services/qdrant.py`:
- Добавить opt-in API: `hybrid_search_rrf(..., return_meta: bool = False)`.
- Если `return_meta=False`: сохранить текущий контракт `list[dict]`.
- Если `return_meta=True`: возвращать `(results, meta)` где:
  - `backend_error: bool`
  - `error_type: str | None`
  - `error_message: str | None`

В `telegram_bot/graph/nodes/retrieve.py`:
- Вызывать `hybrid_search_rrf(..., return_meta=True)`;
- сохранять в state: `retrieval_backend_error`, `retrieval_error_type`.

В `telegram_bot/graph/state.py`:
- Добавить новые поля в `RAGState`.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/test_qdrant_error_signal.py -v
uv run pytest tests/unit/test_qdrant_service.py tests/unit/graph/test_retrieve_node.py -q
```

Expected: green, контракт для текущих call-sites не ломается.

**Step 5: Lint + commit**

```bash
uv run ruff check telegram_bot/services/qdrant.py telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/state.py tests/unit/test_qdrant_error_signal.py --output-format=concise
git add telegram_bot/services/qdrant.py telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/state.py tests/unit/test_qdrant_error_signal.py
git commit -m "feat(qdrant): add per-call backend_error meta for retrieval observability

Differentiate backend failures from genuine empty search results while
preserving graceful degradation and existing default API contract.

Closes #117"
```

---

### Task 4.4: #119 — mypy duplicate module name

**Files:**
- Edit: `pyproject.toml` (точечно, только если реально нужно)

**Problem:** `services/user-base/main.py` and `services/bm42/main.py` both resolve as module `main` — mypy duplicate-module-name error.

**Step 1: Reproduce with CI-aligned commands**

```bash
uv run mypy src telegram_bot --ignore-missing-imports
```

Expected: если duplicate не воспроизводится в этом контуре, config не менять.

**Step 2: Reproduce service-only issue отдельно**

```bash
uv run mypy services --ignore-missing-imports
```

Expected: duplicate error воспроизводится только для standalone services.

**Step 3: Fix минимально-инвазивно**

Предпочтительно:
- Для service-only typecheck использовать `--explicit-package-bases`, либо
- добавить отдельную команду/target для `services/*`, не затрагивая основной CI path.

Избегать широкого global `exclude`, если проблема не влияет на `src telegram_bot`.

**Step 4: Verify**

```bash
uv run mypy src telegram_bot --ignore-missing-imports
uv run mypy services --ignore-missing-imports --explicit-package-bases
```

Expected: нет duplicate-module ошибок в обоих контурах.

**Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "fix(mypy): resolve duplicate module names in standalone services

Align mypy configuration/commands so standalone service entrypoints
do not conflict while preserving main CI typecheck scope.

Closes #119"
```

---

## Phase 5: Final Gate

### Task 5.1: Full verification suite

**Step 1: Lint + types**

```bash
uv run ruff check src telegram_bot tests services --output-format=concise
uv run mypy src telegram_bot --ignore-missing-imports
```

Expected: both clean.

**Step 2: All target tests**

```bash
uv run pytest tests/unit/test_redis_semantic_cache.py tests/unit/test_vectorizers.py -q
uv run pytest tests/unit/test_bot_handlers.py -q
uv run pytest tests/integration/test_graph_paths.py -q
uv run pytest tests/unit/graph -q
uv run pytest tests/unit/test_qdrant_error_signal.py -q
```

Expected: all green.

**Step 3: Full unit suite**

```bash
uv run pytest tests/unit/ -n auto -q
```

Expected: all green.

**Step 4: Post results to #120**

```bash
gh issue comment 120 --body "## Final Gate Results

### Merged Commits
- #115 cross-test pollution ✅
- #112 bot handler tests ✅
- #113 graph path mocks ✅
- #114 streaming fallback ✅
- #116 rewrite_max_tokens default ✅
- #118 redis cache legacy marker ✅
- #117 qdrant error signal ✅
- #119 mypy duplicate module ✅

### Test Results
<paste output from step 3>

### Trace IDs
<paste from Phase 3>

### Go/No-Go
<decision + reasoning>"
```

**Step 5: Close #120**

```bash
gh issue close 120 --reason completed
```
