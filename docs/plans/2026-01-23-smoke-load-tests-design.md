# Smoke + Load Tests Design

**Дата:** 2026-01-23
**Статус:** Approved
**Цель:** Добавить smoke (20 запросов) и load (20-50 параллельных чатов) тесты для проверки routing, caching, quantization A/B и streaming.

---

## 1. Обзор

### Smoke-тесты
- **20 запросов** на русском языке
- **Live сервисы** (Qdrant, Redis)
- Проверяют: routing работает, кэши пишутся, quantization A/B переключается, streaming не ломает формат

### Load-тесты
- **5-20 минут**, 20-50 параллельных чатов
- **Configurable**: live для локала, mock для CI
- Проверяют: p95 latency, Redis LFU eviction не делает thrashing

---

## 2. Структура файлов

```
tests/
├── smoke/
│   ├── __init__.py
│   ├── test_smoke_pipeline.py      # Основной smoke (20 RU запросов)
│   ├── test_smoke_multilang.py     # Опциональный multilingual (6 запросов)
│   ├── queries.py                  # Определения запросов по типам
│   └── conftest.py                 # Smoke-специфичные fixtures
├── load/
│   ├── __init__.py
│   ├── test_load_conversations.py  # Симуляция 20-50 параллельных чатов
│   ├── test_load_redis_eviction.py # Memory pressure + eviction тесты
│   ├── chat_simulator.py           # Генератор реалистичных диалогов
│   ├── metrics_collector.py        # Сборщик p95, TTFT, Redis stats
│   ├── thresholds.py               # Пороги warn/fail
│   ├── conftest.py                 # Load-специфичные fixtures (mock toggle)
│   └── baseline.json               # Исторические p95 для детекции регрессий
└── conftest.py                     # Общие: URLs сервисов, skip markers
```

---

## 3. Smoke-тесты: 20 запросов

### 3.1 Распределение запросов

| Тип | Кол-во | Ожидаемое поведение |
|-----|--------|---------------------|
| CHITCHAT | 6 | Skip RAG полностью |
| SIMPLE | 6 | Лёгкий RAG, skip rerank |
| COMPLEX | 8 | Полный RAG + rerank + quantization A/B + streaming |

### 3.2 Запросы (`queries.py`)

```python
SMOKE_QUERIES = {
    "CHITCHAT": [
        "Привет!",
        "Добрый день",
        "Спасибо за помощь",
        "Кто ты?",
        "Что ты умеешь?",
        "Пока, до свидания",
    ],
    "SIMPLE": [
        "Сколько стоит квартира?",
        "Какая цена на студию?",
        "Есть ли бассейн?",
        "Какой этаж?",
        "Сколько комнат?",
        "Когда сдача дома?",
    ],
    "COMPLEX": [
        "Найди двухкомнатную квартиру в Солнечном берегу до 50000 евро с видом на море",
        "Квартиры в комплексе Harmony Suites корпус 3 с мебелью",
        "Сравни цены на студии в Несебре и Равде",
        "Апартаменты с двумя спальнями рядом с пляжем, первая линия",
        "Что лучше: Sunny Beach или Sveti Vlas для инвестиций?",
        "Новостройки с рассрочкой платежа на 2 года",
        "Квартира с паркингом и кладовой в закрытом комплексе",
        "Покажи варианты до 70000 евро с ремонтом под ключ",
    ],
}
```

### 3.3 Проверки для каждого типа

| Тип | Routing | Cache | Quantization A/B | Streaming |
|-----|---------|-------|------------------|-----------|
| CHITCHAT | `classify_query() == CHITCHAT` | — | — | — |
| SIMPLE | `classify_query() == SIMPLE` | cache write | — | — |
| COMPLEX | `classify_query() == COMPLEX` | cache write | с/без `quantization_ignore` | chunks + MD формат |

### 3.4 Multilingual pack (опционально)

Отдельный файл `test_smoke_multilang.py` с 6 запросами (4 RU + 2 EN) для nightly/release прогонов.

---

## 4. Load-тесты: параллельные чаты

### 4.1 Шаблон диалога

```python
CONVERSATION_TEMPLATE = [
    {"type": "CHITCHAT", "query": "Привет!"},
    {"type": "COMPLEX", "query": "{property_query_1}"},
    {"type": "SIMPLE", "query": "А какая там цена?"},
    {"type": "COMPLEX", "query": "{property_query_2}"},
    {"type": "SIMPLE", "query": "Есть ли рассрочка?"},
    {"type": "CHITCHAT", "query": "Спасибо, пока!"},
]
```

~6 сообщений на чат × 30 чатов = ~180 запросов за сессию.

### 4.2 Параметры

| Параметр | Default | Env override |
|----------|---------|--------------|
| Параллельных чатов | 30 | `LOAD_CHAT_COUNT` |
| Длительность | 10 мин | `LOAD_DURATION_MIN` |
| Задержка между сообщениями | 2-5 сек (random) | — |
| Режим сервисов | live | `LOAD_USE_MOCKS=1` |

### 4.3 Собираемые метрики

```python
@dataclass
class LoadMetrics:
    # Latency (все значения для p50/p95/p99)
    routing_latencies: list[float]
    cache_hit_latencies: list[float]
    qdrant_latencies: list[float]
    full_rag_latencies: list[float]
    ttft_latencies: list[float]

    # Counters
    total_requests: int
    cache_hits: int
    cache_misses: int
    errors: int

    # Redis stats
    redis_stats_start: dict
    redis_stats_end: dict
```

---

## 5. Пороги p95

### 5.1 Абсолютные пороги

| Компонент | Warn (ms) | Fail (ms) |
|-----------|-----------|-----------|
| Query routing | 20 | 30 |
| Cache hit | 20 | 30 |
| Qdrant search | 120 | 200 |
| Full RAG | 3000 | 4000 |
| TTFT | 800 | 1200 |

### 5.2 Детекция регрессий

Тест падает если p95 вырос **> 20%** относительно `baseline.json`:

```python
def check_regression(current_p95, baseline_p95):
    if current_p95 > baseline_p95 * 1.20:
        return Fail(f"Регрессия: {current_p95}ms vs baseline {baseline_p95}ms")
```

### 5.3 Обновление baseline

```bash
pytest tests/load/ -v --update-baseline
```

---

## 6. Redis eviction тесты

### 6.1 Проверка конфигурации (fail fast)

```python
async def verify_redis_config(redis: Redis):
    policy = await redis.config_get("maxmemory-policy")
    maxmem = await redis.config_get("maxmemory")

    assert policy["maxmemory-policy"] == "allkeys-lfu"
    assert int(maxmem["maxmemory"]) > 0
```

### 6.2 Memory pressure тест

1. Отдельная Redis DB с `maxmemory=50MB`
2. Запуск нагрузки 5-10 минут
3. Сэмплирование каждые 10 сек: `keyspace_hits`, `keyspace_misses`, `evicted_keys`

### 6.3 Критерии pass/fail

| Метрика | Pass | Fail |
|---------|------|------|
| Hit rate | ≥ 60% | < 60% дольше 30 сек |
| Evictions/sec trend | стабилен или падает | растёт линейно (slope > 0.5) |
| Cache p95 latency | не деградирует | рост > 50% vs начало |

---

## 7. Makefile команды

```makefile
# Smoke
test-smoke:
	pytest tests/smoke/test_smoke_pipeline.py -v --tb=short

test-smoke-multilang:
	pytest tests/smoke/test_smoke_multilang.py -v --tb=short

# Load
test-load:
	pytest tests/load/test_load_conversations.py -v --tb=short

test-load-eviction:
	pytest tests/load/test_load_redis_eviction.py -v --tb=short

test-load-all:
	pytest tests/load/ -v --tb=short

# CI (с моками, короткий)
test-load-ci:
	LOAD_USE_MOCKS=1 LOAD_DURATION_MIN=2 LOAD_CHAT_COUNT=10 \
	pytest tests/load/test_load_conversations.py -v

# Обновить baseline
test-load-update-baseline:
	pytest tests/load/ -v --update-baseline
```

---

## 8. Вывод результатов

```
======================== LOAD TEST RESULTS ========================
Duration: 10 min | Chats: 30 | Requests: 180

LATENCY (p95):
  routing:    18ms  ✓ (warn: 20ms, fail: 30ms)
  cache_hit:  12ms  ✓ (warn: 20ms, fail: 30ms)
  qdrant:     95ms  ✓ (warn: 120ms, fail: 200ms)
  full_rag:   2.8s  ✓ (warn: 3.0s, fail: 4.0s)
  ttft:       650ms ✓ (warn: 800ms, fail: 1.2s)

CACHE:
  hit_rate:   72%   ✓ (min: 60%)

REDIS EVICTION:
  evictions/sec: 2.3 (stable) ✓
  trend slope:   -0.1         ✓

REGRESSION vs baseline:
  No regressions detected     ✓

======================== PASSED ========================
```

---

## 9. Зависимости

```
# requirements-dev.txt (добавить)
numpy>=1.24.0       # percentile, polyfit
aioredis>=2.0.0     # async Redis
```

---

## 10. Следующие шаги

1. Создать структуру файлов
2. Реализовать `queries.py` и `chat_simulator.py`
3. Реализовать `metrics_collector.py` и `thresholds.py`
4. Написать `test_smoke_pipeline.py`
5. Написать `test_load_conversations.py`
6. Написать `test_load_redis_eviction.py`
7. Добавить команды в Makefile
8. Первый прогон и создание `baseline.json`
