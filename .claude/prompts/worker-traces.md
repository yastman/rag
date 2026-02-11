W-TRACES: Прогнать trace-валидацию для проверки #101/#123/#124

Работай из /repo

ЗАДАЧИ:

1. Проверить что Docker-сервисы и Langfuse доступны:
   curl -sf http://localhost:3001/api/public/health | head -1

2. Запустить trace validation:
   uv run python -m scripts.validate_traces --collection gdrive_bge --report 2>&1 | tee /repo/logs/trace-validation-report.log
   Если скрипт падает с ошибкой — проверь трейсбек, попробуй с --help чтобы увидеть доступные опции.
   Если нет флага --collection, попробуй без него:
   uv run python -m scripts.validate_traces --report

3. Если validate_traces содержит Go/No-Go секцию — записать результат (pass/fail по каждому критерию).

4. Записать результат в лог.

ЛОГИРОВАНИЕ в /repo/logs/worker-traces.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-traces.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-traces.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-traces.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:node" "W-TRACES COMPLETE — проверь logs/worker-traces.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:node" Enter
