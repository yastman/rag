W-T4: Implement Real Langfuse Scores (5 hardcoded -> real values)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-10-sprint1-latency-correctness.md
Работай из /repo. Ветка fix/issue120-umbrella.
Выполняй ТОЛЬКО Task 4 из плана (секция "Task 4: Implement Real Langfuse Scores").

КОНТЕКСТ:
- Tasks 1, 2, 3 УЖЕ выполнены и закоммичены. Файлы обновлены.
- bot.py уже имеет pipeline_wall_ms (Task 2) и hybrid embeddings init (Task 1)
- cache.py уже имеет hybrid embedding logic (Task 1)
- retrieve.py уже имеет hybrid re-embedding logic (Task 1)
- state.py, bot.py, cache.py, retrieve.py — ПРОЧИТАЙ текущее состояние ПЕРЕД редактированием
- Нужно: заменить 3 hardcoded 0.0 scores реальными значениями из state

ЗАДАЧИ (выполняй по порядку):
1. Прочитай ВСЕ файлы: telegram_bot/bot.py, telegram_bot/graph/state.py, telegram_bot/graph/nodes/cache.py, telegram_bot/graph/nodes/retrieve.py, tests/unit/test_bot_handlers.py, tests/unit/graph/test_cache_nodes.py
2. Step 1: Напиши failing тест test_real_scores_from_state в tests/unit/test_bot_handlers.py::TestWriteLangfuseScores
3. Step 2: Запусти тест, убедись FAIL
4. Step 3: Добавь поля embeddings_cache_hit, search_cache_hit в RAGState (state.py) и make_initial_state
5. Step 4: Установи embeddings_cache_hit в cache_check_node (cache.py)
6. Step 5: Установи search_cache_hit в retrieve_node (retrieve.py)
7. Step 6: Обнови _write_langfuse_scores в bot.py — замени hardcoded scores реальными
8. Step 7: Запусти все тесты затронутых модулей
9. Step 8: Lint + commit

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО:
  uv run pytest tests/unit/test_bot_handlers.py tests/unit/graph/test_cache_nodes.py tests/unit/graph/test_retrieve_node.py tests/unit/graph/test_state.py -v
- НЕ запускай tests/ целиком
- Маппинг source -> test:
  telegram_bot/bot.py -> tests/unit/test_bot_handlers.py
  telegram_bot/graph/state.py -> tests/unit/graph/test_state.py
  telegram_bot/graph/nodes/cache.py -> tests/unit/graph/test_cache_nodes.py
  telegram_bot/graph/nodes/retrieve.py -> tests/unit/graph/test_retrieve_node.py
- Используй --lf для перезапуска упавших

ПРАВИЛА:
1. git commit — ТОЛЬКО: telegram_bot/bot.py telegram_bot/graph/state.py telegram_bot/graph/nodes/cache.py telegram_bot/graph/nodes/retrieve.py tests/unit/test_bot_handlers.py
2. НЕ git add -A
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
4. Формат: feat(observability): implement real Langfuse scores for cache hits and confidence
5. ПРОЧИТАЙ текущее состояние файлов — Tasks 1-3 уже изменили bot.py, cache.py, retrieve.py

ЛОГИРОВАНИЕ в /repo/logs/worker-t4-scores.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-t4-scores.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-t4-scores.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker T4 finished" >> /repo/logs/worker-t4-scores.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-T4 COMPLETE — проверь logs/worker-t4-scores.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
