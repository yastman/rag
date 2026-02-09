Анализ покрытия тестами Docker сервисов и их фич.

Работай из /repo

КОНТЕКСТ — полный стек:

Сервис bge-m3 (services/bge-m3-api/):
  Файлы: app.py (FastAPI), config.py
  Endpoints: /health, /encode/dense, /encode/sparse, /encode/colbert, /encode/hybrid, /rerank, /metrics
  Фичи: Dense 1024-dim, Sparse BM25, ColBERT multi-vector, MaxSim reranking, FP16, Prometheus metrics
  Dockerfile: services/bge-m3-api/Dockerfile, port 8000, 4GB RAM

Сервис user-base (services/user-base/):
  Файлы: main.py (FastAPI)
  Endpoints: /health, /embed, /embed_batch
  Фичи: deepvk/USER2-base 768-dim Russian embeddings, semantic cache support
  Dockerfile: services/user-base/Dockerfile, port 8003, 2GB RAM

Сервис bot (telegram_bot/):
  Handlers: /start, /help, /clear, /stats, /cache_stats, default message
  Middlewares: ThrottlingMiddleware (1.5s), ErrorHandlerMiddleware
  Preflight: redis (CRITICAL), qdrant (CRITICAL), bge_m3 (CRITICAL), litellm (OPTIONAL), langfuse (OPTIONAL)
  Services: 18 modules (cache, llm, qdrant, retriever, query_analyzer, etc.)
  Dockerfile: telegram_bot/Dockerfile

Сервис ingestion (src/ingestion/unified/):
  CLI: preflight, bootstrap, run, status, reprocess
  Flow: CocoIndex sources.LocalFile -> QdrantHybridTarget
  Manifest: content-hash -> stable UUID
  State: Postgres (indexed/failed/dlq)
  Dockerfile: Dockerfile.ingestion

Infrastructure:
  postgres (pgvector:pg17) port 5432
  redis (8.4.0) port 6379, 512MB, volatile-lfu
  qdrant (v1.16) port 6333
  litellm (v1.81.3) port 4000, fallback chain: Cerebras -> Groq -> OpenAI
  langfuse (3.150.0) port 3001
  docling port 5001

ЗАДАНИЕ:

1. Для каждого сервиса проверь покрытие тестами:
   - Прочитай tests/unit/ и найди тесты для каждого сервиса
   - Прочитай tests/smoke/ и найди smoke тесты
   - Прочитай tests/chaos/ и tests/e2e/

2. Для каждого endpoint/фичи отметь: покрыт тестом или нет

3. Запиши результат в /repo/logs/docker-coverage-report.txt

Формат:

DOCKER SERVICES TEST COVERAGE

Для каждого сервиса:
  Service: {name}
  Dockerfile: {path}
  Endpoints/Features:
    /health — unit: YES/NO, smoke: YES/NO
    /encode/dense — unit: YES/NO, smoke: YES/NO
    ...
  Gap: что не покрыто

RECOMMENDATIONS
Приоритетный список что тестировать

Логирование в /repo/logs/worker-docker-coverage.log (APPEND):
[START] timestamp Docker coverage analysis
[DONE] timestamp Analysis complete
[COMPLETE] timestamp Worker finished

Webhook — после завершения выполни две отдельные bash команды:
Первая: TMUX="" tmux send-keys -t "claude:1" "W-DOCKER-COV COMPLETE"
Вторая (через пол секунды): sleep 0.5 && TMUX="" tmux send-keys -t "claude:1" Enter
