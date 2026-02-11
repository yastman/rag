W-P101: Написать план реализации для issue #101 (Re-baseline latency + Go/No-Go gate)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 101 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Напиши план в docs/plans/2026-02-11-re-baseline-plan.md
4. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- scripts/validate_traces.py (trace validation runner)
- scripts/golden_queries.py (query goldset, если есть)
- telegram_bot/bot.py (bot entry, scores)
- Makefile (validate-traces-fast target)
- docs/plans/2026-02-11-parallel-execution-roadmap.md (gate criteria)

MCP TOOLS: не требуется (процесс валидации)

ФОРМАТ ПЛАНА:
- Заголовок: "# Re-Baseline Latency + Go/No-Go Gate — Implementation Plan"
- Goal, Issue link
- Prerequisities: какие issue ДОЛЖНЫ быть закрыты до baseline
- Процедура: какие запросы, сколько, какие типы (FAQ/GENERAL/STRUCTURED)
- Go/No-Go criteria: p50/p90 latency, cache hit, orphan traces %
- Как фиксировать baseline trace IDs
- Contingency path если fail (#102)
- Шаги реализации: 2-5 минут каждый
- Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-101.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #101" >> logs/worker-plan-101.log
echo "[DONE] $(date +%H:%M:%S) Issue #101: plan written" >> logs/worker-plan-101.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-101.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P101 COMPLETE — проверь logs/worker-plan-101.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
