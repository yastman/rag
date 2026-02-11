W-P126: Написать план реализации для issue #126 (Langfuse gold-set dataset + experiments)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 126 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-gold-set-dataset-plan.md
5. Залогируй результат

Рабочая директория: /home/user/projects/rag-fresh

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- scripts/validate_traces.py (текущий validation runner)
- scripts/golden_queries.py (query goldset, если есть)
- tests/baseline/conftest.py (baseline fixtures)
- pyproject.toml (langfuse dependency version)
- telegram_bot/observability.py (Langfuse init)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("Langfuse dataset experiment SDK evaluation pipeline 2026")
- Context7: resolve-library-id(libraryName="langfuse", query="dataset experiment run items SDK") затем query-docs(libraryId, "create dataset items run experiment programmatically SDK Python")
- Context7: query-docs(libraryId, "dataset experiment expected_output scoring evaluation run_item")

ФОРМАТ ПЛАНА:
- Заголовок: "# Langfuse Gold-Set Dataset + Experiments — Implementation Plan"
- Goal, Issue link, Architecture
- Текущее состояние: что есть сейчас (validate_traces, golden_queries)
- Dataset design: какие queries, expected_output, metadata
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-126.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #126" >> logs/worker-plan-126.log
echo "[DONE] $(date +%H:%M:%S) Issue #126: plan written" >> logs/worker-plan-126.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-126.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P126 COMPLETE — проверь logs/worker-plan-126.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
