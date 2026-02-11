W-REDIS: Redis hardening (#121)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-11-redis-hardening-plan.md
Работай из /repo

ЗАДАЧИ (выполняй по плану):
- Task 1: Bump redis>=7.1.0 в pyproject.toml L33, затем uv lock
- Task 2: Harden CacheLayerManager в telegram_bot/integrations/cache.py L132-138
  Добавить imports: from redis.backoff import ExponentialBackoff; from redis.retry import Retry
  Заменить socket_timeout=2 на 5, добавить retry_on_timeout=True, retry=Retry(ExponentialBackoff(), 3), health_check_interval=30
  Написать тест test_initialize_uses_hardened_connection_params
- Task 3: Update RedisHealthMonitor в telegram_bot/services/redis_monitor.py L44-50
  Те же параметры: retry_on_timeout, retry, health_check_interval
- Task 4: ruff check + ruff format
- Task 5: Запустить тесты

ТЕСТЫ (строго по файлам):
  uv run pytest tests/unit/integrations/test_cache_layers.py -v
- Маппинг:
  telegram_bot/integrations/cache.py -> tests/unit/integrations/test_cache_layers.py
  telegram_bot/services/redis_monitor.py -> нет отдельных тестов
- Финальная проверка: uv run ruff check telegram_bot/integrations/cache.py telegram_bot/services/redis_monitor.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Коммит: fix(redis): harden connection params — timeout/retry/health_check (#121)

ЛОГИРОВАНИЕ в /repo/logs/worker-redis.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-redis.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-redis.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-redis.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:2" "W-REDIS COMPLETE — проверь logs/worker-redis.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:2" Enter
