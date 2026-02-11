W-REBUILD: Пересобрать и запустить контейнеры bot + bge-m3

Работай из /home/user/projects/rag-fresh

ЗАДАЧИ:

1. Пересобрать bot и bge-m3 (без кеша):
   docker compose build --no-cache bot bge-m3 2>&1 | tee logs/rebuild.log

2. Поднять стек:
   docker compose --profile core --profile bot --profile ml up -d --force-recreate 2>&1 | tee -a logs/rebuild.log

3. Дождаться health checks (до 120s для bge-m3):
   docker compose --profile core --profile bot --profile ml ps
   Проверить что все сервисы healthy/running.

4. Проверить что bot стартовал:
   docker compose logs bot --tail 20

5. Проверить что bge-m3 warmed up (новый lifespan):
   docker compose logs bge-m3 --tail 30
   Должно быть: "Warmup complete in X.XXs" и warmed_up: true в /health

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-rebuild.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /home/user/projects/rag-fresh/logs/worker-rebuild.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /home/user/projects/rag-fresh/logs/worker-rebuild.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-rebuild.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:node" "W-REBUILD COMPLETE — проверь logs/worker-rebuild.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:node" Enter
