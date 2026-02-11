W-P72: Написать план реализации для issue #72 (BuildKit cache mounts + slim Docker images)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 72 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-buildkit-slim-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- docker/bot/Dockerfile (current build)
- docker/bge-m3/Dockerfile (ML image, large)
- docker/ingestion/Dockerfile (ingestion build)
- docker-bake.hcl (bake targets)
- docker-compose.dev.yml (litellm version)
- docker-compose.vps.yml (litellm version)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("Docker BuildKit cache mount uv pip best practices 2026 multi-stage slim")
- Exa: get_code_context_exa("Dockerfile BuildKit mount=type=cache target uv pip multi-stage Python")

ФОРМАТ ПЛАНА:
- Заголовок: "# BuildKit Cache Mounts + Slim Docker Images — Implementation Plan"
- Goal, Issue link
- Текущее состояние: таблица image sizes, build times
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-72.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #72" >> logs/worker-plan-72.log
echo "[DONE] $(date +%H:%M:%S) Issue #72: plan written" >> logs/worker-plan-72.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-72.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P72 COMPLETE — проверь logs/worker-plan-72.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
