W-INFRA: Написать планы реализации для issue #121, #122, #101, #105 (Infra-Perf + Gate stream)

Ты — воркер, пишущий ПЛАНЫ реализации (НЕ код). Для каждого issue:
1. Прочитай issue из GitHub: gh issue view {num} --json title,body,labels,milestone
2. Прочитай исходные файлы проекта, указанные ниже
3. Выполни ресерч через MCP tools (если указано)
4. Напиши план в docs/plans/2026-02-11-{topic}-plan.md
5. Залогируй прогресс

Рабочая директория: /repo

ФОРМАТ ПЛАНА (каждый файл):
- Заголовок: "# {Title} Implementation Plan"
- Goal: 1-2 предложения
- Architecture: какие модули затрагиваются
- Tech Stack: библиотеки, версии
- Issue: ссылка на GitHub issue
- Текущее состояние: таблица файлов с номерами строк, текущими значениями
- Шаги реализации: каждый шаг = 2-5 минут, точные файлы и строки, что менять
- Test Strategy: конкретные тест-файлы, что проверять
- Acceptance Criteria: измеримые критерии
- Effort Estimate: S/M/L + часы
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела для кода.

=== ISSUE #121: Redis SDK hardening ===

Файлы для чтения:
- telegram_bot/integrations/cache.py (CacheLayerManager.initialize, connection pool)
- telegram_bot/services/redis_monitor.py (RedisHealthMonitor)
- telegram_bot/preflight.py (preflight checks)
- pyproject.toml (redis dependency version)
- docker-compose.dev.yml (redis service config)

MCP TOOLS (обязательно):
- Context7: resolve-library-id(libraryName="redis-py", query="connection pool timeout retry health check") затем query-docs(libraryId, "async redis connection pool socket_timeout retry_on_timeout health_check_interval exponential backoff")
- Context7: query-docs(libraryId, "redis Retry ExponentialBackoff configuration example")

Выходной файл: docs/plans/2026-02-11-redis-hardening-plan.md

=== ISSUE #122: Qdrant timeout + FormulaQuery ===

Файлы для чтения:
- telegram_bot/services/qdrant.py (QdrantService, search methods)
- src/retrieval/search_engines.py (search variants)
- pyproject.toml (qdrant-client version)
- docker-compose.dev.yml (qdrant service config)

MCP TOOLS (обязательно):
- Context7: resolve-library-id(libraryName="qdrant-client", query="timeout query API FormulaQuery") затем query-docs(libraryId, "AsyncQdrantClient timeout configuration grpc options")
- Context7: query-docs(libraryId, "FormulaQuery server-side score boosting formula rescore")

Выходной файл: docs/plans/2026-02-11-qdrant-timeout-plan.md

=== ISSUE #101: Re-baseline latency + Go/No-Go gate ===

Файлы для чтения:
- scripts/validate_traces.py (trace validation runner)
- scripts/golden_queries.py (query goldset)
- telegram_bot/bot.py (bot entry, _write_langfuse_scores)
- Makefile (validate-traces-fast target)
- docs/plans/2026-02-11-parallel-execution-roadmap.md (gate criteria)

MCP TOOLS: не требуется (процесс валидации, локальный код)

План должен описать:
- Процедуру re-baseline (какие запросы, сколько, какие типы)
- Go/No-Go criteria (p50/p90 latency, cache hit, orphan traces %)
- Как фиксировать baseline trace IDs
- Contingency path если fail

Выходной файл: docs/plans/2026-02-11-re-baseline-plan.md

=== ISSUE #105: Close parent tracking issue ===

Файлы для чтения:
- gh issue view 105 --json title,body (для понимания scope)
- docs/plans/2026-02-11-parallel-execution-roadmap.md (зависимости)

MCP TOOLS: не требуется

План должен описать:
- Чеклист подзадач (какие issue должны быть закрыты)
- Верификация: что проверить перед закрытием
- Команда закрытия

Выходной файл: docs/plans/2026-02-11-latency-parent-close-plan.md

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-infra.log (APPEND mode, >> для каждой записи):
[START] timestamp Issue #N: description
[DONE] timestamp Issue #N: result summary
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-INFRA COMPLETE — проверь logs/worker-plan-infra.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документы
2. НЕ используй тройные бэктики в план-файлах — используй 4 пробела для кода
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана для соответствующего issue
