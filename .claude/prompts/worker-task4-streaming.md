W-STREAM: Streaming в Telegram Graph Path (Task 4)

ПЛАН: /repo/docs/plans/2026-02-10-latency-phase2-impl.md (Task 4)
Работай из /repo
Ветка: fix/issue-91-ci-smoke-remediation (уже checkout)

ЗАДАЧА: Интегрировать streaming delivery LLM ответов в Telegram бот через LangGraph pipeline.

ОБЯЗАТЕЛЬНО ПЕРЕД КОДОМ:
1. Через MCP Context7 (resolve-library-id + query-docs) найди ОФИЦИАЛЬНУЮ документацию:
   - LangGraph streaming: resolve "langgraph" -> query "streaming astream stream_mode messages events"
   - aiogram streaming/edit message: resolve "aiogram" -> query "edit_text message streaming partial update"
   - OpenAI SDK streaming: resolve "openai python" -> query "chat completions stream async streaming"
   - Langfuse + streaming: resolve "langfuse" -> query "observe streaming openai async tracing"
2. Используй ТОЛЬКО паттерны из оф документации. Никаких хаков.

ТЕКУЩАЯ АРХИТЕКТУРА (прочитай эти файлы):
- telegram_bot/bot.py — PropertyBot.handle_query(), graph.ainvoke(state)
- telegram_bot/graph/nodes/generate.py — generate_node, config.create_llm(), llm.chat.completions.create()
- telegram_bot/graph/graph.py — build_graph(), 9-node StateGraph
- telegram_bot/graph/nodes/respond.py — respond_node, message.answer()

ДИЗАЙН (из плана v2):
- Streaming ТОЛЬКО на этапе генерации (generate -> respond).
- Retrieval/grading/routing НЕ трогать.
- Паттерн доставки в Telegram:
  a. Отправить placeholder сообщение
  b. Редактировать его по мере получения чанков (throttle 200-300ms)
  c. Финализировать когда LLM закончит
- Если streaming fails — fallback на текущий non-streaming send.
- Langfuse метрики и latency_stages должны сохраниться.

ВАРИАНТЫ РЕАЛИЗАЦИИ (выбери по оф документации):
A. graph.astream(state, stream_mode="messages") — LangGraph нативный streaming
B. OpenAI stream=True внутри generate_node + передача chunks через state/callback
C. Отдельный streaming respond node после generate

ФАЙЛЫ которые ты можешь редактировать:
- telegram_bot/bot.py (handle_query — переключить на streaming)
- telegram_bot/graph/nodes/generate.py (stream=True если нужно)
- telegram_bot/graph/nodes/respond.py (streaming edit если нужно)
- telegram_bot/graph/graph.py (если нужна новая нода)
- telegram_bot/graph/state.py (если нужны новые поля)
- tests/unit/graph/test_generate_node.py
- tests/unit/test_bot.py

НЕ ТРОГАЙ: retrieve, grade, rerank, rewrite, cache, classify, edges, config (кроме добавления streaming полей если нужно)

ПРАВИЛА:
1. СНАЧАЛА Context7 для каждого SDK. Без документации НЕ пиши код.
2. TDD: сначала тест, потом код.
3. ТЕСТЫ — только свои модули. НЕ запускай весь tests/unit/
4. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
5. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
6. Используй uv run pytest (не просто pytest).
7. Fallback на non-streaming если streaming fails.

MCP TOOLS (ОБЯЗАТЕЛЬНО):
- Context7: resolve-library-id -> query-docs ДЛЯ КАЖДОГО SDK перед реализацией:
  - langgraph (streaming API)
  - aiogram (message editing)
  - openai (streaming completions)
  - langfuse (tracing streaming)
- Exa: get_code_context_exa для "LangGraph streaming Telegram bot 2025 2026" если Context7 не даёт достаточно

ВЕРИФИКАЦИЯ перед коммитом:
- uv run pytest tests/unit/graph/test_generate_node.py -v
- uv run pytest tests/unit/test_bot.py -v || true
- uv run ruff check telegram_bot/bot.py telegram_bot/graph/nodes/generate.py telegram_bot/graph/nodes/respond.py --fix
- uv run ruff format telegram_bot/bot.py telegram_bot/graph/nodes/generate.py telegram_bot/graph/nodes/respond.py

ЛОГИРОВАНИЕ в /repo/logs/worker-streaming.log (APPEND):
[START] timestamp Task 4: Streaming Telegram
[SDK] timestamp Context7 langgraph streaming: краткий итог что нашёл
[SDK] timestamp Context7 aiogram edit_text: краткий итог
[SDK] timestamp Context7 openai streaming: краткий итог
[SDK] timestamp Context7 langfuse streaming: краткий итог
[DONE] timestamp Task 4: result summary
[COMPLETE] timestamp Worker finished

После завершения ВСЕХ задач выполни ДВЕ bash команды:
1. TMUX="" tmux send-keys -t "claude:3" "W-STREAM COMPLETE — проверь logs/worker-streaming.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:3" Enter
