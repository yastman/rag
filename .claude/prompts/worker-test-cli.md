Напиши unit тесты для src/ingestion/unified/cli.py

GitHub Issue: #51 — test: cover critical unified ingestion modules
Работай из /home/user/projects/rag-fresh

SKILLS (обязательно вызови):
1. /test-driven-development — RED → GREEN → REFACTOR
2. /verification-before-completion — проверка после написания

## Шаги

1. Прочитай src/ingestion/unified/cli.py — пойми что делает (preflight, bootstrap, run, status, reprocess)
2. Прочитай существующие тесты в tests/unit/ingestion/ — пойми паттерны
3. Создай tests/unit/ingestion/test_unified_cli.py
4. Покрой:
   - Arg parsing для каждой команды
   - preflight checks (mock external deps)
   - status command output
   - Error paths (missing config, connection failures)
5. Запусти: uv run pytest tests/unit/ingestion/test_unified_cli.py -v
6. Убедись все зелёные

## Правила
- git add tests/unit/ingestion/test_unified_cli.py
- git commit -m "test(ingestion): add unit tests for unified CLI module

Closes #51 (partial)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
- Тесты ТОЛЬКО свои: tests/unit/ingestion/test_unified_cli.py

## Логирование
/home/user/projects/rag-fresh/logs/worker-test-cli.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

## Webhook
После завершения:
TMUX="" tmux send-keys -t "claude:1" "W-CLI COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
