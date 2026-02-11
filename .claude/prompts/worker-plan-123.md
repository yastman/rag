W-P123: Написать план реализации для issue #123 (Orphan traces + propagate_attributes)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 123 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-orphan-traces-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/observability.py (init_langfuse, observe usage, current propagation)
- telegram_bot/bot.py (handle_query entry point — where trace starts)
- scripts/validate_traces.py (trace validation runner)
- telegram_bot/graph/builder.py (graph construction)
- tests/baseline/conftest.py (smoke test setup — orphan source)
- telegram_bot/graph/nodes/classify.py (first node — trace entry)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Context7: resolve-library-id(libraryName="langfuse", query="propagate_attributes session_id user_id trace context") затем query-docs(libraryId, "propagate_attributes context manager session user tracking nested observe")
- Context7: query-docs(libraryId, "observe decorator trace_id parent child nesting flush")

ФОРМАТ ПЛАНА:
- Заголовок: "# Orphan Traces Cleanup + propagate_attributes — Implementation Plan"
- Goal: 1-2 предложения (82% orphan -> <10%)
- Issue: https://github.com/yastman/rag/issues/123
- Текущее состояние: таблица entry points и их trace поведение
- Root cause analysis: почему 82% orphan
- Шаги реализации: 2-5 минут каждый, точные файлы и строки
- Test Strategy: как верифицировать что orphan % снизился
- Acceptance Criteria: orphan traces < 10%, session_id present
- Effort Estimate: S/M/L + часы
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-123.log (APPEND mode):
echo "[START] $(date +%H:%M:%S) Issue #123: orphan traces plan" >> logs/worker-plan-123.log
... работа ...
echo "[DONE] $(date +%H:%M:%S) Issue #123: plan written" >> logs/worker-plan-123.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-123.log

WEBHOOK (после завершения):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P123 COMPLETE — проверь logs/worker-plan-123.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана
