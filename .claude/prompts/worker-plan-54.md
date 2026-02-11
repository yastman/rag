W-P54: Написать план реализации для issue #54 (Migrate VPS from Docker Compose to k3s)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 54 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-k3s-migration-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- docker-compose.vps.yml (текущий VPS stack — 9 сервисов)
- k8s/ (существующие k3s манифесты)
- Makefile (k3s targets: k3s-secrets, k3s-push-bot, k3s-bot, k3s-status)
- docs/plans/2026-02-05-vps-deployment-plan.md (предыдущий deployment plan)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("Docker Compose to k3s migration single node 2026 best practices rollout")
- Exa: get_code_context_exa("k3s deployment migration Docker Compose Kubernetes manifests kompose")

ФОРМАТ ПЛАНА:
- Заголовок: "# VPS Migration: Docker Compose to k3s — Implementation Plan"
- Goal, Issue link
- Текущее состояние: 9 сервисов, текущий docker-compose
- Prerequisites: #73 (k3s tuning), #70 (snapshots), #72 (slim images)
- Migration phases: staged rollout (не big-bang)
- Rollback plan
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate: XL
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-54.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #54" >> logs/worker-plan-54.log
echo "[DONE] $(date +%H:%M:%S) Issue #54: plan written" >> logs/worker-plan-54.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-54.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P54 COMPLETE — проверь logs/worker-plan-54.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
