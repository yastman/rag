# BGE-M3 Cold Start Mitigation + ONNX Spike — Implementation Plan

**Goal:** Устранить cold start (20-30s) BGE-M3 при первом запросе и исследовать ONNX INT8 для снижения latency на CPU (target: embed stage < 3s на запрос).

**Issue:** https://github.com/yastman/rag/issues/106

**Milestone:** Stream-A: Latency-LLM+Embed

---

## Текущее состояние

| Файл | Строки | Что делает |
|------|--------|------------|
| `services/bge-m3-api/app.py:39-56` | `_model = None`, `get_model()` | Lazy loading PyTorch модели — cold start 20-30s при первом запросе |
| `services/bge-m3-api/app.py:149-152` | `/health` endpoint | Возвращает `model_loaded` status, но НЕ загружает модель |
| `services/bge-m3-api/config.py:20-22` | `MAX_LENGTH=2048`, `BATCH_SIZE=12` | MAX_LENGTH завышен для query-time (query обычно 10-50 токенов) |
| `services/bge-m3-api/Dockerfile:59-60` | `HEALTHCHECK --start-period=120s` | 120s start period, но модель загружается только при первом encode запросе |
| `services/bge-m3-api/Dockerfile:50` | `OMP_NUM_THREADS=2` | Dockerfile ставит 2, но docker-compose.dev.yml переопределяет на 4 |
| `services/bge-m3-api/pyproject.toml:8-9` | `FlagEmbedding==1.3.5`, `torch==2.10.0` | Текущий PyTorch backend |
| `telegram_bot/integrations/embeddings.py:120-128` | `BGEM3HybridEmbeddings.__init__` | `max_length=512` на стороне клиента (передаётся в API) |
| `telegram_bot/preflight.py:228-233` | `_check_single_dep("bge_m3")` | Только GET `/health` — не тригерит загрузку модели |
| `telegram_bot/graph/config.py:27-28` | `bge_m3_timeout=120.0` | Таймаут 120s — учитывает cold start |
| `docker-compose.dev.yml:82-108` | `bge-m3` service | 4GB memory limit, volume `hf_cache:/models` |

---

## Phase A: Quick Fix (до Gate 1 — baseline)

**Effort:** S (2-3 часа)

### Task A1: Добавить startup warmup через FastAPI lifespan

**Файл:** `services/bge-m3-api/app.py`

**Что сделать:**
1. Строка 24-28: Заменить создание `app = FastAPI(...)` на lifespan-based pattern
2. Добавить `@asynccontextmanager async def lifespan(app)` перед строкой 24
3. Внутри lifespan:
   - Вызвать `get_model()` для eager loading
   - Выполнить dummy encode: `model.encode(["warmup"], batch_size=1, max_length=64, return_dense=True, return_sparse=True, return_colbert_vecs=False)`
   - Залогировать время загрузки и warmup
4. Строка 24: Передать `lifespan=lifespan` в `FastAPI()`

**Пример структуры (отступ 4 пробела вместо code block):**

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting model warmup...")
        start = time.time()
        model = get_model()
        model.encode(["warmup query"], batch_size=1, max_length=64,
                     return_dense=True, return_sparse=True, return_colbert_vecs=False)
        logger.info("Warmup complete in %.2fs", time.time() - start)
        yield

    app = FastAPI(..., lifespan=lifespan)

**Результат:** Модель загружается и прогревается при старте контейнера, а не при первом пользовательском запросе.

### Task A2: Добавить QUERY_MAX_LENGTH конфигурацию

**Файл:** `services/bge-m3-api/config.py`

**Что сделать:**
1. Строка 21 (после `MAX_LENGTH`): Добавить `QUERY_MAX_LENGTH: int = 256`
2. Документировать: MAX_LENGTH=2048 для документов, QUERY_MAX_LENGTH=256 для коротких запросов

**Файл:** `services/bge-m3-api/app.py`

**Что сделать:**
1. Строка 61-63: В `EncodeRequest` сделать `max_length` default = `settings.MAX_LENGTH` (уже так)
2. Клиент (`telegram_bot/integrations/embeddings.py:124-128`) уже передаёт `max_length=512` — это ОК для bot queries

**Примечание:** Основной выигрыш от QUERY_MAX_LENGTH — на стороне API. Для query encoding (1 текст, 10-50 токенов) padding до 2048 = лишние вычисления. Клиент уже ограничивает до 512, но можно уменьшить дефолт для query use-case.

### Task A3: Добавить keep-warm encode в preflight

**Файл:** `telegram_bot/preflight.py`

**Что сделать:**
1. Строка 228-233: Изменить `_check_single_dep("bge_m3")`:
   - После GET `/health` добавить POST `/encode/dense` с dummy текстом
   - Это гарантирует что модель прогрета ПЕРЕД тем как bot начнёт обрабатывать запросы

**Текущий код (строка 228-233):**

    if name == "bge_m3":
        resp = await client.get(f"{config.bge_m3_url}/health")
        if resp.status_code != 200:
            logger.error("Preflight FAIL: BGE-M3 — %s", resp.status_code)
            return False
        return True

**Новый код:**

    if name == "bge_m3":
        resp = await client.get(f"{config.bge_m3_url}/health")
        if resp.status_code != 200:
            logger.error("Preflight FAIL: BGE-M3 — %s", resp.status_code)
            return False
        # Warm encode to ensure model is loaded and warmed
        warmup_resp = await client.post(
            f"{config.bge_m3_url}/encode/dense",
            json={"texts": ["preflight warmup"], "max_length": 64, "batch_size": 1},
            timeout=120.0,
        )
        if warmup_resp.status_code == 200:
            data = warmup_resp.json()
            logger.info("Preflight BGE-M3 warmup OK (%.3fs)", data.get("processing_time", 0))
        else:
            logger.warning("Preflight BGE-M3 warmup failed: %s", warmup_resp.status_code)
        return True

### Task A4: Обновить /health endpoint для отражения warmup статуса

**Файл:** `services/bge-m3-api/app.py`

**Что сделать:**
1. Строка 39: Добавить глобальный `_warmed_up = False`
2. В `lifespan` (Task A1): после warmup encode установить `_warmed_up = True`
3. Строка 149-152: Обновить `/health`:

    @app.get("/health")
    async def health():
        return {"status": "ok", "model_loaded": _model is not None, "warmed_up": _warmed_up}

### Task A5: Записать baseline метрики

**Действия (ручные, не код):**
1. Запустить `make docker-up` с текущим кодом (до изменений) — записать p50/p95 embed latency
2. Применить изменения Phase A — записать новые метрики
3. Проверить через Langfuse traces: `bge-m3-hybrid-embed` span duration

---

## Phase B: ONNX Spike (после Gate 1)

**Effort:** M-L (4-8 часов, включая бенчмарк)

### Task B1: Исследование — подготовка ONNX модели

**Ресурсы (из MCP research):**
- `gpahal/bge-m3-onnx-int8` — готовый ONNX INT8 с O2 оптимизациями на HuggingFace
- `aapot/bge-m3-onnx` — FP32 ONNX версия
- Используется `optimum.onnxruntime.ORTModelForCustomTasks` для инференса
- Dynamic quantization (INT8) — рекомендуется для transformer моделей (ONNX Runtime docs)
- CPU: S8S8 с QDQ — дефолт, хорошо работает с AVX2/AVX512

**Ключевые находки:**
- `ORTModelForCustomTasks.from_pretrained("gpahal/bge-m3-onnx-int8")` — прямой drop-in
- Tokenizer: `AutoTokenizer.from_pretrained("BAAI/bge-m3")`
- Выходы: 3 numpy array (dense, sparse, ColBERT) — нужна нормализация dense + ColBERT
- Session options: `intra_op_num_threads`, `graph_optimization_level=ORT_ENABLE_ALL`
- **Важно:** ONNX INT8 даёт спидап на CPU с AVX512-VNNI. На старых CPU (без VNNI) может быть медленнее

### Task B2: Добавить BGE_BACKEND конфигурацию

**Файл:** `services/bge-m3-api/config.py`

**Что сделать:**
1. Добавить после строки 18:

    BGE_BACKEND: str = "pytorch"  # "pytorch" | "onnx"
    ONNX_MODEL_ID: str = "gpahal/bge-m3-onnx-int8"
    ONNX_OPTIMIZATION_LEVEL: str = "O2"

### Task B3: Реализовать ONNX inference path

**Файл:** `services/bge-m3-api/app.py`

**Что сделать:**
1. Добавить новую функцию `get_onnx_model()` — загрузка через `ORTModelForCustomTasks`
2. Добавить `get_onnx_tokenizer()` — загрузка `AutoTokenizer`
3. Модифицировать `get_model()` (строка 42-56): роутинг по `settings.BGE_BACKEND`
4. Создать абстракцию `encode_texts(texts, max_length, return_dense, return_sparse, return_colbert)`:
   - PyTorch path: текущий `model.encode()` через FlagEmbedding
   - ONNX path: tokenize → `model(**inputs)` → parse 3 outputs (dense, sparse, ColBERT)
5. Обновить все endpoint handlers для использования `encode_texts()`

**ONNX inference pattern:**

    from optimum.onnxruntime import ORTModelForCustomTasks
    from transformers import AutoTokenizer
    import numpy as np

    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
    model = ORTModelForCustomTasks.from_pretrained("gpahal/bge-m3-onnx-int8")

    inputs = tokenizer(texts, padding=True, truncation=True,
                       max_length=max_length, return_tensors="np")
    outputs = model(**inputs)
    # outputs: [dense_vecs, sparse_vecs, colbert_vecs] — numpy arrays
    dense = outputs[0]  # normalize: dense / np.linalg.norm(dense, axis=-1, keepdims=True)

**Session options для ONNX:**

    import onnxruntime as ort
    sess_options = ort.SessionOptions()
    sess_options.intra_op_num_threads = settings.NUM_THREADS  # 4
    sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

### Task B4: Обновить зависимости для ONNX

**Файл:** `services/bge-m3-api/pyproject.toml`

**Что добавить в dependencies:**

    "onnxruntime>=1.20.0",
    "optimum[onnxruntime]>=1.24.0",

**Важно:** torch остаётся как зависимость для PyTorch fallback path.

### Task B5: Обновить Dockerfile для ONNX модели

**Файл:** `services/bge-m3-api/Dockerfile`

**Что сделать:**
1. ONNX модель будет скачиваться при первом запуске и кэшироваться в volume `hf_cache:/models`
2. Альтернатива: добавить шаг в builder для pre-download ONNX модели
3. Рассмотреть: отдельный Dockerfile.onnx или env-based switch

### Task B6: Бенчмарк ONNX vs PyTorch

**Файл:** Новый скрипт `services/bge-m3-api/benchmark.py`

**Метрики для сравнения:**
- Cold start time (model load)
- Warmup time (first encode)
- p50/p95 encode latency (batch_size=1, max_length=256)
- p50/p95 encode latency (batch_size=12, max_length=2048)
- Recall@10 parity: encode 100 query-document пар, сравнить top-10 с PyTorch baseline
- RAM consumption (docker stats)

**Acceptance criteria для ONNX:**
- Encode latency p50 < 2s (одиночный query)
- Recall@10 >= 95% overlap с PyTorch baseline
- Cold start < 10s (vs 20-30s PyTorch)

### Task B7: Обновить Docker Compose и документацию

**Файл:** `docker-compose.dev.yml`

**Что сделать (строка 93-94, environment):**

    BGE_BACKEND: ${BGE_BACKEND:-pytorch}

**Rollback:** Достаточно поменять env var на `BGE_BACKEND=pytorch`.

---

## Test Strategy

| Тест | Файл | Что проверяет |
|------|------|---------------|
| Unit: warmup при старте | `tests/unit/services/test_bge_warmup.py` | lifespan загружает модель и делает dummy encode |
| Unit: QUERY_MAX_LENGTH config | `tests/unit/services/test_bge_config.py` | Settings парсит QUERY_MAX_LENGTH |
| Unit: preflight warmup | `tests/unit/test_preflight.py` | BGE-M3 check делает POST encode |
| Unit: /health warmed_up | `tests/unit/services/test_bge_health.py` | /health возвращает warmed_up field |
| Integration: cold start | `tests/integration/test_bge_cold_start.py` | Время от docker up до первого успешного encode < 3s после warmup |
| Benchmark: ONNX vs PyTorch | `services/bge-m3-api/benchmark.py` | Latency comparison, recall parity |

**Существующие тесты для embeddings:**

    tests/unit/integrations/test_embeddings.py  — LangChain wrappers
    tests/unit/graph/test_retrieve_node.py      — retrieve node (6 tests)

---

## Acceptance Criteria

### Phase A (обязательные)
- [ ] Cold start = 0s для первого пользовательского запроса (модель прогрета при старте контейнера)
- [ ] `/health` отражает `warmed_up: true` после lifespan warmup
- [ ] Preflight делает warmup encode (не только GET /health)
- [ ] Время от `docker compose up` до ready-for-queries < 60s (= model load + warmup)
- [ ] Нет регрессии: top-k overlap идентичен (warmup не влияет на inference)

### Phase B (при успешном spike)
- [ ] ONNX INT8 encode latency p50 < 2s для одиночного query (max_length=256)
- [ ] Recall@10 >= 95% overlap с PyTorch baseline на тестовом датасете
- [ ] Feature flag `BGE_BACKEND=pytorch|onnx` работает, rollback за 1 env change
- [ ] Бенчмарк отчёт зафиксирован в `docs/benchmarks/bge-onnx-vs-pytorch.md`

---

## Effort Estimate

| Phase | Effort | Часы | Зависимости |
|-------|--------|------|-------------|
| Phase A | S | 2-3 | Нет |
| Phase B | M-L | 4-8 | Phase A (baseline), CPU с AVX2+ |
| **Итого** | **M** | **6-11** | |

---

## Risks & Mitigations

| Риск | Вероятность | Mitigation |
|------|-------------|------------|
| ONNX INT8 медленнее PyTorch на CPU без AVX512-VNNI | Средняя | Benchmark на target CPU; fallback на PyTorch |
| ONNX sparse output формат отличается от FlagEmbedding | Средняя | Нужен adapter для конвертации sparse output |
| gpahal/bge-m3-onnx-int8 может не поддерживать все 3 output | Низкая | Проверить output format; альтернатива: self-export через optimum CLI |
| Увеличение Docker image size (onnxruntime + optimum) | Низкая | Multi-stage build; ONNX-only image без torch (Phase B+) |
