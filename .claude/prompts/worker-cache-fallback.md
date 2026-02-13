W-CACHE: Graceful embedding error fallback in cache_check_node + route_cache (#210)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans -- для пошагового выполнения задач
2. /requesting-code-review -- code review ПОСЛЕ завершения, ПЕРЕД коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) -- просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion -- финальная проверка перед коммитом

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для актуальной документации SDK/API
- Exa: web_search_exa(query) или get_code_context_exa(query) для поиска решений, примеров кода

ПЛАН: /repo/docs/plans/2026-02-12-bge-m3-retry-resilience-plan.md
Работай из /repo
Ветка: fix/210-bge-m3-retry-resilience (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ЗАДАЧА: Task 2 из плана -- Graceful Fallback in cache_check_node

Файлы для изменения:
- telegram_bot/graph/state.py (добавить embedding_error, embedding_error_type)
- telegram_bot/graph/nodes/cache.py (try/except вокруг embedding call)
- telegram_bot/graph/edges.py (route_cache checks embedding_error first)
- tests/unit/graph/test_cache_nodes.py (3 новых теста)
- tests/unit/graph/test_edges.py (1 новый тест)

ЧТО ДЕЛАТЬ (TDD по плану):

Step 1: Добавь тесты в tests/unit/graph/test_cache_nodes.py
- Класс TestCacheCheckEmbeddingError: 3 теста
  - test_embedding_error_sets_error_state (RemoteProtocolError -> embedding_error=True, response содержит "недоступен")
  - test_embedding_error_on_read_timeout (ReadTimeout -> embedding_error=True)
  - test_cached_embedding_skips_bge_call (cached embedding -> aembed_hybrid not called, embedding_error=False)
- Не забудь import httpx в начале файла

Step 2: Добавь тест в tests/unit/graph/test_edges.py
- В класс TestRouteCache добавь:
  - test_embedding_error_routes_to_respond (embedding_error=True, cache_hit=False -> "respond")

Step 3: Убедись что тесты ПАДАЮТ:
  uv run pytest tests/unit/graph/test_cache_nodes.py::TestCacheCheckEmbeddingError tests/unit/graph/test_edges.py::TestRouteCache::test_embedding_error_routes_to_respond -v

Step 4: Реализуй изменения:

4a. В telegram_bot/graph/state.py:
- В RAGState TypedDict добавь 2 поля (после retrieval_error_type):
    embedding_error: bool
    embedding_error_type: str | None
- В make_initial_state() добавь:
    "embedding_error": False,
    "embedding_error_type": None,

4b. В telegram_bot/graph/nodes/cache.py:
- Оберни секцию embedding (строки 66-77) в try/except Exception
- При ошибке: логируй, update span с ERROR level, верни dict с embedding_error=True, response с user-friendly сообщением
- Точный код fallback -- см. Task 2, Step 4 в плане

4c. В telegram_bot/graph/edges.py:
- В route_cache() добавь проверку embedding_error ПЕРЕД cache_hit:
    if state.get("embedding_error", False):
        return "respond"

Step 5: Убедись что тесты ПРОХОДЯТ:
  uv run pytest tests/unit/graph/test_cache_nodes.py tests/unit/graph/test_edges.py -v

Step 6: Lint:
  uv run ruff check telegram_bot/graph/state.py telegram_bot/graph/nodes/cache.py telegram_bot/graph/edges.py
  uv run ruff format --check telegram_bot/graph/state.py telegram_bot/graph/nodes/cache.py telegram_bot/graph/edges.py

Step 7: Коммит (ТОЛЬКО эти файлы):
  git add telegram_bot/graph/state.py telegram_bot/graph/nodes/cache.py telegram_bot/graph/edges.py tests/unit/graph/test_cache_nodes.py tests/unit/graph/test_edges.py
  git diff --cached --stat
  git commit -m "fix(cache): explicit embedding error route without false cache-hit metrics #210

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО: uv run pytest tests/unit/graph/test_cache_nodes.py tests/unit/graph/test_edges.py -v
- НЕ запускай tests/unit/graph/ целиком
- Маппинг:
  telegram_bot/graph/state.py -> tests/unit/graph/test_edges.py (state used there)
  telegram_bot/graph/nodes/cache.py -> tests/unit/graph/test_cache_nodes.py
  telegram_bot/graph/edges.py -> tests/unit/graph/test_edges.py

ПРАВИЛА:
1. git commit -- ТОЛЬКО конкретные файлы. НЕ git add -A. ПЕРЕД коммитом: git diff --cached --stat
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите
3. НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки

ЛОГИРОВАНИЕ в /repo/logs/worker-cache-fallback.log (APPEND):
Перед каждым шагом:
  echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-cache-fallback.log
После каждого шага:
  echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-cache-fallback.log
В конце:
  echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-cache-fallback.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-CACHE COMPLETE -- проверь logs/worker-cache-fallback.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Используй ИМЯ окна "ORCH", НЕ индекс.
