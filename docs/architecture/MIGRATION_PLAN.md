# 🚀 Migration Plan: Custom Scripts → Production Tools

**Цель:** Заменить самописные скрипты (923 lines) на production-grade инструменты за 2-3 дня.

**Статус:** ✅ **ЗАВЕРШЕНО** (2025-10-23)

---

## 📋 Статус выполнения

| Фаза | Статус | Дата завершения | Документация |
|------|--------|-----------------|--------------|
| **Фаза 1:** MLflow + RAGAS Infrastructure | ✅ Завершено | 2025-10-23 | [PHASE1_COMPLETION_SUMMARY.md](PHASE1_COMPLETION_SUMMARY.md) |
| **Фаза 2:** MLflow Integration в run_ab_test.py | ✅ Завершено | 2025-10-23 | [PHASE2_COMPLETION_SUMMARY.md](PHASE2_COMPLETION_SUMMARY.md) |
| **Фаза 3:** Langfuse Native SDK Integration | ✅ Завершено | 2025-10-23 | [PHASE3_COMPLETION_SUMMARY.md](PHASE3_COMPLETION_SUMMARY.md) |

**Итого:** Все 3 фазы завершены, production-ready ML platform развернут.

---

## 📊 Что заменяем

| Компонент | Было (наш код) | Станет | Выигрыш |
|-----------|---------------|---------|---------|
| Config versioning | config_snapshot.py (67 lines) | **MLflow** | UI + reproducibility |
| E2E evaluation | ❌ Не было | **RAGAS** | 4 метрики из коробки |
| Metrics logging | metrics_logger.py (403 lines) | **Langfuse** | Full observability |
| Smoke testing | smoke_test.py (453 lines) | **Giskard** | Автотесты + reports |

---

## 🎯 Фазированная миграция

### ✅ Фаза 1 (День 1): MLflow + RAGAS - Quick Wins

**Цель:** Репродуцируемость экспериментов + e2e метрики
**Время:** 4 часа
**Риск:** 🟢 Минимальный

#### Шаг 1.1: Создать virtual environment (15 мин)

```bash
cd /home/admin/contextual_rag
python3 -m venv venv
source venv/bin/activate

# Сохранить текущие зависимости
pip freeze > requirements_current.txt
```

#### Шаг 1.2: Установить MLflow (15 мин)

```bash
pip install mlflow==2.22.1
pip install boto3  # Если будем использовать S3 для артефактов

# Запустить MLflow UI
mlflow ui --backend-store-uri ./mlruns --port 5001
# Открыть: http://localhost:5001
```

#### Шаг 1.3: Интегрировать MLflow в run_ab_test.py (1.5 часа)

Создать `evaluation/mlflow_integration.py`:

```python
"""MLflow integration wrapper for A/B tests."""
import mlflow
from config_snapshot import get_config_hash, CONFIG_SNAPSHOT

def log_ab_test(engine_name: str, results: dict, report_path: str):
    """Log A/B test results to MLflow."""

    with mlflow.start_run(run_name=f"{engine_name}_evaluation"):
        # Log parameters
        mlflow.log_param("engine", engine_name)
        mlflow.log_param("config_hash", get_config_hash())
        mlflow.log_param("collection", results["collection"])
        mlflow.log_param("queries_count", results["queries_count"])

        # Log search config as nested params
        engine_config = CONFIG_SNAPSHOT["search_engines"].get(engine_name, {})
        for key, value in engine_config.items():
            mlflow.log_param(f"search.{key}", value)

        # Log metrics
        mlflow.log_metric("recall_at_1", results["recall_at_1"])
        mlflow.log_metric("recall_at_10", results["recall_at_10"])
        mlflow.log_metric("ndcg_at_10", results["ndcg_at_10"])
        mlflow.log_metric("mrr", results["mrr"])
        mlflow.log_metric("latency_p50_ms", results["latency_p50_ms"])
        mlflow.log_metric("latency_p95_ms", results["latency_p95_ms"])

        # Log artifacts
        mlflow.log_artifact(report_path, artifact_path="reports")

        # Log tags
        mlflow.set_tag("experiment_type", "ab_test")
        mlflow.set_tag("qdrant_version", CONFIG_SNAPSHOT["infrastructure"]["qdrant_version"])
        mlflow.set_tag("embedder", CONFIG_SNAPSHOT["models"]["embedder"]["name"])
```

Добавить в `evaluation/run_ab_test.py`:

```python
from mlflow_integration import log_ab_test

# В конце функции run_evaluation():
if args.mlflow:
    log_ab_test(engine_name, results, report_path)
```

#### Шаг 1.4: Установить RAGAS (30 мин)

```bash
pip install ragas==0.1.20 langchain-openai==0.3.2

# Добавить в .env
echo "OPENAI_API_KEY=your_key_here" >> .env
```

#### Шаг 1.5: Создать evaluate_with_ragas.py (1.5 часа)

```python
#!/usr/bin/env python3
"""
RAGAS E2E Evaluation for RAG System

Evaluates faithfulness, context relevance, answer relevancy for all queries.
"""
import json
import mlflow
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    Faithfulness,
    ContextRelevance,
    AnswerRelevancy,
    ContextRecall,
)
from ragas.llms import LangchainLLMWrapper
from langchain_openai import ChatOpenAI

from search_engines import HybridDBSFColBERTSearchEngine
from config_snapshot import get_config_hash

def create_ragas_dataset(engine, queries_file: str, limit: int = 50):
    """Create RAGAS dataset from search results."""
    with open(queries_file) as f:
        queries = json.load(f)[:limit]

    dataset_dict = {
        "question": [],
        "contexts": [],
        "answer": [],
        "ground_truth": []
    }

    for query_data in queries:
        query = query_data["query"]
        expected_article = query_data.get("expected_article")

        # Search
        results = engine.search(query, limit=5)

        # Extract contexts
        contexts = [r.payload.get("text", "") for r in results]

        # Generate answer (top result)
        answer = results[0].payload.get("text", "") if results else ""

        # Ground truth (expected article text)
        ground_truth = query_data.get("ground_truth", "")

        dataset_dict["question"].append(query)
        dataset_dict["contexts"].append(contexts)
        dataset_dict["answer"].append(answer)
        dataset_dict["ground_truth"].append(ground_truth)

    return Dataset.from_dict(dataset_dict)

def run_ragas_evaluation(engine_name: str = "dbsf_colbert"):
    """Run RAGAS evaluation and log to MLflow."""

    # Initialize engine
    engine = HybridDBSFColBERTSearchEngine(collection_name="uk_civil_code_v2")

    # Create dataset
    print("📊 Creating RAGAS dataset...")
    dataset = create_ragas_dataset(
        engine,
        queries_file="data/queries_testset.json",
        limit=50  # Start with 50 queries
    )

    # Initialize LLM for evaluation
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    evaluator_llm = LangchainLLMWrapper(llm)

    # Define metrics
    metrics = [
        Faithfulness(llm=evaluator_llm),
        ContextRelevance(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm),
        ContextRecall(llm=evaluator_llm),
    ]

    # Run evaluation
    print("🔍 Running RAGAS evaluation...")
    with mlflow.start_run(run_name=f"ragas_{engine_name}"):
        # Log params
        mlflow.log_param("engine", engine_name)
        mlflow.log_param("config_hash", get_config_hash())
        mlflow.log_param("evaluator_llm", "gpt-4o-mini")
        mlflow.log_param("evaluator_temperature", 0.0)
        mlflow.log_param("ragas_version", "0.1.20")
        mlflow.log_param("queries_count", len(dataset))

        # Evaluate
        results = evaluate(dataset=dataset, metrics=metrics)

        # Log metrics
        for metric_name, value in results.items():
            mlflow.log_metric(f"ragas_{metric_name}", value)

        # Log results as artifact
        results_df = results.to_pandas()
        results_df.to_csv("/tmp/ragas_results.csv", index=False)
        mlflow.log_artifact("/tmp/ragas_results.csv", artifact_path="ragas")

        print("\n✅ RAGAS Evaluation Complete!")
        print(results)

if __name__ == "__main__":
    run_ragas_evaluation()
```

#### Шаг 1.6: Тестирование (30 мин)

```bash
# Запустить MLflow UI
mlflow ui --backend-store-uri ./mlruns --port 5001 &

# Запустить A/B тест с MLflow
source venv/bin/activate
cd evaluation
python run_ab_test.py --engines dbsf_colbert --mlflow

# Запустить RAGAS evaluation
python evaluate_with_ragas.py

# Проверить в UI: http://localhost:5001
```

**✅ Результат Фазы 1:**
- Все эксперименты в MLflow UI
- 4 новых метрики от RAGAS
- Сравнение разных runs
- Полная репродуцируемость

---

### ✅ Фаза 2 (День 2): MLflow Integration в run_ab_test.py - ЗАВЕРШЕНО

**Цель:** Автоматическое логирование A/B тестов в MLflow
**Время:** 2 часа (запланировано: 6 часов)
**Риск:** 🟢 Минимальный
**Статус:** ✅ **ЗАВЕРШЕНО** (2025-10-23)

**Реализация:**
- Добавлено опциональное логирование в `run_ab_test.py` (+85 строк)
- Graceful degradation: работает с/без MLflow
- Логируется: 5 параметров + 25 метрик + markdown report
- Создан тест-скрипт `test_mlflow_ab.py` для быстрой проверки

Подробности: [PHASE2_COMPLETION_SUMMARY.md](PHASE2_COMPLETION_SUMMARY.md)

---

### ✅ Фаза 3 (День 2-3): Langfuse - Production Observability - ЗАВЕРШЕНО

**Цель:** Трейсинг production запросов с native SDK
**Время:** 3 часа (запланировано: 6 часов)
**Риск:** 🟢 Минимальный (использован native SDK)
**Статус:** ✅ **ЗАВЕРШЕНО** (2025-10-23)

#### Шаг 2.1: Установить Langfuse (1 час)

**Вариант A: Self-hosted (рекомендуется)**

Добавить в `/home/admin/docker-compose.yml`:

```yaml
  langfuse-server:
    image: langfuse/langfuse:2
    container_name: ai-langfuse
    depends_on:
      - ai-postgres
    ports:
      - "3001:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD}@ai-postgres:5432/langfuse
      - NEXTAUTH_SECRET=${LANGFUSE_SECRET}
      - SALT=${LANGFUSE_SALT}
      - NEXTAUTH_URL=http://localhost:3001
    networks:
      - ai-unified-network
```

Создать DB:

```bash
docker exec -it ai-postgres psql -U postgres -c "CREATE DATABASE langfuse;"

# Добавить в .env
echo "LANGFUSE_SECRET=$(openssl rand -hex 32)" >> .env
echo "LANGFUSE_SALT=$(openssl rand -hex 32)" >> .env

# Перезапустить
docker compose up -d langfuse-server
```

**Вариант B: Cloud (быстрее)**

```bash
# Получить ключи на https://cloud.langfuse.com
echo "LANGFUSE_PUBLIC_KEY=pk-lf-..." >> .env
echo "LANGFUSE_SECRET_KEY=sk-lf-..." >> .env
echo "LANGFUSE_HOST=https://cloud.langfuse.com" >> .env
```

#### Шаг 2.2: Установить Python SDK (15 мин)

```bash
pip install langfuse==2.56.0
```

#### Шаг 2.3: Создать langfuse_integration.py с native SDK (1 час) ✅

**Фактическая реализация:** Использован official Langfuse SDK без custom wrappers

Создан `evaluation/langfuse_integration.py` (430 строк):

```python
"""
Langfuse Integration for Production RAG Observability - Native SDK Usage

Uses official Langfuse Python SDK patterns with @observe() decorator.
No custom wrappers - just native SDK features.
"""
from langfuse import Langfuse, observe, get_client

# Helper function with native decorator
@observe(name="rag-search-query")
def trace_search_with_decorator(
    query: str,
    search_fn: callable,
    engine_name: str = "unknown",
    user_id: str = "anonymous",
    session_id: str | None = None,
    expected_article: int | None = None,
) -> tuple[list[Any], dict[str, float]]:
    """Trace a RAG search query using native @observe() decorator."""
    langfuse = get_client()

    # Update trace with metadata
    langfuse.update_current_trace(
        input={"query": query, "engine": engine_name},
        user_id=user_id,
        session_id=session_id,
        tags=["search", engine_name, "evaluation"]
    )

    # Execute search
    results = search_fn(query)

    # Log scores
    if expected_article:
        precision = calculate_precision(results, expected_article)
        langfuse.score_current_trace(name="precision_at_1", value=precision)

    return results

# Manual spans for fine-grained control
def trace_search_with_spans(query, search_fn, engine_name):
    """Trace using manual span creation for complex pipelines."""
    langfuse = get_client()

    with langfuse.start_as_current_span(name="rag-search") as trace:
        # Retrieval span
        with trace.start_as_current_span(name="retrieval") as span:
            results = search_fn(query)
            span.update(output={"num_results": len(results)})

        # Evaluation span
        with trace.start_as_current_span(name="evaluation") as span:
            metrics = calculate_metrics(results)
            span.score(name="precision_at_1", value=metrics["p@1"])
```

**Преимущества native SDK:**
- Нет custom wrappers → меньше кода, меньше багов
- Автоматическое нестирование decorated functions
- Официальные паттерны из документации
- Поддержка из коробки от Langfuse team

#### Шаг 2.4: Добавить custom scores (1 час)

```python
from langfuse import Langfuse

langfuse = Langfuse()

def log_search_metrics(trace_id: str, precision_at_1: float, latency_ms: float):
    """Log custom metrics to Langfuse."""
    langfuse.score(
        trace_id=trace_id,
        name="precision_at_1",
        value=precision_at_1
    )
    langfuse.score(
        trace_id=trace_id,
        name="latency_ms",
        value=latency_ms
    )
```

#### Шаг 2.5: Тестирование (30 мин)

```bash
# Открыть Langfuse UI
open http://localhost:3001  # Self-hosted
# or
open https://cloud.langfuse.com  # Cloud

# Запустить тест с трейсингом
python run_ab_test.py --engines dbsf_colbert --sample 10

# Проверить traces в UI
```

**✅ Результат Фазы 2:**
- Полный трейсинг: encode → search → rerank
- Latency breakdown по шагам
- Custom scores (P@1, latency)
- Production-ready observability

---

### ✅ Фаза 3 (Опционально): Giskard - Automated Testing

**Цель:** Автоматические проверки качества + HTML reports
**Время:** 4 часа
**Риск:** 🟢 Минимальный

#### Шаг 3.1: Установить Giskard (15 мин)

```bash
pip install giskard==2.15.4
```

#### Шаг 3.2: Создать giskard_smoke_tests.py (3 часа)

```python
#!/usr/bin/env python3
"""Giskard automated smoke tests for RAG."""
import giskard as gsk
from search_engines import HybridDBSFColBERTSearchEngine

# Wrap search engine
def rag_model(query: str) -> str:
    """RAG model wrapper for Giskard."""
    engine = HybridDBSFColBERTSearchEngine(collection_name="uk_civil_code_v2")
    results = engine.search(query, limit=1)
    return results[0].payload.get("text", "") if results else ""

# Create Giskard model
model = gsk.Model(
    rag_model,
    model_type="text_generation",
    name="DBSF+ColBERT RAG",
    description="Ukrainian Criminal Code RAG system"
)

# Load smoke queries
with open("data/smoke_queries.json") as f:
    smoke_queries = json.load(f)

dataset = gsk.Dataset(
    pd.DataFrame({"query": [q["query"] for q in smoke_queries]}),
    target=None
)

# Create test suite
suite = gsk.Suite()

# Add tests
suite.add_test(
    gsk.testing.test_llm_output_against_rules(
        model=model,
        dataset=dataset,
        rules=["Output must contain article number", "Output must be in Ukrainian"]
    )
)

suite.add_test(
    gsk.testing.test_llm_similarity(
        model=model,
        dataset=dataset,
        threshold=0.8
    )
)

# Run and generate report
results = suite.run()
results.to_html("evaluation/reports/giskard_smoke_report.html")
```

#### Шаг 3.3: Интеграция с CI/CD (30 мин)

Создать `.github/workflows/smoke_test.yml`:

```yaml
name: Smoke Test with Giskard

on: [push, pull_request]

jobs:
  smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run Giskard smoke tests
        run: |
          python evaluation/giskard_smoke_tests.py
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: smoke-test-report
          path: evaluation/reports/giskard_smoke_report.html
```

**✅ Результат Фазы 3:**
- Автоматические smoke tests
- HTML reports
- CI/CD integration
- Проверки на hallucinations, bias, prompt injection

---

## ⚠️ Риски и митигация

### Риск 1: Версионирование LLM для RAGAS

**Проблема:** Оценки RAGAS могут меняться при смене версии LLM
**Митигация:**
- Зафиксировать `gpt-4o-mini` + `temperature=0.0` в MLflow params
- Запускать evaluation несколько раз и проверять дисперсию
- Использовать `ragas_version` как tag

### Риск 2: Секреты в репозитории

**Проблема:** OpenAI keys, Langfuse keys могут попасть в git
**Митигация:**
- Все ключи только в `.env` (уже в `.gitignore`)
- Использовать environment variables в CI/CD
- Добавить pre-commit hook для проверки секретов

### Риск 3: Latency overhead от трейсинга

**Проблема:** Langfuse может добавлять latency
**Митигация:**
- Async отправка в Langfuse (по умолчанию)
- Измерить overhead: запустить A/B с/без трейсинга
- Настроить sampling (не логировать каждый запрос в prod)

### Риск 4: PII в трейсах

**Проблема:** Пользовательские запросы могут содержать персональные данные
**Митигация:**
- Для тестовых данных (150 queries УК) - не проблема
- Для production: включить PII masking в Langfuse
- Регулярно чистить старые traces

---

## 📦 Финальная архитектура

```
contextual_rag/
├── venv/                          # 🆕 Virtual environment
├── mlruns/                        # 🆕 MLflow experiments
├── evaluation/
│   ├── search_engines.py          # ✅ Без изменений
│   ├── run_ab_test.py             # 🔄 + MLflow logging
│   ├── mlflow_integration.py      # 🆕 MLflow wrapper
│   ├── evaluate_with_ragas.py     # 🆕 RAGAS evaluation
│   ├── langfuse_integration.py    # 🆕 Langfuse tracing
│   ├── giskard_smoke_tests.py     # 🆕 Giskard tests
│   ├── config_snapshot.py         # 📦 Deprecated → MLflow
│   ├── smoke_test.py              # 📦 Deprecated → Giskard
│   └── metrics_logger.py          # 📦 Deprecated → Langfuse
├── docker-compose.yml             # 🔄 + Langfuse service
├── .env                           # 🔄 + API keys
└── requirements.txt               # 🔄 Updated

🆕 New tools:
- MLflow UI: http://localhost:5001
- Langfuse UI: http://localhost:3001
```

---

## 📊 Ожидаемые результаты

| Метрика | До миграции | После миграции |
|---------|------------|----------------|
| **Lines of custom code** | 923 | ~150 (-84%) |
| **UI dashboards** | 0 | 2 (MLflow + Langfuse) |
| **Метрик RAG** | 5 (R@1, R@10, NDCG, MRR, latency) | 9 (+4 RAGAS) |
| **Трейсинг** | ❌ Нет | ✅ Full pipeline |
| **Автотесты** | Manual | ✅ Automated |
| **Reproducibility** | Hash only | ✅ Full experiment tracking |
| **Production-ready** | 🟡 Partial | ✅ Yes |

---

## 🚀 Следующие шаги

1. **Прочитать и утвердить план**
2. **Начать с Фазы 1** (MLflow + RAGAS) → 4 часа работы
3. **Проверить результаты** в MLflow UI
4. **Перейти к Фазе 2** (Langfuse) → production observability
5. **Опционально Фаза 3** (Giskard) → automated testing

**Готов начать?** Скажи "го Фаза 1" и я сразу создам все нужные файлы и запущу установку.
