W-T2: Fix latency_total_ms Score (wall-time instead of sum of stages)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-10-sprint1-latency-correctness.md
Работай из /repo. Ветка fix/issue120-umbrella.
Выполняй ТОЛЬКО Task 2 из плана (секция "Task 2: Fix latency_total_ms Score").

КОНТЕКСТ:
- latency_total_ms сейчас считается как sum(latency_stages.values()) — inflated 300x+ при rewrite loops
- Нужно использовать wall-time (time.perf_counter) вместо суммы
- Добавить pipeline_wall_ms в result dict в handle_query
- Исправить _write_langfuse_scores чтобы брать pipeline_wall_ms

ЗАДАЧИ (выполняй по порядку):
1. Прочитай текущие файлы: telegram_bot/bot.py, tests/unit/test_bot_handlers.py
2. Step 1: Напиши failing тесты TestWriteLangfuseScores в tests/unit/test_bot_handlers.py (как в плане)
3. Step 2: Запусти тест, убедись что FAIL
4. Step 3: Исправь _write_langfuse_scores в bot.py — используй pipeline_wall_ms
5. Step 4: Добавь pipeline_wall_ms в handle_query (time.perf_counter)
6. Step 5: Запусти тесты, убедись что PASS
7. Step 6: Lint + commit

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО: uv run pytest tests/unit/test_bot_handlers.py -v
- НЕ запускай tests/ целиком
- Маппинг: telegram_bot/bot.py -> tests/unit/test_bot_handlers.py
- Используй --lf для перезапуска упавших
- Финальная проверка: uv run ruff check telegram_bot/bot.py tests/unit/test_bot_handlers.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы: telegram_bot/bot.py tests/unit/test_bot_handlers.py
2. НЕ git add -A
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в коммите
4. Формат коммита: fix(observability): use wall-time for latency_total_ms score
5. НЕ трогай файлы которые не указаны в Task 2

ЛОГИРОВАНИЕ в /repo/logs/worker-t2-latency.log (APPEND):
Каждый шаг логируй:
echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-t2-latency.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-t2-latency.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker T2 finished" >> /repo/logs/worker-t2-latency.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-T2 COMPLETE — проверь logs/worker-t2-latency.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
