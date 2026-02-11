W-SMOKE: Прогнать smoke-тесты LangGraph в рантайме

Работай из /repo

ЗАДАЧИ:

1. Проверить что Docker-сервисы доступны:
   docker compose ps --format json | python3 -c "import sys,json; [print(c['Name'],c['State'],c.get('Health','')) for c in json.loads(sys.stdin.read())]"

2. Запустить smoke-тесты:
   uv run pytest tests/smoke/test_langgraph_smoke.py -q --timeout=120
   Если тесты падают из-за connection errors — подождать 10 секунд и повторить.

3. Если smoke pass — запустить integration tests тоже:
   uv run pytest tests/integration/test_graph_paths.py -v --timeout=30

4. Записать результат в лог.

ЛОГИРОВАНИЕ в /repo/logs/worker-smoke.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-smoke.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-smoke.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-smoke.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:node" "W-SMOKE COMPLETE — проверь logs/worker-smoke.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:node" Enter
