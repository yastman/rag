W-STATE: Unit тесты для state_manager async методов

GitHub Issue: #52 — P1: ingestion state_manager async methods
Работай из /home/user/projects/rag-fresh

Шаги:

1. Прочитай src/ingestion/unified/state_manager.py — найди async методы:
   get_stats, get_dlq_count, mark_indexed, mark_error, upsert_state и другие
2. Прочитай tests/unit/ingestion/test_state_manager_sync.py — паттерн
3. Создай tests/unit/ingestion/test_state_manager_async.py:

   Мокай asyncpg pool через AsyncMock.
   Покрой:
   a) get_stats — возвращает dict с counts
   b) get_dlq_count — возвращает int
   c) mark_indexed — вызывает UPDATE с правильными параметрами
   d) mark_error — вызывает UPDATE, устанавливает failed status
   e) upsert_state — INSERT ON CONFLICT
   f) Edge cases: pool not initialized, connection error

4. Запусти: uv run pytest tests/unit/ingestion/test_state_manager_async.py -v
5. Фикси пока все не зелёные

После успеха:
- git add tests/unit/ingestion/test_state_manager_async.py
- git commit -m "test(ingestion): add unit tests for state_manager async methods

Covers get_stats, get_dlq_count, mark_indexed, mark_error, upsert_state.
Closes #52 (partial)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /home/user/projects/rag-fresh/logs/worker-state-manager.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook — после завершения:
TMUX="" tmux send-keys -t "claude:1" "W-STATE COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
