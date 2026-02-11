W-INFRA: Validate Traces — Makefile targets + .gitignore

Работай из /repo.

ЗАДАЧИ (выполняй по порядку):

ЗАДАЧА 1 (Task 6 из плана): Add Makefile targets for trace validation
Файл: Makefile
Вставь ПОСЛЕ секции QDRANT BACKUP (после строки 757, перед секцией K3S DEPLOYMENT):

Содержимое для вставки (ТОЧНО как есть):
Секция с заголовком TRACE VALIDATION (#110)
Два .PHONY target: validate-traces validate-traces-fast

validate-traces: ## Full rebuild + trace validation + report
	@echo "$(BLUE)Full rebuild + validation...$(NC)"
	$(COMPOSE_CMD) build --no-cache telegram-bot litellm bge-m3
	$(COMPOSE_CMD) --profile core --profile bot --profile ml up -d --wait
	uv run python scripts/validate_traces.py --report
	@echo "$(GREEN)Validation complete — see docs/reports/$(NC)"

validate-traces-fast: ## No rebuild, just start stack + trace validation + report
	@echo "$(BLUE)Fast validation (no rebuild)...$(NC)"
	$(COMPOSE_CMD) --profile core --profile bot --profile ml up -d --wait
	uv run python scripts/validate_traces.py --report
	@echo "$(GREEN)Validation complete — see docs/reports/$(NC)"

Переменные уже определены в Makefile:
- COMPOSE_CMD := docker compose --compatibility -f docker-compose.dev.yml (line 308)
- BLUE, GREEN, NC (lines 20-24)

ВАЖНО: используй TABS (не пробелы) для рецептов в Makefile!

Проверка: make help | grep validate — оба target должны быть видны.

ЗАДАЧА 2 (Task 9 из плана): Add docs/reports/ to .gitignore
Файл: .gitignore
Добавь в конец файла:
# Validation reports (generated, not committed)
docs/reports/

Затем создай директорию:
mkdir -p docs/reports
touch docs/reports/.gitkeep

Коммит:
git add .gitignore docs/reports/.gitkeep
git commit (conventional commit format, scope=validation, ref #110)

ЗАДАЧА 3: Commit Makefile
git add Makefile
git commit (conventional commit format, scope=validation, ref #110)

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.

ЛОГИРОВАНИЕ в /repo/logs/worker-validate-infra.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-validate-infra.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-validate-infra.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-validate-infra.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:2" "W-INFRA COMPLETE — проверь logs/worker-validate-infra.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:2" Enter
