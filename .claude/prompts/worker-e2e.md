W-E2E: E2E тест бота (Task 9)

Работай из /home/user/projects/rag-fresh
GitHub Issue: #44 — Task 9: E2E bot test

Docker сервисы уже UP (8 healthy). Telegram env скопирован с VPS.

Шаги:

1. Проверь что .env содержит TELEGRAM_BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH
2. Проверь что E2E setup готов: ls scripts/e2e/
3. Если нужен setup: make e2e-setup
4. Запусти E2E тесты:
   uv run python scripts/e2e/runner.py --skip-judge 2>&1 | tee /home/user/projects/rag-fresh/logs/e2e-tests.txt
5. Если runner.py не работает — попробуй:
   uv run pytest tests/e2e/ -v --tb=short 2>&1 | tee /home/user/projects/rag-fresh/logs/e2e-tests.txt
6. Запиши результат

Если E2E требует ANTHROPIC_API_KEY для Judge и его нет — запусти с --skip-judge.
Если E2E вообще не может запуститься (нет Telegram session) — запиши причину в лог и выполни хотя бы smoke тесты повторно с живыми Docker:
   uv run pytest tests/smoke/ -v --tb=short 2>&1 | tee /home/user/projects/rag-fresh/logs/e2e-smoke-fallback.txt
   uv run pytest tests/integration/ -v --tb=short 2>&1 | tee -a /home/user/projects/rag-fresh/logs/e2e-smoke-fallback.txt

НЕ делай git commit.

Логирование в /home/user/projects/rag-fresh/logs/worker-e2e.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-E2E COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
