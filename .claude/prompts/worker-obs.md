W-OBS: Orphan traces cleanup + propagate_attributes (#123)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-11-orphan-traces-plan.md
Работай из /home/user/projects/rag-fresh

ЗАДАЧИ (выполняй по плану):

Step 1: Add @observe to store_conversation_batch в telegram_bot/integrations/cache.py:390
- Добавить @observe(name="cache-conversation-batch-store") декоратор
- import observe уже есть в файле

Step 2: Add traced_pipeline helper в telegram_bot/observability.py (после строки 137)
- Написать тест test_traced_pipeline_is_context_manager
- Реализовать функцию traced_pipeline(session_id, user_id, tags)
- Это обёртка над propagate_attributes

Step 3: Wrap smoke test в tests/smoke/test_langgraph_smoke.py:126
- Добавить import traced_pipeline
- Обернуть graph.ainvoke в with traced_pipeline(session_id="smoke-test", user_id="smoke")

Step 4: Wrap 6 integration tests в tests/integration/test_graph_paths.py
- Строки 177, 228, 273, 350, 399, 449 — обернуть каждый graph.ainvoke
- session_id: test-chitchat, test-cache-hit, test-happy-path, test-rewrite-loop, test-rewrite-exhausted, test-rewrite-ineffective

Step 5: Update observability docs в .claude/rules/observability.md

ТЕСТЫ (строго по файлам):
  uv run pytest tests/unit/integrations/test_cache_layers.py -v -x
  uv run pytest tests/smoke/test_langgraph_smoke.py -v
  uv run pytest tests/integration/test_graph_paths.py -v
- Маппинг:
  telegram_bot/integrations/cache.py -> tests/unit/integrations/test_cache_layers.py
  telegram_bot/observability.py -> tests/unit/test_observability.py (новый)
  tests/smoke/test_langgraph_smoke.py -> сам файл
  tests/integration/test_graph_paths.py -> сам файл
- ВАЖНО: test_graph_paths.py также меняется в #108 (новый тест). Твоя область — обёртка СУЩЕСТВУЮЩИХ тестов в traced_pipeline. НЕ добавляй новые тесты для rewrite guard.

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Коммит: fix(observability): add traced_pipeline + wrap entry points (#123)
4. ВАЖНО: cache.py также меняется в #121 (строка 132). Твоя область — строка 390 (store_conversation_batch). НЕ трогай initialize().

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-obs.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /home/user/projects/rag-fresh/logs/worker-obs.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /home/user/projects/rag-fresh/logs/worker-obs.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-obs.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:2" "W-OBS COMPLETE — проверь logs/worker-obs.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:2" Enter
