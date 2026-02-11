W-P0-TESTS: Fix 3 P0 test issues (#115, #112, #113)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-10-issue120-umbrella-execution.md
Работай из /repo. Ты на ветке fix/issue120-umbrella.

ЗАДАЧИ (выполняй по порядку):

Task 1.1 (#115): Cross-test pollution sys.modules
- Прочитай план Task 1.1 целиком
- Отредактируй tests/unit/test_redis_semantic_cache.py: замени top-level sys.modules mock на save/restore pattern
- Запусти тесты: uv run pytest tests/unit/test_redis_semantic_cache.py tests/unit/test_vectorizers.py -q
- Lint: uv run ruff check tests/unit/test_redis_semantic_cache.py --output-format=concise
- Commit: git add tests/unit/test_redis_semantic_cache.py && commit с "Closes #115"

Task 1.2 (#112): test_bot_handlers Langfuse API
- Прочитай план Task 1.2 целиком
- Сначала прочитай telegram_bot/bot.py:226-274 чтобы понять текущий контракт handle_query
- Отредактируй tests/unit/test_bot_handlers.py: замени test_handle_query_passes_langfuse_handler и test_handle_query_no_langfuse
- Запусти: uv run pytest tests/unit/test_bot_handlers.py -q
- Проверь: grep -r "create_langfuse_handler" tests/ (должно быть пусто)
- Lint: uv run ruff check tests/unit/test_bot_handlers.py --output-format=concise
- Commit: git add tests/unit/test_bot_handlers.py && commit с "Closes #112"

Task 1.3 (#113): test_graph_paths GraphConfig mocks
- Прочитай план Task 1.3 целиком
- Отредактируй tests/integration/test_graph_paths.py: добавь typed fields в _make_mock_graph_config
- Запусти: uv run pytest tests/integration/test_graph_paths.py -v
- Lint: uv run ruff check tests/integration/test_graph_paths.py --output-format=concise
- Commit: git add tests/integration/test_graph_paths.py && commit с "Closes #113"

ТЕСТЫ (строго по файлам):
- Task 1.1: tests/unit/test_redis_semantic_cache.py + tests/unit/test_vectorizers.py
- Task 1.2: tests/unit/test_bot_handlers.py
- Task 1.3: tests/integration/test_graph_paths.py
- НЕ запускай tests/ целиком, НЕ запускай tests/unit/ целиком

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для актуальной документации SDK/API
- Exa: web_search_exa(query) или get_code_context_exa(query) для поиска решений

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Каждый commit message через HEREDOC формат.
4. Если тест падает — дебажь и фикси, не пропускай.

ЛОГИРОВАНИЕ в /repo/logs/worker-p0-tests.log (APPEND):
Каждое действие логируй через: echo "[TAG] $(date +%H:%M:%S) message" >> /repo/logs/worker-p0-tests.log
Теги: [START], [DONE], [ERROR], [COMPLETE]
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker P0-TESTS finished" >> /repo/logs/worker-p0-tests.log

После завершения ВСЕХ задач выполни ДВЕ bash команды:
1. TMUX="" tmux send-keys -t "claude:1" "W-P0-TESTS COMPLETE — проверь logs/worker-p0-tests.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
