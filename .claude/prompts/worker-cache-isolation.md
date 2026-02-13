W-CACHE: Semantic Cache Isolation — allowlist guard + per-user filters + legacy LIST cleanup

SKILLS (обязательно вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения задач
2. /requesting-code-review — code review ПОСЛЕ завершения каждой таски, ПЕРЕД коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion — финальная проверка перед коммитом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-semantic-cache-isolation-plan.md
Работай из /home/user/projects/rag-fresh. Ветка: feat/159-memory-observability-scores (или создай новую feat/163-semantic-cache-isolation от main если нужно).

ЗАДАЧИ (выполняй по порядку):

Task A: Add semantic cache allowlist guard
- Файлы: telegram_bot/graph/nodes/cache.py, tests/unit/graph/test_cache_nodes.py
- Добавь allowlist constant: CACHEABLE_QUERY_TYPES = {"FAQ", "ENTITY", "STRUCTURED"}
- В cache_check_node: skip check_semantic для non-allowlisted types
- В cache_store_node: skip store_semantic для non-allowlisted types
- TDD: сначала напиши падающие тесты (GENERAL не должен вызывать check_semantic / store_semantic), потом реализуй
- Коммит после прохождения тестов

Task B: Add per-user isolation to semantic cache (SDK filters)
- Файлы: telegram_bot/integrations/cache.py, telegram_bot/graph/nodes/cache.py, tests/unit/integrations/test_cache_layers.py, tests/unit/graph/test_cache_nodes.py
- SemanticCache(filterable_fields=...) добавь user_id tag
- Extend check_semantic(..., user_id: int) и store_semantic(..., user_id: int)
- Build combined Tag filter on check (user_id + language, optionally query_type)
- Pass state["user_id"] from graph nodes into cache calls
- TDD: тест что одинаковый prompt от разных user_id НЕ cross-hit, тест что тот же user_id hits
- Коммит после прохождения тестов

Task C: Integration path validation
- Файлы: tests/integration/test_graph_paths.py
- Тест: GENERAL query bypasses semantic cache even when mock cache has a candidate hit
- Тест: allowlisted query still uses semantic cache as expected
- Коммит после прохождения тестов

Task D: Legacy Redis LIST cleanup in runtime path
- Файлы: telegram_bot/graph/nodes/cache.py, tests/unit/graph/test_cache_nodes.py
- Remove store_conversation_batch(...) call from active graph path
- Keep memory source single: checkpointer
- TDD: тест что store_conversation_batch не вызывается
- Коммит после прохождения тестов

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для актуальной документации RedisVL SemanticCache (filterable_fields, Tag filters)
- Exa: web_search_exa(query) или get_code_context_exa(query) для поиска решений по redisvl semantic cache filtering

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО тесты для файлов которые ты изменил:
  uv run pytest tests/unit/graph/test_cache_nodes.py -v
  uv run pytest tests/unit/integrations/test_cache_layers.py -v
  uv run pytest tests/integration/test_graph_paths.py -v
- НЕ запускай tests/ целиком, НЕ запускай tests/unit/ целиком
- Маппинг source -> test:
  telegram_bot/graph/nodes/cache.py -> tests/unit/graph/test_cache_nodes.py
  telegram_bot/integrations/cache.py -> tests/unit/integrations/test_cache_layers.py
  graph paths -> tests/integration/test_graph_paths.py
- Используй --lf для перезапуска только упавших
- Финальная проверка: uv run ruff check telegram_bot/graph/nodes/cache.py telegram_bot/integrations/cache.py && uv run ruff format --check telegram_bot/graph/nodes/cache.py telegram_bot/integrations/cache.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. ПЕРЕД реализацией фильтров RedisVL — Context7 для актуальной документации SemanticCache.
4. GitHub issue: #163. В каждом коммите ссылайся на #163.
5. Создай ветку feat/163-semantic-cache-isolation от main если текущая ветка другая.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-cache-isolation.log (APPEND):
[START] timestamp Task N: description
[DONE] timestamp Task N: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:Claude3" "W-CACHE COMPLETE — проверь logs/worker-cache-isolation.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:Claude3" Enter
ВАЖНО: Используй ИМЯ окна (Claude3), НЕ индекс. Индекс сдвигается при kill-window.
