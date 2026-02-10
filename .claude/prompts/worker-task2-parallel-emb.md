W-EMB: Parallel Dense+Sparse Embeddings (Task 2)

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-10-latency-phase2-impl.md
Работай из /home/user/projects/rag-fresh
Ветка: fix/issue-91-ci-smoke-remediation (уже checkout)

ЗАДАЧА: Task 2 — Parallel Dense+Sparse Embeddings in retrieve_node

Выполняй шаги СТРОГО по плану (Steps 1-3):

1. Добавь тест test_parallel_embeddings_after_rewrite в tests/unit/graph/test_retrieve_node.py
   - Тест проверяет что оба embeddings вызваны при query_embedding=None
2. Рефакторинг retrieve_node (telegram_bot/graph/nodes/retrieve.py):
   - Добавь sparse_vector: Any = None после dense_vector = state.get(...)
   - При dense_vector is None AND embeddings is not None:
     a. Проверь кэш dense embedding
     b. Если кэш пуст: asyncio.gather для _get_dense() + _get_sparse()
   - Ниже: if sparse_vector is None: (стандартный путь для НЕ rewrite)
3. Запусти тесты: uv run pytest tests/unit/graph/test_retrieve_node.py -v
4. Commit с сообщением из плана

ВАЖНО — точная структура кода:
- import asyncio внутри if-блока (не на уровне модуля — он нужен только для re-embed пути)
- sparse_vector инициализируй как None в начале функции
- Проверку "if sparse_vector is None:" для Step 2 используй вместо прямого вызова

ФАЙЛЫ которые ты редактируешь:
- telegram_bot/graph/nodes/retrieve.py (ОСНОВНОЙ)
- tests/unit/graph/test_retrieve_node.py (тест)

НЕ ТРОГАЙ другие файлы!

ПРАВИЛА:
1. ТЕСТЫ — только test_retrieve_node.py. НЕ запускай весь tests/unit/
2. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
4. После каждого Edit используй grep для проверки что изменение применилось.
5. Используй uv run pytest (не просто pytest).

MCP TOOLS:
- ПЕРЕД реализацией внешних SDK/API используй MCP Context7 (resolve-library-id, query-docs) для актуальной документации
- Для поиска решений и best practices используй MCP Exa (web_search_exa, get_code_context_exa)

ВЕРИФИКАЦИЯ перед коммитом:
- uv run pytest tests/unit/graph/test_retrieve_node.py -v
- uv run ruff check telegram_bot/graph/nodes/retrieve.py --fix
- uv run ruff format telegram_bot/graph/nodes/retrieve.py

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-parallel-emb.log (APPEND):
[START] timestamp Task 2: Parallel Embeddings
[DONE] timestamp Task 2: result summary
[COMPLETE] timestamp Worker finished

После завершения ВСЕХ задач выполни ДВЕ bash команды:
1. TMUX="" tmux send-keys -t "claude:6" "W-EMB COMPLETE — проверь logs/worker-parallel-emb.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:6" Enter
