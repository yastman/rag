W-P73: Написать план реализации для issue #73 (k3s production tuning 2026)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 73 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-k3s-tuning-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- k8s/ (все k3s манифесты)
- docker-compose.vps.yml (текущий VPS stack)
- Makefile (k3s targets)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("k3s production tuning 2026 single node best practices containerd Gateway API")
- Exa: get_code_context_exa("k3s Trivy image scanning CI/CD Kubernetes security 2026")

ФОРМАТ ПЛАНА:
- Заголовок: "# k3s Production Tuning (2026) — Implementation Plan"
- Goal, Issue link
- Текущее состояние: текущая k3s версия, config
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-73.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #73" >> logs/worker-plan-73.log
echo "[DONE] $(date +%H:%M:%S) Issue #73: plan written" >> logs/worker-plan-73.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-73.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P73 COMPLETE — проверь logs/worker-plan-73.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
