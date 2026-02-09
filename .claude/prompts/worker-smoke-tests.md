W-SMOKE: Запусти Docker сервисы и smoke тесты

GitHub Issue: #44 — Task 8: Smoke tests
Работай из /repo

Шаги:

1. Подними core Docker сервисы: docker compose -f docker-compose.dev.yml up -d
2. Подожди 30 секунд пока сервисы стартуют
3. Проверь что сервисы живы: docker compose -f docker-compose.dev.yml ps
4. Запусти smoke тесты: uv run pytest tests/smoke/ -v --tb=short 2>&1 | tee /repo/logs/smoke-tests.txt
5. Если есть фейлы — проанализируй причины, запиши в лог
6. Если bge-m3 контейнер доступен — запусти так же: uv run pytest tests/integration/test_docker_services.py -v --tb=short 2>&1 | tee -a /repo/logs/smoke-tests.txt

НЕ фикси тесты, только запусти и сохрани результат.
НЕ делай git commit.

Логирование в /repo/logs/worker-smoke-tests.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook — после завершения:
TMUX="" tmux send-keys -t "claude:1" "W-SMOKE COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
