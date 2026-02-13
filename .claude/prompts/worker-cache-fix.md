W-CACHE-FIX: Fix user_id inconsistency + commit Task C/D for #163

Работай из /repo
Ветка: feat/163-semantic-cache-isolation (уже checkout)

ЗАДАЧИ (выполняй по порядку):

Task 1: Fix user_id default inconsistency in cache_check_node
- Файл: telegram_bot/graph/nodes/cache.py строка ~86
- Проблема: state.get("user_id", 0) использует default 0, а в cache_store_node user_id берётся как state.get("user_id", 0) (строка ~155) — ОК, но дефолт 0 не матчит None семантику в check_semantic/store_semantic
- Fix: заменить state.get("user_id", 0) на state.get("user_id") в cache_check_node (строка ~86), чтобы None передавался когда user_id отсутствует. check_semantic уже обрабатывает user_id=None (пропускает фильтр)
- Аналогично проверь cache_store_node — если user_id=0, store_semantic запишет "0" как tag. Лучше передавать None когда нет user_id
- В cache_store_node (строка ~155): state.get("user_id", 0) -> оставить 0 для store_conversation_batch (legacy), но для store_semantic передавать state.get("user_id") или user_id if user_id else None

Task 2: Commit unstaged Task C+D changes
- Unstaged changes уже в working tree (из stash apply):
  - telegram_bot/graph/nodes/cache.py: удаление store_conversation_batch из active path
  - tests/integration/test_graph_paths.py: обновлённые integration tests
  - tests/unit/graph/test_cache_nodes.py: test_does_not_call_store_conversation_batch
- НО: сначала убедись что Task 1 fix тоже включён в файлы
- Прогони тесты: uv run pytest tests/unit/graph/test_cache_nodes.py tests/unit/integrations/test_cache_layers.py tests/integration/test_graph_paths.py -v
- Если тесты прошли — один коммит:
  feat(cache): remove legacy LIST store + fix user_id consistency #163

Task 3: Финальная проверка
- uv run ruff check telegram_bot/graph/nodes/cache.py telegram_bot/integrations/cache.py
- uv run ruff format --check telegram_bot/graph/nodes/cache.py telegram_bot/integrations/cache.py
- uv run pytest tests/unit/graph/test_cache_nodes.py tests/unit/integrations/test_cache_layers.py tests/integration/test_graph_paths.py -v
- Убедись что все тесты зелёные

ПРАВИЛА:
1. git add ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Ссылка на #163 в коммите.

ТЕСТЫ:
- uv run pytest tests/unit/graph/test_cache_nodes.py -v
- uv run pytest tests/unit/integrations/test_cache_layers.py -v
- uv run pytest tests/integration/test_graph_paths.py -v
- НЕ запускай tests/ целиком

ЛОГИРОВАНИЕ в /repo/logs/worker-cache-fix.log (APPEND):
[START] timestamp Task N: description
[DONE] timestamp Task N: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:Claude3" "W-CACHE-FIX COMPLETE — проверь logs/worker-cache-fix.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:Claude3" Enter
ВАЖНО: Используй ИМЯ окна (Claude3), НЕ индекс.
