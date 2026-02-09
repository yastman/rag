W-PREFLIGHT: Unit тесты для telegram_bot/preflight.py

GitHub Issue: #52 — test: cover Docker services critical test gaps
Работай из /home/user/projects/rag-fresh

SKILLS (обязательно вызови):
1. /test-driven-development — RED -> GREEN -> REFACTOR
2. /verification-before-completion — проверка после написания

Шаги:

1. Прочитай telegram_bot/preflight.py — все функции и классы:
   - _check_redis_deep(settings) -> dict
   - _verify_cache_synthetic(redis_client, settings) -> dict
   - _check_single_dep(dep_name, settings, dep_config) -> dict
   - check_dependencies(settings) -> dict (main orchestrator)
   - PreflightError (SystemExit subclass)
   - DEPENDENCY_MAP dict

2. Прочитай существующие тесты в tests/unit/test_bot*.py — пойми паттерны

3. Создай tests/unit/test_preflight.py:

   Тесты (все async, используй AsyncMock для httpx/redis):

   a) _check_redis_deep:
      - success: mock redis с INFO (used_memory, connected_clients, redis_version, maxmemory_policy)
      - failure: redis.ping() raises ConnectionError -> status fail
      - wrong eviction: policy != volatile-lfu -> warning в details

   b) _verify_cache_synthetic:
      - success: write/read/ttl/delete работает для всех 5 префиксов
      - failure: redis.set raises -> status fail с описанием

   c) _check_single_dep:
      - redis: вызывает _check_redis_deep
      - qdrant: mock httpx GET -> 200 -> status ok
      - bge_m3: mock httpx GET -> 200 -> status ok
      - litellm: mock httpx GET -> 200 -> status ok
      - langfuse: mock httpx GET -> 200 -> status ok
      - unknown dep: raises KeyError или возвращает fail

   d) check_dependencies:
      - all pass: возвращает dict со всеми deps, overall=True
      - critical fail: redis fails -> raises PreflightError
      - optional fail: langfuse fails -> overall=True, langfuse status=fail
      - retry logic: first attempt fail, second pass -> overall=True

   e) PreflightError:
      - isinstance(PreflightError(), SystemExit)
      - message содержит failed dep name

4. Запусти: uv run pytest tests/unit/test_preflight.py -v
5. Фикси пока все не зелёные

Правила:
- git add tests/unit/test_preflight.py
- git commit -m "test(bot): add unit tests for preflight dependency checks

Covers _check_redis_deep, _verify_cache_synthetic, _check_single_dep,
check_dependencies retry logic, and PreflightError. Closes #52 (partial)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
- Тесты ТОЛЬКО свои: tests/unit/test_preflight.py

Логирование в /home/user/projects/rag-fresh/logs/worker-preflight-tests.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook — после завершения выполни две отдельные bash команды:
Первая: TMUX="" tmux send-keys -t "claude:1" "W-PREFLIGHT COMPLETE"
Вторая (через пол секунды): sleep 0.5 && TMUX="" tmux send-keys -t "claude:1" Enter
