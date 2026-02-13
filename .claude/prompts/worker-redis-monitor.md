W-REDIS: Checkpoint key growth monitoring in RedisHealthMonitor (Task 3 from plan)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-12-memory-observability-plan.md
Работай из /repo. Tasks 1, 2, 4, 5 выполняются другим воркером, НЕ трогай bot.py и test_bot_scores.py.

ЗАДАЧА (TDD: сначала падающий тест, потом минимальная реализация):

Task 3: Checkpoint key count в RedisHealthMonitor + тесты
  - Файлы: telegram_bot/services/redis_monitor.py, tests/unit/services/test_redis_monitor.py (новый файл)
  - Прочитай telegram_bot/services/redis_monitor.py ПОЛНОСТЬЮ перед началом работы
  - Проверь структуру tests/unit/services/ — создай __init__.py если нужно
  - Напиши тест: test_check_health_scans_all_checkpoint_keys_and_alerts_on_growth (см. план)
  - Запусти тест — убедись что FAIL
  - Реализуй:
    1. CHECKPOINT_GROWTH_WARN_DELTA = 1 (константа)
    2. self._prev_checkpoint_count: int | None = None (в __init__)
    3. Checkpoint key SCAN loop в _check_health() (cursor iteration until 0)
    4. Growth warning log
  - Запусти: uv run pytest tests/unit/services/test_redis_monitor.py -v
  - Коммит: feat(observability): checkpoint key growth monitoring in RedisHealthMonitor #159

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для актуальной документации SDK/API
- Exa: web_search_exa(query) или get_code_context_exa(query) для поиска решений, примеров кода, свежих best practices

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО: uv run pytest tests/unit/services/test_redis_monitor.py -v
- НЕ запускай tests/ целиком
- Маппинг: telegram_bot/services/redis_monitor.py -> tests/unit/services/test_redis_monitor.py
- Финальная проверка: uv run pytest tests/unit/services/test_redis_monitor.py -v && uv run ruff check telegram_bot/services/redis_monitor.py tests/unit/services/test_redis_monitor.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. НЕ трогать bot.py, test_bot_scores.py, memory.py — другой воркер или deferred
4. Conventional commits: feat(observability): ... #159

ЛОГИРОВАНИЕ в /repo/logs/worker-redis-monitor.log (APPEND):
В начале Task: echo "[START] $(date +%H:%M:%S) Task 3: checkpoint key growth monitoring" >> /repo/logs/worker-redis-monitor.log
По завершении Task: echo "[DONE] $(date +%H:%M:%S) Task 3: result" >> /repo/logs/worker-redis-monitor.log
После всех задач: echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-redis-monitor.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:Claude" "W-REDIS COMPLETE — проверь logs/worker-redis-monitor.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:Claude" Enter
ВАЖНО: Используй ИМЯ окна "Claude", НЕ индекс. Индекс сдвигается при kill-window.
