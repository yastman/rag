W-RUN: Execute make validate-traces-fast

Работай из /home/user/projects/rag-fresh.

ЗАДАЧИ (выполняй по порядку, БЕЗ ОСТАНОВОК):

ЗАДАЧА 1: Проверить Docker stack
Запусти: docker compose --compatibility -f docker-compose.dev.yml --profile core --profile bot --profile ml ps --format json 2>&1
Если сервисы НЕ запущены — запусти:
docker compose --compatibility -f docker-compose.dev.yml --profile core --profile bot --profile ml up -d --wait
Подожди пока все healthy.

ЗАДАЧА 2: Проверить что Langfuse доступен
curl -s http://localhost:3001/api/public/health | head -5
Если не отвечает — подожди 30 сек, retry.

ЗАДАЧА 3: Запустить валидацию
uv run python scripts/validate_traces.py --collection legal_documents --report
Если ошибка подключения к Qdrant/Redis — проверь что контейнеры running и retry.
Если ошибка в скрипте — зафиксируй в лог и продолжай.

ЗАДАЧА 4: Если legal_documents прошёл — попробуй contextual_bulgaria_voyage
uv run python scripts/validate_traces.py --collection contextual_bulgaria_voyage --report
Если нет VOYAGE_API_KEY — это OK, запиши в лог и пропусти.

ЗАДАЧА 5: Покажи итоговый отчёт
ls -la docs/reports/
cat последний .md файл из docs/reports/

ПРАВИЛА:
1. НЕ останавливайся на ошибках — логируй и продолжай
2. git commit НЕ нужен (это runtime, не код)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-validate-run.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /home/user/projects/rag-fresh/logs/worker-validate-run.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /home/user/projects/rag-fresh/logs/worker-validate-run.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-validate-run.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-RUN COMPLETE — проверь logs/worker-validate-run.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
