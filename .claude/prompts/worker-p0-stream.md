W-P0-STREAM: Fix #114 streaming fallback duplicate response (TDD)

SKILLS (обязательно вызови):
1. /test-driven-development — RED-GREEN-REFACTOR цикл
2. /executing-plans — для пошагового выполнения
3. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-10-issue120-umbrella-execution.md
Работай из /repo. Ты на ветке fix/issue120-umbrella. Читай Task 1.4 в плане.

ЗАДАЧА: #114 — Streaming fallback duplicate response

Проблема: в generate.py:221-261, если _generate_streaming отправил partial chunks юзеру но потом упал,
response_sent остаётся False. Fallback генерирует новый ответ, respond_node отправляет его как НОВОЕ сообщение.
Юзер видит: partial streamed text + полный новый ответ = дубликат.

ШАГИ (TDD):

Step 1: Прочитай текущий код
- telegram_bot/graph/nodes/generate.py (весь файл, фокус на строки 200-270)
- telegram_bot/graph/nodes/respond.py (как используется response_sent)
- tests/unit/graph/test_generate_node.py (существующие тесты)

Step 2: RED — напиши падающие тесты
В tests/unit/graph/test_generate_node.py добавь 2 теста:
- test_stream_error_before_visible_output: стрим падает ДО первого user-visible chunk -> response_sent=False
- test_stream_error_after_visible_output: стрим падает ПОСЛЕ partial delivery -> fallback edit_text + response_sent=True
Запусти: uv run pytest tests/unit/graph/test_generate_node.py -k "stream_error" -v
Ожидание: минимум 1 тест КРАСНЫЙ

Step 3: GREEN — реализуй fix
В telegram_bot/graph/nodes/generate.py:
- Введи StreamingPartialDeliveryError (или аналог) с ссылкой на sent_msg
- В fallback блоке: если partial delivery была -> edit_text того же сообщения + response_sent=True
- Если partial delivery НЕ было -> response_sent=False (respond_node отправит)
- НЕ ломай non-streaming path

Step 4: Запусти тесты
uv run pytest tests/unit/graph/test_generate_node.py -k "stream_error" -v
Ожидание: ВСЕ зелёные

Step 5: Regression
uv run pytest tests/integration/test_graph_paths.py -v
uv run pytest tests/unit/graph/test_generate_node.py -v
Ожидание: ВСЕ зелёные

Step 6: Lint + commit
uv run ruff check telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py --output-format=concise
git add telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py
Commit с "Closes #114"

ТЕСТЫ (строго по файлам):
- tests/unit/graph/test_generate_node.py (основной)
- tests/integration/test_graph_paths.py (regression)
- НЕ запускай tests/unit/graph/ целиком

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query)
- Exa: web_search_exa(query) или get_code_context_exa(query)

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Каждый commit message через HEREDOC формат.
4. TDD: НЕТ кода без падающего теста сначала.
5. Если тест не падает в RED — пересмотри тест.

ЛОГИРОВАНИЕ в /repo/logs/worker-p0-stream.log (APPEND):
Каждое действие логируй через: echo "[TAG] $(date +%H:%M:%S) message" >> /repo/logs/worker-p0-stream.log
Теги: [START], [DONE], [ERROR], [COMPLETE]
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker P0-STREAM finished" >> /repo/logs/worker-p0-stream.log

После завершения ВСЕХ задач выполни ДВЕ bash команды:
1. TMUX="" tmux send-keys -t "claude:1" "W-P0-STREAM COMPLETE — проверь logs/worker-p0-stream.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
