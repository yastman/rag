# Baseline & Observability Design

**Дата:** 2026-01-28
**Статус:** Draft
**Цель:** Regression detection + Cost tracking через Langfuse v3

---

## 1. Обзор

### Проблема
Нет способа автоматически ловить деградацию производительности и рост затрат при изменениях в коде/конфигурации.

### Решение
Трёхуровневая система тестирования с Langfuse v3 как единым источником метрик:

| Уровень | Когда | Что проверяет | Время |
|---------|-------|---------------|-------|
| **Smoke baseline** | Каждый PR | Функциональность + базовые метрики | ~30 сек |
| **Load baseline** | Pre-merge | Performance под нагрузкой (p95) | ~2 мин |
| **E2E Telegram** | Nightly/Release | Полный user journey | ~5 мин |

### Ключевые решения
- **Langfuse v3.150.0** — источник истины для всех метрик
- **Гибрид Smoke + Load** — для baseline (не E2E Telegram)
- **Полный observability** — LLM tokens, Voyage calls, Qdrant metrics, Redis memory

---

## 2. Архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Test Runner                                  │
│  (make baseline-smoke / make baseline-load / make baseline-compare) │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Langfuse v3 (localhost:3001)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Traces     │  │  Metrics API │  │  Daily API   │              │
│  │  (per call)  │  │ (aggregated) │  │ (cost/tokens)│              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
    ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
    │ LiteLLM │          │ Qdrant  │          │  Redis  │
    │  OTEL   │          │ /metrics│          │  INFO   │
    └─────────┘          └─────────┘          └─────────┘
```

### Источники метрик

| Метрика | Источник | API/Endpoint |
|---------|----------|--------------|
| LLM calls, tokens, cost | Langfuse | `GET /api/public/metrics/daily` |
| LLM latency (p50/p95) | Langfuse | `GET /api/public/metrics` (v2 query) |
| Voyage embed calls | Custom counter → Langfuse span | Trace observations |
| Voyage rerank calls | Custom counter → Langfuse span | Trace observations |
| Cache hits/misses | CacheService.get_metrics() | Direct Python call |
| Qdrant vectors scanned | Qdrant | `GET /metrics` (Prometheus) |
| Redis memory | Redis | `INFO memory` command |

---

## 3. Компоненты

### 3.1 LangfuseMetricsCollector

Новый класс для сбора метрик из Langfuse API.

**Файл:** `tests/baseline/langfuse_collector.py`

```python
from datetime import datetime, timedelta
from langfuse import Langfuse

class LangfuseMetricsCollector:
    """Collect metrics from Langfuse v3 API."""

    def __init__(self, public_key: str, secret_key: str, host: str):
        self.client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host
        )

    def get_daily_metrics(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str | None = None
    ) -> dict:
        """Get aggregated daily metrics."""
        # GET /api/public/metrics/daily
        return self.client.api.metrics_daily.get(
            from_timestamp=from_ts.isoformat(),
            to_timestamp=to_ts.isoformat(),
            trace_name=trace_name
        )

    def get_latency_metrics(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str | None = None
    ) -> dict:
        """Get latency percentiles via v2 metrics API."""
        query = {
            "view": "observations",
            "metrics": [
                {"measure": "latency", "aggregation": "p50"},
                {"measure": "latency", "aggregation": "p95"},
                {"measure": "totalCost", "aggregation": "sum"},
                {"measure": "count", "aggregation": "count"}
            ],
            "dimensions": [{"field": "providedModelName"}],
            "filters": [],
            "fromTimestamp": from_ts.isoformat(),
            "toTimestamp": to_ts.isoformat()
        }
        return self.client.api.metrics_v_2.get(query=json.dumps(query))

    def get_trace_count(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str
    ) -> int:
        """Count traces for specific operation."""
        query = {
            "view": "traces",
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "dimensions": [{"field": "name"}],
            "filters": [{"field": "name", "operator": "=", "value": trace_name}],
            "fromTimestamp": from_ts.isoformat(),
            "toTimestamp": to_ts.isoformat()
        }
        result = self.client.api.metrics.metrics(query=json.dumps(query))
        return int(result.data[0].get("count_count", 0)) if result.data else 0
```

### 3.2 BaselineManager

Управление baseline через Langfuse.

**Файл:** `tests/baseline/manager.py`

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class BaselineSnapshot:
    """Snapshot of metrics for comparison."""
    timestamp: datetime
    tag: str  # e.g., "smoke-v1.2.3" or "load-main"

    # Latency
    llm_latency_p50_ms: float
    llm_latency_p95_ms: float
    full_rag_latency_p95_ms: float

    # Cost
    total_cost_usd: float
    llm_tokens_input: int
    llm_tokens_output: int

    # Calls
    llm_calls: int
    voyage_embed_calls: int
    voyage_rerank_calls: int

    # Cache
    cache_hit_rate: float
    cache_hits: int
    cache_misses: int

    # Infrastructure
    qdrant_vectors_scanned: int
    redis_memory_mb: float


class BaselineManager:
    """Manage baselines stored as Langfuse tags/sessions."""

    def __init__(self, collector: LangfuseMetricsCollector):
        self.collector = collector

    def create_baseline(
        self,
        tag: str,
        from_ts: datetime,
        to_ts: datetime
    ) -> BaselineSnapshot:
        """Create baseline from Langfuse data in time range."""
        daily = self.collector.get_daily_metrics(from_ts, to_ts)
        latency = self.collector.get_latency_metrics(from_ts, to_ts)

        # Aggregate and return snapshot
        ...

    def compare(
        self,
        current: BaselineSnapshot,
        baseline: BaselineSnapshot,
        thresholds: dict
    ) -> tuple[bool, list[str]]:
        """
        Compare current metrics against baseline.

        Returns:
            (passed, list of regression messages)
        """
        regressions = []

        # Latency regression (default: 20% tolerance)
        if current.llm_latency_p95_ms > baseline.llm_latency_p95_ms * thresholds.get("latency_factor", 1.2):
            regressions.append(
                f"LLM p95 latency regression: {current.llm_latency_p95_ms:.0f}ms "
                f"vs baseline {baseline.llm_latency_p95_ms:.0f}ms"
            )

        # Cost regression (default: 10% tolerance)
        if current.total_cost_usd > baseline.total_cost_usd * thresholds.get("cost_factor", 1.1):
            regressions.append(
                f"Cost regression: ${current.total_cost_usd:.4f} "
                f"vs baseline ${baseline.total_cost_usd:.4f}"
            )

        # Cache hit rate drop (default: 10% absolute drop)
        if current.cache_hit_rate < baseline.cache_hit_rate - thresholds.get("cache_drop", 0.1):
            regressions.append(
                f"Cache hit rate drop: {current.cache_hit_rate:.1%} "
                f"vs baseline {baseline.cache_hit_rate:.1%}"
            )

        return len(regressions) == 0, regressions
```

### 3.3 VoyageService instrumentation

Добавить трейсинг Voyage API calls в Langfuse.

**Изменения в:** `telegram_bot/services/voyage_service.py`

```python
from langfuse.decorators import observe

class VoyageService:
    @observe(name="voyage-embed-query")
    async def embed_query(self, text: str) -> list[float]:
        # existing code
        ...

    @observe(name="voyage-embed-documents")
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # existing code
        ...

    @observe(name="voyage-rerank")
    async def rerank(self, query: str, documents: list[str], top_k: int) -> list:
        # existing code
        ...
```

### 3.4 Makefile targets

**Добавить в:** `Makefile`

```makefile
# =============================================================================
# BASELINE & OBSERVABILITY
# =============================================================================

.PHONY: baseline-smoke baseline-load baseline-compare baseline-report

# Run smoke tests and tag results in Langfuse
baseline-smoke:
	@echo "Running smoke tests with Langfuse tracing..."
	LANGFUSE_SESSION_ID="smoke-$(shell git rev-parse --short HEAD)" \
	pytest tests/smoke/ -v --tb=short
	@echo "Results tagged as: smoke-$(shell git rev-parse --short HEAD)"

# Run load tests and tag results in Langfuse
baseline-load:
	@echo "Running load tests with Langfuse tracing..."
	LANGFUSE_SESSION_ID="load-$(shell git rev-parse --short HEAD)" \
	pytest tests/load/ -v --tb=short
	@echo "Results tagged as: load-$(shell git rev-parse --short HEAD)"

# Compare current run against baseline
baseline-compare:
	@echo "Comparing against baseline..."
	python -m tests.baseline.compare \
		--current="$(shell git rev-parse --short HEAD)" \
		--baseline="$(BASELINE_TAG)" \
		--thresholds=tests/baseline/thresholds.yaml

# Generate baseline report
baseline-report:
	@echo "Generating baseline report..."
	python -m tests.baseline.report \
		--output=reports/baseline-$(shell date +%Y%m%d-%H%M%S).html

# Set current run as new baseline
baseline-set:
	@echo "Setting current as baseline: $(TAG)"
	python -m tests.baseline.set_baseline --tag="$(TAG)"
```

---

## 4. Thresholds (пороги регрессии)

**Файл:** `tests/baseline/thresholds.yaml`

```yaml
# Baseline comparison thresholds
# Regression = current > baseline * factor

latency:
  llm_p95_factor: 1.20      # 20% tolerance
  full_rag_p95_factor: 1.20
  qdrant_p95_factor: 1.30   # 30% tolerance (more variance)

cost:
  total_factor: 1.10        # 10% tolerance
  tokens_factor: 1.15       # 15% tolerance

cache:
  hit_rate_min_drop: 0.10   # Alert if drops >10% absolute

calls:
  llm_factor: 1.05          # 5% tolerance (should be stable)
  voyage_embed_factor: 1.10
  voyage_rerank_factor: 1.10

infrastructure:
  redis_memory_factor: 1.50  # 50% tolerance
  qdrant_vectors_factor: 1.20
```

---

## 5. Smoke Test Queries

Использовать существующие 20 запросов из `tests/smoke/queries.py`:

| Тип | Количество | Примеры |
|-----|------------|---------|
| CHITCHAT | 6 | "Привет", "Спасибо", "Пока" |
| SIMPLE | 6 | "Квартиры до 50000", "2-комнатные" |
| COMPLEX | 8 | "Квартира у моря с видом до 80000 евро" |

**Cold/Warm path тестирование:**
1. Flush Redis cache перед smoke
2. Прогнать все 20 запросов (cold path)
3. Прогнать те же 20 запросов (warm path)
4. Сравнить latency и cache hits

---

## 6. Интеграция с CI

### GitHub Actions workflow

**Файл:** `.github/workflows/baseline.yml`

```yaml
name: Baseline Check

on:
  pull_request:
    branches: [main]

jobs:
  smoke-baseline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Start services
        run: docker compose -f docker-compose.dev.yml up -d

      - name: Wait for services
        run: |
          ./scripts/wait-for-healthy.sh dev-langfuse 60
          ./scripts/wait-for-healthy.sh dev-litellm 30

      - name: Run smoke baseline
        run: make baseline-smoke
        env:
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}

      - name: Compare with baseline
        run: make baseline-compare BASELINE_TAG=main-latest

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: baseline-report
          path: reports/baseline-*.html
```

---

## 7. План реализации

### Фаза 1: Инфраструктура (готово)
- [x] Обновить Langfuse до v3.150.0
- [x] Добавить ClickHouse, MinIO, Redis для Langfuse
- [x] Обновить LiteLLM callback на `langfuse_otel`

### Фаза 2: Сбор метрик
- [ ] Создать `tests/baseline/` директорию
- [ ] Реализовать `LangfuseMetricsCollector`
- [ ] Добавить `@observe` декораторы в VoyageService
- [ ] Добавить Qdrant metrics scraping
- [ ] Добавить Redis INFO collection

### Фаза 3: Baseline management
- [ ] Реализовать `BaselineManager`
- [ ] Создать `thresholds.yaml`
- [ ] Добавить Makefile targets
- [ ] Написать compare скрипт

### Фаза 4: Отчёты
- [ ] HTML отчёт с графиками (plotly)
- [ ] Slack/Telegram notification при регрессии
- [ ] Интеграция с GitHub Actions

### Фаза 5: Документация
- [ ] Обновить CLAUDE.md
- [ ] Добавить README в tests/baseline/
- [ ] Примеры использования

---

## 8. Примеры использования

### Локальная разработка

```bash
# 1. Запустить стек
docker compose -f docker-compose.dev.yml up -d

# 2. Дождаться healthy
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(langfuse|litellm)"

# 3. Прогнать smoke и установить как baseline
make baseline-smoke
make baseline-set TAG=local-baseline

# 4. Внести изменения в код...

# 5. Проверить на регрессии
make baseline-smoke
make baseline-compare BASELINE_TAG=local-baseline
```

### Pre-merge check

```bash
# На feature branch
git checkout feature/new-cache-strategy

# Прогнать тесты
make baseline-smoke
make baseline-load

# Сравнить с main
make baseline-compare BASELINE_TAG=main-latest

# Если всё ок — merge
```

### Nightly E2E

```bash
# Cron job или GitHub Actions scheduled
make e2e-test
make baseline-report
# → reports/baseline-20260128-030000.html
```

---

## 9. Метрики для дашборда

### Langfuse Dashboard (built-in)
- Traces over time
- Latency distribution
- Cost by model
- Token usage trends

### Custom metrics (через API)
- Cache hit rate trend
- Cold vs warm latency comparison
- Voyage API calls per query
- Qdrant vectors scanned distribution

---

## 10. Риски и митигации

| Риск | Митигация |
|------|-----------|
| Langfuse недоступен → тесты падают | Graceful degradation: логировать локально, сравнивать потом |
| Нестабильные метрики (variance) | Использовать p95 вместо avg, несколько прогонов |
| Baseline устаревает | Автоматическое обновление при merge в main |
| Слишком много false positives | Начать с широких thresholds, сужать постепенно |

---

## Appendix A: Langfuse API Reference

### GET /api/public/metrics/daily

```bash
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "http://localhost:3001/api/public/metrics/daily?limit=7"
```

Response:
```json
{
  "data": [
    {
      "date": "2026-01-28",
      "countTraces": 150,
      "countObservations": 450,
      "totalCost": 0.0523,
      "usage": [
        {
          "model": "gpt-4o-mini",
          "inputUsage": 12000,
          "outputUsage": 3000,
          "totalCost": 0.0523
        }
      ]
    }
  ]
}
```

### GET /api/public/metrics (v2)

```bash
curl -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  -G --data-urlencode 'query={
    "view": "observations",
    "metrics": [{"measure": "latency", "aggregation": "p95"}],
    "dimensions": [{"field": "name"}],
    "fromTimestamp": "2026-01-28T00:00:00Z",
    "toTimestamp": "2026-01-29T00:00:00Z"
  }' \
  "http://localhost:3001/api/public/metrics"
```

---

## Appendix B: Docker Services (после обновления)

| Сервис | Порт | Назначение |
|--------|------|------------|
| langfuse | 3001 | Web UI + API |
| langfuse-worker | - | Background processing |
| clickhouse | 8123, 9009 | Analytics storage |
| minio | 9090, 9091 | S3 events/media |
| redis-langfuse | 6380 | Langfuse queues |
| litellm | 4000 | LLM Gateway → Langfuse OTEL |
| redis | 6379 | App cache |
| qdrant | 6333 | Vector DB |
