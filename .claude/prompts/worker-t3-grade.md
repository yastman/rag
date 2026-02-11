W-T3: Recalibrate Grade Threshold for RRF Score Scale

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-10-sprint1-latency-correctness.md
Работай из /repo. Ветка fix/issue120-umbrella.
Выполняй ТОЛЬКО Task 3 из плана (секция "Task 3: Recalibrate Grade Threshold for RRF Scores").

КОНТЕКСТ:
- RRF scores = 1/(k+rank), k=60: rank 1 = 0.016, rank 100 = 0.00625
- Текущий RELEVANCE_THRESHOLD = 0.3 — абсолютно недостижим для RRF scores
- Это вызывает: все документы помечаются irrelevant -> бесконечные rewrite loops
- Нужно: снизить threshold до 0.005, сделать configurable через env var

ЗАДАЧИ (выполняй по порядку):
1. Прочитай текущие файлы: telegram_bot/graph/nodes/grade.py, telegram_bot/graph/config.py, tests/unit/graph/test_agentic_nodes.py, tests/unit/graph/test_edges.py
2. Step 1: Напиши failing тесты TestGradeNodeRRFScores в tests/unit/graph/test_agentic_nodes.py (как в плане)
3. Step 2: Запусти тест, убедись что FAIL
4. Step 3: Добавь relevance_threshold_rrf в GraphConfig (config.py) + from_env()
5. Step 4: Исправь grade.py — используй config.relevance_threshold_rrf вместо hardcoded 0.3
6. Step 5: Запусти тесты grade + edges, убедись что PASS
7. Step 6: Lint + commit

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО: uv run pytest tests/unit/graph/test_agentic_nodes.py tests/unit/graph/test_edges.py -v
- НЕ запускай tests/ целиком и НЕ tests/unit/graph/ целиком
- Маппинг:
  telegram_bot/graph/nodes/grade.py -> tests/unit/graph/test_agentic_nodes.py
  telegram_bot/graph/config.py -> tests/unit/graph/test_edges.py (regression)
- Используй --lf для перезапуска упавших
- Финальная проверка: uv run ruff check telegram_bot/graph/nodes/grade.py telegram_bot/graph/config.py tests/unit/graph/test_agentic_nodes.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы: telegram_bot/graph/nodes/grade.py telegram_bot/graph/config.py tests/unit/graph/test_agentic_nodes.py
2. НЕ git add -A
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в коммите
4. Формат коммита: fix(grade): recalibrate RELEVANCE_THRESHOLD for RRF score scale
5. НЕ трогай файлы которые не указаны в Task 3

ЛОГИРОВАНИЕ в /repo/logs/worker-t3-grade.log (APPEND):
Каждый шаг логируй:
echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-t3-grade.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-t3-grade.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker T3 finished" >> /repo/logs/worker-t3-grade.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-T3 COMPLETE — проверь logs/worker-t3-grade.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
