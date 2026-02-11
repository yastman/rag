W-P1-QDRANT: Fix #117 qdrant error vs no-results (TDD)

SKILLS (обязательно вызови):
1. /test-driven-development — RED-GREEN-REFACTOR цикл
2. /executing-plans — для пошагового выполнения
3. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-10-issue120-umbrella-execution.md
Работай из /home/user/projects/rag-fresh. Ты на ветке fix/issue120-umbrella. Читай Task 4.3 в плане.

ЗАДАЧА: #117 — Qdrant error vs no-results

Проблема: pipeline не различает "Qdrant вернул 0 результатов" от "Qdrant упал с ошибкой".
Нужен per-call meta signal без shared mutable state.

ШАГИ (TDD):

Step 1: Прочитай текущий код
- telegram_bot/services/qdrant.py (весь файл — hybrid_search_rrf метод)
- telegram_bot/graph/nodes/retrieve.py (как вызывается search)
- telegram_bot/graph/state.py (RAGState)
- tests/unit/test_qdrant_service.py (существующие тесты)
- tests/unit/graph/test_retrieve_node.py (существующие тесты)

Step 2: RED — напиши падающие тесты
Создай tests/unit/test_qdrant_error_signal.py с 2 тестами:
- test_backend_exception_returns_error_meta: qdrant exception -> backend_error=True, error_type заполнен
- test_empty_results_returns_no_error: genuine empty -> backend_error=False
Используй Context7 для qdrant-client API (AsyncQdrantClient, exceptions).
Запусти: uv run pytest tests/unit/test_qdrant_error_signal.py -v
Ожидание: FAIL (сигнал backend_error ещё не реализован)

Step 3: GREEN — реализуй
В telegram_bot/services/qdrant.py:
- Добавь return_meta: bool = False параметр в hybrid_search_rrf
- Если return_meta=False: текущий контракт list[dict] (backwards compatible)
- Если return_meta=True: возвращай (results, meta) с backend_error, error_type, error_message

В telegram_bot/graph/nodes/retrieve.py:
- Вызывай hybrid_search_rrf(..., return_meta=True)
- Сохраняй в state: retrieval_backend_error, retrieval_error_type

В telegram_bot/graph/state.py:
- Добавь новые Optional поля в RAGState

Step 4: Запусти тесты
uv run pytest tests/unit/test_qdrant_error_signal.py -v
uv run pytest tests/unit/test_qdrant_service.py tests/unit/graph/test_retrieve_node.py -q
Ожидание: ВСЕ зелёные

Step 5: Lint + commit
uv run ruff check telegram_bot/services/qdrant.py telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/state.py tests/unit/test_qdrant_error_signal.py --output-format=concise
git add telegram_bot/services/qdrant.py telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/state.py tests/unit/test_qdrant_error_signal.py
Commit с "Closes #117"

ТЕСТЫ (строго по файлам):
- tests/unit/test_qdrant_error_signal.py (новый)
- tests/unit/test_qdrant_service.py (regression)
- tests/unit/graph/test_retrieve_node.py (regression)
- НЕ запускай tests/ целиком

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id("qdrant-client", "AsyncQdrantClient exceptions error handling") затем query-docs
- Exa: get_code_context_exa("qdrant python client error handling backend_error meta")

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Каждый commit message через HEREDOC формат.
4. TDD: НЕТ кода без падающего теста сначала.
5. SDK-first: используй qdrant-client SDK, НЕ raw HTTP.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-p1-qdrant.log (APPEND):
Каждое действие логируй через: echo "[TAG] $(date +%H:%M:%S) message" >> /home/user/projects/rag-fresh/logs/worker-p1-qdrant.log
Теги: [START], [DONE], [ERROR], [COMPLETE]
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker P1-QDRANT finished" >> /home/user/projects/rag-fresh/logs/worker-p1-qdrant.log

После завершения ВСЕХ задач выполни ДВЕ bash команды:
1. TMUX="" tmux send-keys -t "claude:1" "W-P1-QDRANT COMPLETE — проверь logs/worker-p1-qdrant.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
