W-P105: Написать план реализации для issue #105 (Close parent tracking issue)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 105 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Напиши план в docs/plans/2026-02-11-latency-parent-close-plan.md
4. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- docs/plans/2026-02-11-parallel-execution-roadmap.md (зависимости, streams)
- gh issue view 105 (для scope и подзадач)

MCP TOOLS: не требуется

ФОРМАТ ПЛАНА:
- Заголовок: "# Latency Parent Issue Close — Implementation Plan"
- Goal, Issue link
- Чеклист подзадач (какие issue должны быть закрыты перед закрытием #105)
- Верификация: что проверить перед закрытием (baseline passed, metrics OK)
- Команда закрытия: gh issue close 105 --comment "..."
- Шаги: 2-5 минут каждый
- Effort Estimate: S
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-105.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #105" >> logs/worker-plan-105.log
echo "[DONE] $(date +%H:%M:%S) Issue #105: plan written" >> logs/worker-plan-105.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-105.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P105 COMPLETE — проверь logs/worker-plan-105.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
