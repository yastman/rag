W-P108: Написать план реализации для issue #108 (Rewrite stop-guard)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 108 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Напиши план в docs/plans/2026-02-11-rewrite-guard-plan.md
4. Залогируй результат

Рабочая директория: /home/user/projects/rag-fresh

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/graph/nodes/grade.py (route_grade, grade logic, threshold)
- telegram_bot/graph/nodes/rewrite.py (rewrite_node, rewrite_count)
- telegram_bot/graph/state.py (GraphState, rewrite_count field)
- telegram_bot/graph/config.py (GraphConfig, max_rewrite_attempts)
- telegram_bot/graph/builder.py (graph edges, routing)
- telegram_bot/graph/nodes/retrieve.py (retrieve after rewrite)

MCP TOOLS: не требуется (локальный код, graph routing logic)

ФОРМАТ ПЛАНА:
- Заголовок: "# Rewrite Stop-Guard — Implementation Plan"
- Goal: 1-2 предложения
- Issue: https://github.com/yastman/rag/issues/108
- Текущее состояние: таблица файлов с номерами строк, текущие значения threshold/max_rewrite
- Шаги реализации: 2-5 минут каждый, точные файлы и строки
- Включить: score-delta threshold между rewrite iterations, max_rewrites cap enforcement
- Test Strategy: конкретные тест-файлы (tests/unit/graph/)
- Acceptance Criteria: max 1 rewrite, score-delta guard working
- Effort Estimate: S/M/L + часы
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-108.log (APPEND mode):
echo "[START] $(date +%H:%M:%S) Issue #108: rewrite guard plan" >> logs/worker-plan-108.log
... работа ...
echo "[DONE] $(date +%H:%M:%S) Issue #108: plan written" >> logs/worker-plan-108.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-108.log

WEBHOOK (после завершения):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P108 COMPLETE — проверь logs/worker-plan-108.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
