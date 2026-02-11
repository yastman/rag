W-P71: Написать план реализации для issue #71 (Security: pin uv images + update minio CVE)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 71 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-security-pins-plan.md
5. Залогируй результат

Рабочая директория: /home/user/projects/rag-fresh

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- docker/bot/Dockerfile (uv builder image)
- docker/bge-m3/Dockerfile (uv builder image)
- docker/ingestion/Dockerfile (uv builder image)
- docker/litellm/Dockerfile (if exists)
- docker-compose.dev.yml (minio service version)
- docker-compose.vps.yml (minio service version)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("ghcr.io astral-sh uv Docker image digest pinning security 2026")
- Exa: web_search_exa("MinIO CVE 2025 2026 latest secure version")

ФОРМАТ ПЛАНА:
- Заголовок: "# Security: Pin UV Images + Update MinIO — Implementation Plan"
- Goal, Issue link
- Текущее состояние: таблица Dockerfile image references
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-71.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #71" >> logs/worker-plan-71.log
echo "[DONE] $(date +%H:%M:%S) Issue #71: plan written" >> logs/worker-plan-71.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-71.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P71 COMPLETE — проверь logs/worker-plan-71.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
