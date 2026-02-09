W-DOCKER-UP: Подними Docker сервисы для E2E тестирования

Работай из /repo

Шаги:

1. Проверь текущий статус: docker compose -f docker-compose.dev.yml ps
2. Подними core + bot: docker compose -f docker-compose.dev.yml --profile core --profile bot up -d
3. Подожди 30 секунд
4. Проверь что все сервисы healthy: docker compose -f docker-compose.dev.yml ps
5. Проверь health endpoints:
   - curl -s http://localhost:6333/healthz (Qdrant)
   - curl -s http://localhost:6379 (Redis — через redis-cli ping)
   - curl -s http://localhost:8000/health (BGE-M3)
6. Запиши статус всех сервисов в лог

Логирование в /repo/logs/worker-docker-up.log (APPEND):
[START] timestamp
[DONE] timestamp — X services running
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-DOCKER-UP COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
