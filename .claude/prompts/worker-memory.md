W-MEMORY: Conversation Memory v4 SDK enhancements (TTL, adelete_thread, checkpoint_ns)

CONTEXT:
Branch: 154-featmemory-short-term-conversation-memory-redis-checkpointer-+-langmem-sdk (already exists)
Working dir: /repo
Plan: /repo/docs/plans/2026-02-11-conversation-memory-plan.md (v4, Tasks 0-4)
Design: /repo/docs/plans/2026-02-11-conversation-memory-design.md (v3)
Issue: #154

PREREQUISITE: Read the plan file FIRST. Pay special attention to "Audit Notes" section.
v3 tasks (1-7) are ALREADY IMPLEMENTED. This session adds v4 enhancements only.

GOAL: Add three SDK-native enhancements to existing conversation memory:
1. TTL idle expiry via AsyncRedisSaver ttl= dict (7 days, refresh on read)
2. /clear via checkpointer.adelete_thread(thread_id) — SDK-native, replaces manual cache clear
3. Checkpoint namespace separation: "tg:text:v1" for text, "tg:voice:v1" for voice

AUDIT NOTES (critical — read before coding):
- AsyncRedisSaver takes TTL via ttl={"default_ttl": minutes_int, "refresh_on_read": bool} — NOT as separate constructor arg
- Test for /clear is in tests/unit/test_bot_handlers.py, NOT in a separate file
- adelete_thread(thread_id) deletes the entire thread (all namespaces) — no per-ns clear needed
- Namespace values must be versioned: "tg:text:v1" and "tg:voice:v1"

SKILLS (invoke these):
1. /executing-plans — follow plan task-by-task
2. /verification-before-completion — before final report

TASKS (execute in order from plan):

Task 0: SDK pre-flight verification
  Run Python snippet from plan to check AsyncRedisSaver signatures.
  If signatures differ from expected — STOP, log the actual signatures, adapt plan.

Task 1: Add TTL config to AsyncRedisSaver
  Modify: telegram_bot/integrations/memory.py (update create_redis_checkpointer)
  Modify: telegram_bot/bot.py (pass ttl_minutes to factory in start())
  Test: tests/unit/integrations/test_memory.py (add TestCheckpointerTTL class)
  TDD: test -> fail -> implement -> pass -> commit

Task 2: SDK-native /clear via adelete_thread
  Modify: telegram_bot/bot.py (cmd_clear method)
  Test: tests/unit/test_bot_handlers.py (add test IN EXISTING FILE, near existing cmd_clear tests)
  TDD: test -> fail -> implement -> pass -> commit

Task 3: Checkpoint namespace by channel
  Modify: telegram_bot/bot.py (handle_query + handle_voice invoke_config)
  Test: tests/unit/test_bot_handlers.py (add namespace tests)
  Constants: _CHECKPOINT_NS_TEXT = "tg:text:v1", _CHECKPOINT_NS_VOICE = "tg:voice:v1"
  TDD: test -> fail -> implement -> pass -> commit

Task 4: Lint + verify
  ruff check + ruff format on all changed files
  Run affected tests + integration regression

MCP TOOLS (use BEFORE implementing):
- Context7: resolve-library-id(libraryName="langgraph-checkpoint-redis", query="AsyncRedisSaver TTL config adelete_thread") then query-docs for current API
- Context7: resolve-library-id(libraryName="langgraph", query="checkpoint_ns configurable namespace") then query-docs
- Exa: get_code_context_exa(query="langgraph AsyncRedisSaver TTL ttl config 2026") for fresh examples

TESTS (strict file scope):
- Run ONLY tests for files you changed:
  uv run pytest tests/unit/integrations/test_memory.py tests/unit/test_bot_handlers.py -v
- DO NOT run tests/ or tests/unit/ broadly
- Source -> test mapping:
  telegram_bot/integrations/memory.py -> tests/unit/integrations/test_memory.py
  telegram_bot/bot.py -> tests/unit/test_bot_handlers.py
- Regression (after all tasks): uv run pytest tests/integration/test_graph_paths.py -v
- Use --lf to rerun only failed tests

RULES:
1. git commit — ONLY specific files. NEVER git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> in every commit.
3. BEFORE implementing — Context7 to verify SDK API signatures.
4. Conventional commits: feat(memory): description #154
5. If SDK API differs from plan — adapt code to real API, do NOT break tests.
6. Read each file BEFORE modifying — understand existing patterns.

LOGGING to /repo/logs/worker-memory.log (APPEND):
[START] timestamp Task N: description
[DONE] timestamp Task N: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:W-REVIEW" "W-MEMORY COMPLETE — проверь logs/worker-memory.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:W-REVIEW" Enter
ВАЖНО: Используй ИМЯ окна W-REVIEW, НЕ индекс. Индекс сдвигается при kill-window.
