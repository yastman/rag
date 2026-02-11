W-P129: Написать план реализации для issue #129 (Concise-answer UX)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 129 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Напиши план в docs/plans/2026-02-11-concise-answer-plan.md
4. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/integrations/prompt_manager.py (prompt loading, template management)
- telegram_bot/graph/nodes/generate.py (generate_node, prompt construction)
- telegram_bot/graph/state.py (GraphState)
- telegram_bot/graph/nodes/classify.py (query classification — short vs long)
- telegram_bot/graph/config.py (GraphConfig)

MCP TOOLS: не требуется (промт-инжиниринг, локальный код)

ФОРМАТ ПЛАНА:
- Заголовок: "# Concise Answer UX — Implementation Plan"
- Goal, Issue link
- Текущее состояние: текущий system prompt, query classification
- Стратегия: как определять short query, как менять prompt
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-129.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #129" >> logs/worker-plan-129.log
echo "[DONE] $(date +%H:%M:%S) Issue #129: plan written" >> logs/worker-plan-129.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-129.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P129 COMPLETE — проверь logs/worker-plan-129.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
