W-P127: Написать план реализации для issue #127 (LLM-as-a-Judge calibration + regression gate)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 127 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-llm-judge-plan.md
5. Залогируй результат

Рабочая директория: /home/user/projects/rag-fresh

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- scripts/validate_traces.py (текущий scoring)
- telegram_bot/integrations/prompt_manager.py (промт менеджмент)
- pyproject.toml (langfuse version)
- telegram_bot/observability.py (Langfuse setup)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("LLM as a Judge evaluation calibration methodology risks 2026")
- Exa: get_code_context_exa("Langfuse managed evaluator LLM judge configuration Python")
- Context7: resolve-library-id(libraryName="langfuse", query="evaluator LLM judge managed") затем query-docs(libraryId, "managed evaluators LLM as a judge setup configuration template scoring")

ФОРМАТ ПЛАНА:
- Заголовок: "# LLM-as-a-Judge Calibration + Regression Gate — Implementation Plan"
- Goal, Issue link, Architecture
- Evaluator design: какие критерии, модель, промт
- Calibration process: как калибровать thresholds
- Regression gate: интеграция в CI/validate
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-127.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #127" >> logs/worker-plan-127.log
echo "[DONE] $(date +%H:%M:%S) Issue #127: plan written" >> logs/worker-plan-127.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-127.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P127 COMPLETE — проверь logs/worker-plan-127.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
