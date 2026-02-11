W-DOCKER: Phase 3 — Docker bot rebuild + health check

Работай из /home/user/projects/rag-fresh. Ветка fix/issue120-umbrella.

ЗАДАЧИ:

1. Rebuild and start bot stack:
   make docker-bot-up
   Жди пока все сервисы поднимутся.

2. Проверь health:
   docker compose -f docker-compose.dev.yml ps
   Ожидание: postgres, redis, qdrant, bge-m3, litellm, bot — все healthy/running.

3. Проверь логи бота:
   docker logs --tail 50 dev-bot
   Ожидание: "Preflight checks passed", нет ошибок.

4. Если бот НЕ стартовал — прочитай ошибку, попробуй пофиксить (перезапуск, проверка конфигурации).

5. Запости статус в #120:
   gh issue comment 120 --body "## Phase 3: Docker Validation

   ### Services Status
   (вставь вывод docker compose ps)

   ### Bot Logs (last 20 lines)
   (вставь ключевые строки)

   ### Result
   Bot healthy / Bot FAILED (опиши проблему)"

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-docker.log (APPEND):
echo "[TAG] $(date +%H:%M:%S) message" >> /home/user/projects/rag-fresh/logs/worker-docker.log
Теги: [START], [DONE], [ERROR], [COMPLETE]

После завершения выполни:
1. TMUX="" tmux send-keys -t "claude:1" "W-DOCKER COMPLETE — проверь logs/worker-docker.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
