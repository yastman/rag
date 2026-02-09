W-FIX-A: Починить 17 тестов в test_unified_cli.py + test_unified_flow.py

Работай из /home/user/projects/rag-fresh

Проблемы:
- MagicMock используется вместо AsyncMock для async методов (manager.get_stats, manager.close, manager._get_pool)
- cmd_run/cmd_watch mock config не совпадает (Expected/Actual differ)
- main() возвращает mock вместо int

Шаги:

1. Прочитай tests/unit/ingestion/test_unified_cli.py — найди все MagicMock которые должны быть AsyncMock
2. Прочитай src/ingestion/unified/cli.py — пойми какие функции async
3. Замени MagicMock на AsyncMock для всех async методов
4. Для cmd_run/cmd_watch — убедись что mock config использует тот же instance
5. Для main dispatch тестов — убедись что cmd функции возвращают int (return_value=0)
6. Прочитай tests/unit/ingestion/test_unified_flow.py — починь test_starts_live_updater (mock_updater.wait)
7. Запусти: uv run pytest tests/unit/ingestion/test_unified_cli.py tests/unit/ingestion/test_unified_flow.py -v --tb=short
8. Фикси пока все зелёные

После успеха:
- git add tests/unit/ingestion/test_unified_cli.py tests/unit/ingestion/test_unified_flow.py
- git commit -m "fix(tests): repair unified CLI and flow tests — AsyncMock + config alignment

17 tests fixed: replace MagicMock with AsyncMock for async methods,
align config mock instances, fix main() return values.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /home/user/projects/rag-fresh/logs/worker-fix-a.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-FIX-A COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
