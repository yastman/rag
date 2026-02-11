W-P102: Написать план реализации для issue #102 (Contingency A/B — reasoning_effort, split models)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 102 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-contingency-ab-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/services/llm.py (LLM service, model config, fallback chain)
- telegram_bot/graph/nodes/generate.py (generate call)
- telegram_bot/graph/nodes/rewrite.py (rewrite call)
- telegram_bot/graph/config.py (GraphConfig)
- docker-compose.dev.yml (litellm config)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("reasoning_effort parameter LLM API split models fast rewrite strong generate 2026")
- Exa: get_code_context_exa("LiteLLM reasoning_effort parameter model routing per-request")

ФОРМАТ ПЛАНА:
- Заголовок: "# Contingency A/B: reasoning_effort + Split Models — Implementation Plan"
- Goal, Issue link
- Trigger: только если Gate 1 (#101) fails
- Options: A/B benchmark, reasoning_effort, split models
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-102.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #102" >> logs/worker-plan-102.log
echo "[DONE] $(date +%H:%M:%S) Issue #102: plan written" >> logs/worker-plan-102.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-102.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P102 COMPLETE — проверь logs/worker-plan-102.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
