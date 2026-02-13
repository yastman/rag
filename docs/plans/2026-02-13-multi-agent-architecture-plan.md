# Multi-Agent Supervisor + Unified LangGraph/Langfuse Plan (#240)

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Уйти от монолитного `classify_node` к supervisor-tools архитектуре и одновременно сделать единый observability-контур `LangGraph + Langfuse` (один trace tree на пользовательский запрос).

**Architecture:** Supervisor в `LangGraph` выбирает один из tools (`rag_search`, `history_search`, `direct_response`). `rag_search` оборачивает текущий RAG subgraph без переписывания 10 нод. `history_search` использует текущий `HistoryService` (Qdrant + BGE-M3), а не `PostgresStore`. Все ветки пишут в один trace через `@observe + propagate_attributes + score_current_trace`.

**Tech Stack:** LangGraph StateGraph + ToolNode, Langfuse SDK v3 (`observe`, `propagate_attributes`, `score_current_trace`), aiogram, текущие `QdrantService`/`HistoryService`, BGE-M3 embeddings.

---

## Актуализация от 2026-02-13 (точечная)

- Убрана жёсткая привязка `#240 -> PostgresStore`.
- Dependency теперь: `#239` должен дать стабильный `HistoryService` API (`save_turn`, `search_user_history`) и рабочую `/history`.
- По эмбеддингам для истории: используем уже существующий BGE-M3 контур и Qdrant коллекцию `conversation_history`, без нового embedding-engine.
- По observability: для `#240` фиксируем единый путь `LangGraph orchestration -> Langfuse trace/scores`; не заводим второй параллельный контур в bot-path.

## Task 1: Stabilize Supervisor State Contract

**Files:**
- Create: `telegram_bot/graph/supervisor_state.py`
- Test: `tests/unit/graph/test_supervisor_state.py`

**Step 1: Write failing test**
- Проверить, что `SupervisorState` содержит только минимальные поля: `messages`, `user_id`, `session_id`, `agent_used`, `latency_stages`.

**Step 2: Run test to verify fail**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/graph/test_supervisor_state.py -v`

**Step 3: Implement state schema**
- Добавить `TypedDict` + `add_messages` reducer.

**Step 4: Run test to verify pass**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/graph/test_supervisor_state.py -v`

## Task 2: Implement Tools With Runtime User Context

**Files:**
- Create: `telegram_bot/agents/tools.py`
- Test: `tests/unit/agents/test_tools_runtime_context.py`

**Step 1: Write failing tests**
- `rag_search` и `history_search` читают `user_id/session_id` из `config["configurable"]`.
- Без `user_id` tool возвращает controlled error message (не traceback).

**Step 2: Run tests to verify fail**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_tools_runtime_context.py -v`

**Step 3: Implement tools**
- Добавить `rag_search(query: str, config: RunnableConfig)`.
- Добавить `history_search(query: str, config: RunnableConfig)`.
- Добавить `direct_response(message: str)`.

**Step 4: Run tests to verify pass**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_tools_runtime_context.py -v`

## Task 3: Wrap Existing RAG Graph As Tool (No Pipeline Rewrite)

**Files:**
- Create: `telegram_bot/agents/rag_agent.py`
- Modify: `telegram_bot/graph/graph.py` (only if adapter needed)
- Test: `tests/unit/agents/test_rag_agent_tool.py`

**Step 1: Write failing test**
- Tool wrapper вызывает текущий `build_graph().ainvoke()` и возвращает `response`.

**Step 2: Run test to verify fail**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_rag_agent_tool.py -v`

**Step 3: Implement minimal wrapper**
- Инжект текущие сервисы через closure.
- Для streaming оставить текущее поведение через `message` injection.

**Step 4: Run test to verify pass**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_rag_agent_tool.py -v`

## Task 4: History Tool On Top Of Qdrant HistoryService

**Files:**
- Create: `telegram_bot/agents/history_agent.py`
- Modify: `telegram_bot/services/history_service.py` (только если не хватает API)
- Test: `tests/unit/agents/test_history_agent_tool.py`

**Step 1: Write failing tests**
- `history_search` вызывает `search_user_history(user_id, query, limit=5)`.
- Пустой результат -> безопасный fallback.
- Ответ форматируется кратко, без нового LLM вызова (MVP).

**Step 2: Run tests to verify fail**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_history_agent_tool.py -v`

**Step 3: Implement history tool**
- Использовать существующий history backend (Qdrant/BGE-M3).
- Не добавлять Postgres dependency.

**Step 4: Run tests to verify pass**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_history_agent_tool.py -v`

## Task 5: Build Supervisor Graph

**Files:**
- Create: `telegram_bot/agents/supervisor.py`
- Test: `tests/unit/agents/test_supervisor_routing.py`

**Step 1: Write failing routing tests**
- Недвижимость -> `rag_search`
- История диалога -> `history_search`
- Chitchat/off-topic -> `direct_response`

**Step 2: Run tests to verify fail**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_supervisor_routing.py -v`

**Step 3: Implement supervisor**
- `bind_tools([rag_search, history_search, direct_response])`
- Loop: `supervisor -> tools -> supervisor` до финального сообщения.

**Step 4: Run tests to verify pass**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_supervisor_routing.py -v`

## Task 6: Integrate Supervisor Into Telegram Bot With /history Bypass

**Files:**
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/test_bot_handlers.py`

**Step 1: Write failing integration tests**
- `handle_query()` использует `supervisor.ainvoke()` под feature flag.
- `/history` идёт напрямую в `history_search` (bypass supervisor).

**Step 2: Run tests to verify fail**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/test_bot_handlers.py -k "supervisor or history" -v`

**Step 3: Implement bot wiring**
- Добавить `USE_SUPERVISOR` feature flag.
- Сохранить rollback path на текущий монолитный graph.

**Step 4: Run tests to verify pass**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/test_bot_handlers.py -k "supervisor or history" -v`

## Task 7: Unify Langfuse + LangGraph As One Observability System

**Files:**
- Modify: `telegram_bot/agents/supervisor.py`
- Modify: `telegram_bot/bot.py`
- Modify: `telegram_bot/observability.py` (минимально)
- Test: `tests/unit/agents/test_supervisor_observability.py`

**Step 1: Write failing observability tests**
- Один trace на запрос содержит supervisor + выбранный tool.
- Пишутся scores: `agent_used`, `supervisor_latency_ms`, `supervisor_model`.

**Step 2: Run tests to verify fail**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_supervisor_observability.py -v`

**Step 3: Implement unified tracing**
- На входе: `propagate_attributes(session_id, user_id, tags=["telegram","rag","supervisor"])`.
- На supervisor/tool nodes: `@observe(...)`.
- В конце запроса: `update_current_trace(...) + score_current_trace(...)`.

**Step 4: Run tests to verify pass**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/unit/agents/test_supervisor_observability.py -v`

## Task 8: Documentation + Final Validation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.claude/rules/features/telegram-bot.md`
- Modify: `docs/PIPELINE_OVERVIEW.md`

**Step 1: Update docs**
- Новый routing path (supervisor/tools).
- Явно зафиксировать: history backend = Qdrant, embeddings = BGE-M3 reuse.
- Явно зафиксировать единый LangGraph/Langfuse trace model.

**Step 2: Run required validation**
Run: `make check`
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

**Step 3: Run focused integration check**
Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' uv run pytest tests/integration/test_graph_paths.py -v`

---

## Acceptance Criteria

- `#240` больше не зависит от PostgresStore как технологического выбора.
- Supervisor роутит минимум в 3 домена (`rag`, `history`, `direct`) без регресса старого graph path.
- `/history` остаётся явной командой и работает напрямую через history tool.
- В Langfuse виден единый trace tree: `telegram-rag-query -> supervisor -> selected_tool -> existing nodes`.
- Все новые тесты проходят в параллельном режиме.

## Risks / Mitigations

1. **Streaming regressions через tool-wrapper**
Mitigation: оставить существующий `message` injection path, покрыть отдельным unit test.

2. **Неверная передача user context в tools**
Mitigation: строго использовать `RunnableConfig.configurable` и тестировать отсутствие `user_id`.

3. **+1 LLM роутинг-вызов**
Mitigation: использовать cheap/fast model для supervisor и ограничить промпт до routing-only.

## SDK References (Context7 + Official Docs)

- LangGraph Graph API: tools могут читать runtime context через `RunnableConfig` (`configurable.user_id/session_id`).
- Langfuse Python SDK: `@observe`, `propagate_attributes`, `score_current_trace` для сквозной трассировки.
- LangChain multi-agent docs (Jan 2026): для новых приложений рекомендован supervisor через tools; `langgraph-supervisor` оставлен для back-compat.
