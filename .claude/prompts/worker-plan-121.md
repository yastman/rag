W-P121: Написать план реализации для issue #121 (Redis SDK hardening)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 121 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-redis-hardening-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/integrations/cache.py (CacheLayerManager.initialize — primary connection pool)
- telegram_bot/services/redis_monitor.py (RedisHealthMonitor connection)
- telegram_bot/preflight.py (preflight Redis checks)
- pyproject.toml (redis dependency version — line ~33)
- docker-compose.dev.yml (redis service config)
- src/cache/redis_semantic_cache.py (legacy evaluation cache)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Context7: resolve-library-id(libraryName="redis-py", query="async connection pool timeout retry health check") затем query-docs(libraryId, "redis asyncio connection pool socket_timeout retry_on_timeout health_check_interval Retry ExponentialBackoff")
- Context7: query-docs(libraryId, "redis Retry class ExponentialBackoff configuration async example")

ФОРМАТ ПЛАНА:
- Заголовок: "# Redis Hardening: Connection Params — Implementation Plan"
- Goal: 1-2 предложения
- Issue: https://github.com/yastman/rag/issues/121
- Текущее состояние: таблица ВСЕХ connection points (файл, строка, текущие параметры)
- Target параметры: socket_timeout, connect_timeout, retry, health_check, версия redis-py
- Шаги реализации: 2-5 минут каждый, точные файлы и строки
- Test Strategy: конкретные тест-файлы
- Acceptance Criteria: все параметры applied, тесты проходят
- Effort Estimate: S/M/L + часы
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-121.log (APPEND mode):
echo "[START] $(date +%H:%M:%S) Issue #121: redis hardening plan" >> logs/worker-plan-121.log
... работа ...
echo "[DONE] $(date +%H:%M:%S) Issue #121: plan written" >> logs/worker-plan-121.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-121.log

WEBHOOK (после завершения):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P121 COMPLETE — проверь logs/worker-plan-121.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана
