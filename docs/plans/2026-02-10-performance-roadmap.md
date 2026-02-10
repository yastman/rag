# RAG Pipeline Performance & Observability Roadmap

**Дата:** 2026-02-10
**Источники:** worker-bge-research.log, worker-trace-audit.log, worker-sdk-research.log
**Baseline trace:** `2b920c515cdd5315a2575ae0b8059bbb` (FAQ, 20s, rewrite x1)
**Branch:** `fix/issue120-umbrella` (8 fixes merged, issues #112–#119 closed)

---

## Current State

### Latency Breakdown (avg по 8 root traces)

| Компонент | Avg ms | Max ms | % total | Статус |
|-----------|--------|--------|---------|--------|
| generate-answer (LLM) | 5,711 | 23,393 | 27.6% | Стриминг маскирует UX |
| bge-m3-dense-embed | 3,406 | 13,231 | 16.4% | **BOTTLENECK** |
| rewrite-query (LLM) | 1,792 | 4,099 | 8.6% | Ложные rewrites |
| bge-m3-sparse-embed | 1,411 | 7,847 | 6.8% | **BOTTLENECK** |
| qdrant-hybrid-search-rrf | 123 | 523 | 0.6% | OK |
| cache-semantic-check | 34 | 109 | 0.2% | OK |
| Всё остальное | <10 | — | <0.1% | OK |

**Cold start:** dense=6.3s + sparse=7.8s = 14.1s (первый запрос после деплоя).
**Warm:** dense=0.3–1.2s, sparse=0.3–1.0s.
**Total avg:** 20.7s per RAG query.

### Проблемы (приоритезировано)

| # | Проблема | Источник | Влияние |
|---|----------|----------|---------|
| P0-1 | `latency_total_ms` score inflated 300x+ при rewrite loops | trace-audit | Метрики бесполезны |
| P0-2 | 2 отдельных HTTP вызова BGE (dense+sparse) вместо 1 `/encode/hybrid` | bge-research | +40–50% latency |
| P0-3 | Нет connection pooling (новый httpx client каждый раз) | bge-research | +50–200ms overhead |
| P0-4 | Rewrite loop: 3 итерации при MAX_REWRITE_ATTEMPTS=1 | trace-audit | 3–5s лишней работы |
| P1-1 | Grade threshold (0.3) не калиброван под RRF scores | trace-audit | Ложные rewrites |
| P1-2 | Rerank НИКОГДА не вызывается (skip_rerank_threshold=0.85) | trace-audit | Качество ответов |
| P1-3 | 5 из 12 Langfuse scores hardcoded 0.0 | trace-audit | Нет observability |
| P1-4 | Redis: timeout 2s, нет retry, нет health_check | sdk-research | Fragile connections |
| P1-5 | Qdrant: нет explicit timeout, score boosting на клиенте | sdk-research | Suboptimal perf |
| P2-1 | 41 orphan traces из 50 (no session/user) | trace-audit | Шум в Langfuse |
| P2-2 | store_conversation_batch без @observe | trace-audit | Невидимый span |
| P2-3 | LLM generate variance 28x (839ms–23.4s) | trace-audit | Непредсказуемо |
| P2-4 | OMP_NUM_THREADS конфликт Dockerfile vs compose | bge-research | Неопределённость |
| P3-1 | ONNX INT8 migration (3.6x speedup potential) | bge+sdk research | Требует spike |

---

## Sprint 1: Latency & Correctness (NOW — эта неделя)

**Цель:** Убрать P0 blockers. Целевая latency: 20s → <8s (warm), <12s (cold).

### 1.1 BGE-M3: `/encode/hybrid` + connection pooling

**Issues:** #106, #105
**Files:** `telegram_bot/integrations/embeddings.py`, `telegram_bot/graph/nodes/retrieve.py`

**Изменения:**
1. Создать `BGEM3HybridEmbeddings` class → один вызов `/encode/hybrid` возвращает `{dense_vecs, lexical_weights}`
2. Shared `httpx.AsyncClient` (singleton per bot lifecycle) с connection pooling
3. `retrieve_node`: вызывать hybrid вместо dense+sparse раздельно
4. `cache_check_node`: dense embedding из hybrid (кеш тот же ключ)

**Expected impact:** 2x latency reduction на embed phase (14s → ~7s cold, 2s → ~1s warm).

```python
# Before: 2 HTTP calls, 2 forward passes
dense = await self.dense_embedder.embed(query)   # 6.3s
sparse = await self.sparse_embedder.embed(query)  # 7.8s

# After: 1 HTTP call, 1 forward pass
result = await self.hybrid_embedder.embed(query)  # ~8s cold, ~1s warm
dense, sparse = result["dense_vecs"], result["lexical_weights"]
```

**Acceptance:** Unit test hybrid client + integration trace showing single embed span.

### 1.2 Fix latency_total_ms score

**Issues:** #107, #105
**Files:** `telegram_bot/bot.py` (`_write_langfuse_scores`), `telegram_bot/graph/state.py`

**Изменения:**
1. Заменить `sum(latency_stages.values()) * 1000` на wall-time: `(end - start) * 1000`
2. Записывать `start_time` в state при входе в graph, `end_time` при выходе
3. `latency_stages` оставить для breakdown, но не использовать для total

**Expected impact:** Корректные latency scores во всех traces.

### 1.3 Fix rewrite loop count

**Issues:** #109, #108
**Files:** `telegram_bot/graph/nodes/grade.py`, `telegram_bot/graph/nodes/rewrite.py`

**Изменения:**
1. Audit `route_grade()`: проверить условие `rewrite_count < max_rewrite_attempts`
2. Проверить `GraphConfig.from_env()` → `max_rewrite_attempts` propagation
3. Если баг в state merge (LangGraph dict без reducer) — добавить `Annotated[int, operator.add]` или explicit increment

**Expected impact:** MAX_REWRITE_ATTEMPTS=1 → максимум 1 rewrite iteration.

### 1.4 Recalibrate grade threshold for RRF scores

**Issues:** #109
**Files:** `telegram_bot/graph/nodes/grade.py`

**Изменения:**
1. Снять реальные RRF score distributions из Langfuse traces
2. RRF scores = `1/(k+rank)`, обычно 0.01–0.02 — порог 0.3 **невозможно** достичь
3. Перевести на percentile-based threshold ИЛИ отдельный binary grader (LLM-based)

**Expected impact:** Прекращение ложных rewrites, rerank начнёт вызываться.

### 1.5 Docker rebuild + trace validation

**Issues:** #110
**After:** 1.1–1.4 merged

**Шаги:**
1. `docker compose build --no-cache bot bge-m3`
2. `docker compose up -d --force-recreate`
3. Telegram smoke: `/start`, RAG query, `/stats`
4. Langfuse: проверить single embed span, correct latency_total_ms, no 3x rewrite
5. Зафиксировать baseline trace IDs в #120

---

## Sprint 2: Observability & SDK Hardening (NEXT — следующая неделя)

**Цель:** Полная observability, hardened connections, rerank pipeline working.

### 2.1 Implement real Langfuse scores (5 hardcoded → real values)

**Issues:** #103
**Files:** `telegram_bot/bot.py`, `telegram_bot/graph/state.py`, `telegram_bot/graph/nodes/cache_check.py`, `telegram_bot/graph/nodes/retrieve.py`

| Score | Источник | Реализация |
|-------|----------|------------|
| `embeddings_cache_hit` | cache_check_node | `state["embeddings_cache_hit"] = bool(cached_embedding)` |
| `search_cache_hit` | retrieve_node | `state["search_cache_hit"] = bool(cached_results)` |
| `confidence_score` | grade_node | `state["confidence_score"] = top_score` (уже есть) |
| `hyde_used` | cache_check_node | `state["hyde_used"] = bool(hyde_query)` |
| `rerank_cache_hit` | rerank_node | `state["rerank_cache_hit"] = bool(cached_rerank)` |

### 2.2 Enable rerank pipeline

**Files:** `telegram_bot/graph/nodes/grade.py`, `telegram_bot/graph/nodes/rerank.py`

**Изменения:**
1. После 1.4 (grade threshold fix) — rerank route должен срабатывать
2. Проверить `route_grade`: `relevant AND confidence < skip_rerank_threshold` → rerank
3. Добавить ColBERT rerank span в traces
4. Benchmark rerank latency (expected: bge-m3 `/rerank` ~100–500ms)

### 2.3 Redis SDK hardening

**Issues:** NEW
**Files:** `telegram_bot/integrations/cache.py`

| Параметр | Сейчас | Target |
|----------|--------|--------|
| `redis>=` | 7.0.1 | 7.1.0 |
| `socket_timeout` | 2s | 5s |
| `socket_connect_timeout` | 2s | 5s |
| `retry_on_timeout` | not set | True |
| `health_check_interval` | not set | 30 |
| Eviction policy | ? | volatile-lfu |

### 2.4 Qdrant SDK improvements

**Issues:** NEW
**Files:** `telegram_bot/services/qdrant.py`

| Параметр | Сейчас | Target |
|----------|--------|--------|
| `timeout` | default (5s) | 30s explicit |
| Score boosting | Client-side `exp_decay` | `FormulaQuery` server-side (Qdrant 1.14+) |
| RRF `k` param | `Rrf(k=rrf_k)` | ✅ OK already |

### 2.5 Orphan traces cleanup

**Issues:** NEW
**Files:** `telegram_bot/observability.py`, smoke test scripts

1. Добавить `propagate_attributes` wrapper в smoke tests
2. Dashboard filter: `sessionId is not null`
3. Bulk delete orphan traces via Langfuse API

### 2.6 Add @observe to missing spans

**Files:** `telegram_bot/integrations/cache.py`

1. `store_conversation_batch` → `@observe(name="cache-conversation-store")`
2. `get_conversation_history` → `@observe(name="cache-conversation-get")` если добавим

---

## Sprint 3: Performance Deep Dive (LATER — через 2 недели)

**Цель:** ONNX spike, LLM optimization, infrastructure hardening.

### 3.1 ONNX INT8 spike (dense path)

**Issues:** #106
**Model:** `gpahal/bge-m3-onnx-int8` (488 downloads/month, O2 optimized)

**Scope spike:**
1. Заменить `services/bge-m3-api/app.py` backend на ONNX Runtime
2. Использовать `ORTModelForCustomTasks` (НЕ `ORTModelForFeatureExtraction` — нет sparse/colbert)
3. Session options: `intra_op=4, inter_op=1, ORT_SEQUENTIAL, ORT_ENABLE_ALL`
4. Warmup при старте (dummy inference)
5. INT8 dynamic quantization (НЕ float8 — NaN errors)

**Expected:** ~3.6x speedup (10.8s → ~3s total embed), ~800MB RAM.

**Decision gate:**
- Если >=20% выигрыш на dense + quality parity → implement
- Если нет стабильного выигрыша для tri-vector → оставить PyTorch + hybrid

```python
# ONNX INT8 reference
from optimum.onnxruntime import ORTModelForCustomTasks
model = ORTModelForCustomTasks.from_pretrained("gpahal/bge-m3-onnx-int8")
outputs = model(**inputs)  # {dense_vecs, sparse_vecs, colbert_vecs}
```

### 3.2 OMP/MKL thread tuning

**Files:** `services/bge-m3-api/Dockerfile`, `docker-compose.dev.yml`

1. Resolve конфликт: Dockerfile OMP=2 vs compose OMP=4
2. Set: `OMP_NUM_THREADS=4, MKL_NUM_THREADS=4, OMP_WAIT_POLICY=PASSIVE, KMP_BLOCKTIME=1`
3. ONNX: `intra_op_num_threads=4, inter_op_num_threads=1`

### 3.3 LLM latency investigation

**Issues:** NEW
**Files:** `telegram_bot/services/llm.py`

1. Добавить `provider` и `model` в trace metadata для каждого LLM call
2. Диагностика: Cerebras primary (839ms) vs fallback chain (23.4s)
3. Рассмотреть: `reasoning_effort` param, split models (fast for rewrite, strong for generate)

### 3.4 Re-baseline latency

**Issues:** #101
**After:** 3.1–3.3

1. Запустить 25 E2E scenarios
2. Зафиксировать p50/p95 per span
3. Сравнить с текущим baseline (20.7s avg)
4. Go/No-Go по production deploy

---

## Backlog (не скоро)

| # | Issue | Тема | Описание |
|---|-------|------|----------|
| #74 | PostgresSaver | LangGraph persistence | Enable checkpointing |
| #75 | astream | Telegram UX | LangGraph streaming API |
| #72 | BuildKit cache | Infra | Slim Docker images |
| #54 | k3s migration | Infra | Docker Compose → k3s |
| #70 | Qdrant snapshots | Infra | Backup before re-index |
| #71 | Security | Infra | Pin uv images, CVE fixes |
| #5 | Voice messages | Feature | Bot voice support |
| #102 | A/B benchmark | Perf | reasoning_effort, split models |

---

## Issue Mapping

### Existing issues → sprint tasks

| Issue | Sprint | Task |
|-------|--------|------|
| #105 | S1 | 1.1 + 1.2 (BGE + latency fix) |
| #106 | S1 + S3 | 1.1 (hybrid) + 3.1 (ONNX spike) |
| #107 | S1 | 1.2 (latency_total_ms) |
| #108 | S1 | 1.3 (rewrite stop-guard) |
| #109 | S1 | 1.3 + 1.4 (grade recalibration) |
| #110 | S1 | 1.5 (rebuild + traces) |
| #103 | S2 | 2.1 (real scores) |
| #91 | S2 | 2.5 (audit remediation) |
| #100 | S3 | 3.1 (ONNX tail-latency guard) |
| #101 | S3 | 3.4 (re-baseline) |

### New issues to create

| Тема | Sprint | Описание |
|------|--------|----------|
| Redis SDK hardening | S2 | timeout, retry, health_check, upgrade 7.1 |
| Qdrant SDK improvements | S2 | explicit timeout, FormulaQuery |
| Orphan traces cleanup | S2 | propagate_attributes fix |
| LLM latency investigation | S3 | provider metadata + variance analysis |

---

## Target Metrics

| Метрика | Сейчас | После S1 | После S3 |
|---------|--------|----------|----------|
| Total latency (warm, p50) | ~18s | <8s | <5s |
| Total latency (cold, p50) | ~32s | <12s | <8s |
| BGE-M3 embed (warm) | ~2s | ~1s | ~0.5s (ONNX) |
| BGE-M3 embed (cold) | ~14s | ~8s | ~3s (ONNX) |
| Rewrite iterations (avg) | 2.1 | ≤1 | ≤1 |
| Rerank applied % | 0% | >50% | >70% |
| Langfuse scores accurate | 7/12 | 12/12 | 12/12 |
| Orphan trace % | 82% | <10% | <5% |

---

## Execution Strategy

- Sprint 1: `/tmux-swarm-orchestration` — 3-4 параллельных workers (1.1+1.2, 1.3+1.4, 1.5 after merge)
- Sprint 2: `/subagent-driven-development` — sequential tasks, review after each
- Sprint 3: `/writing-plans` → `/executing-plans` — ONNX spike requires careful design

**PR strategy:** 1 PR per sprint, squash merge to main.
