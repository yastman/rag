W-BUILD: Rebuild bot + dependencies with --no-cache

Работай из /home/user/projects/rag-fresh.

ЗАДАЧИ (без остановок):

ЗАДАЧА 1: Пересобрать bot контейнер (полный rebuild)
docker compose --compatibility -f docker-compose.dev.yml build --no-cache telegram-bot
Это займёт несколько минут. Жди завершения.

ЗАДАЧА 2: Пересобрать litellm и bge-m3 (если нужны свежие)
docker compose --compatibility -f docker-compose.dev.yml build --no-cache litellm bge-m3

ЗАДАЧА 3: Перезапустить стек с новыми образами
docker compose --compatibility -f docker-compose.dev.yml --profile core --profile bot --profile ml up -d --force-recreate --wait
Дождись пока все сервисы healthy.

ЗАДАЧА 4: Проверить что бот запустился
docker compose --compatibility -f docker-compose.dev.yml logs telegram-bot --tail 20
Убедись что нет ошибок импорта или crash loop.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-docker-rebuild.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /home/user/projects/rag-fresh/logs/worker-docker-rebuild.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /home/user/projects/rag-fresh/logs/worker-docker-rebuild.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-docker-rebuild.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-BUILD COMPLETE — проверь logs/worker-docker-rebuild.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
