W-DEPLOY: Finalize #154 review — CallbackHandler decision + deploy checklist (Issue #157)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения
2. /requesting-code-review — code review ПОСЛЕ кодовых изменений, ПЕРЕД коммитом
3. /verification-before-completion — финальная проверка

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName="langgraph", query="CallbackHandler in summarize chain") затем query-docs
- Context7: resolve-library-id(libraryName="langchain", query="CallbackHandler vs native observe tracing") затем query-docs
- Exa: web_search_exa("langgraph 2026 CallbackHandler vs langfuse observe tracing best practice")
- Exa: get_code_context_exa("langfuse observe decorator vs langchain CallbackHandler comparison 2026")

КОНТЕКСТ:
Issue #157: Follow-up от code review #154 (Conversation Memory).
Уже сделано: deps fix, lock/rebuild, try/except в summarize_wrapper.
Осталось:
1. Decide: keep/remove CallbackHandler в _create_summarize_model
2. Live test checklist (memory continuity, /clear, Redis keys)
3. Deploy to VPS checklist
4. Dead code: store_conversation_batch writes (найдено в ревью)

Dead code details (из комментария yastman):
- store_conversation() — dead code, remove
- store_conversation_batch() — called but result never read, remove call + method
- get_conversation() — never called, remove
- clear_conversation() — called in /clear, KEEP

РАБОЧАЯ ДИРЕКТОРИЯ: /home/user/projects/rag-w/deploy
ВЕТКА: chore/parallel-backlog/deploy-157 (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ФАЗА 1 — ИССЛЕДОВАНИЕ И ПЛАН:
1. Прочитай _create_summarize_model: telegram_bot/graph/nodes.py (найди функцию)
2. Прочитай CacheLayerManager: telegram_bot/integrations/cache_layer.py
3. Исследуй через MCP: CallbackHandler vs @observe() — что лучше для Langfuse tracing в 2026
4. Исследуй через MCP: LangGraph conversation memory deploy best practices
5. Напиши план в docs/plans/2026-02-12-deploy-checklist-157-plan.md

ФАЗА 2 — ВЫПОЛНЕНИЕ:
1. Реши по CallbackHandler:
   - Если @observe() покрывает все нужды — удали CallbackHandler из _create_summarize_model
   - Если есть преимущества — оставь с комментарием почему
   - Задокументируй решение в плане
2. Удали dead code из CacheLayerManager:
   - Удали метод store_conversation()
   - Удали метод store_conversation_batch() И вызов в cache_store_node
   - Удали метод get_conversation()
   - ОСТАВЬ clear_conversation()
3. Напиши deploy checklist: docs/checklists/deploy-memory-157.md
   - Pre-deploy: unit tests, lint
   - Deploy steps: docker build, push, k3s apply
   - Post-deploy: live test scenarios (memory continuity, /clear, Redis TTL)
   - Rollback plan
4. Запусти тесты для затронутых файлов

ТЕСТЫ:
- telegram_bot/integrations/cache_layer.py -> tests/unit/test_cache_layer.py
- telegram_bot/graph/nodes.py -> tests/unit/graph/test_nodes.py (только test_cache_store*)
- Запускай: uv run pytest tests/unit/test_cache_layer.py tests/unit/graph/test_nodes.py -v -k "cache"
- НЕ запускай tests/ целиком

ПРАВИЛА:
1. Работай ТОЛЬКО в /home/user/projects/rag-w/deploy
2. НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки
3. git commit — ТОЛЬКО конкретные файлы. ЗАПРЕЩЕНО git add -A
4. ПЕРЕД коммитом: git diff --cached --stat — убедись что ТОЛЬКО нужные файлы
5. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
6. НЕ деплой на VPS — только подготовь чеклист

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-deploy.log (APPEND):
Формат: echo "[START/DONE] $(date +%H:%M:%S) Task N: description" >> /home/user/projects/rag-fresh/logs/worker-deploy.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker deploy finished" >> /home/user/projects/rag-fresh/logs/worker-deploy.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-DEPLOY COMPLETE — проверь logs/worker-deploy.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
