W-P124: Написать план реализации для issue #124 (TTFT variance + provider metadata)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 124 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-ttft-variance-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/services/llm.py (LLM service, callbacks)
- telegram_bot/bot.py (_write_langfuse_scores)
- telegram_bot/observability.py (Langfuse integration)
- telegram_bot/graph/nodes/generate.py (LLM call node)
- telegram_bot/graph/nodes/rewrite.py (rewrite LLM call)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("LiteLLM callback provider metadata TTFT latency tracking 2026")
- Exa: get_code_context_exa("LiteLLM success callback provider model latency metadata response_cost")
- Context7: resolve-library-id(libraryName="litellm", query="callback provider metadata TTFT") затем query-docs для SDK документации

ФОРМАТ ПЛАНА:
- Заголовок: "# TTFT Variance Investigation + Provider Metadata — Implementation Plan"
- Goal: 1-2 предложения
- Issue: ссылка https://github.com/yastman/rag/issues/124
- Architecture: какие модули затрагиваются
- Tech Stack: библиотеки, версии
- Текущее состояние: таблица файлов с номерами строк, текущими значениями
- Шаги реализации: каждый шаг = 2-5 минут, точные файлы и строки, что менять
- Test Strategy: конкретные тест-файлы
- Acceptance Criteria: измеримые критерии
- Effort Estimate: S/M/L + часы
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела для примеров кода.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-124.log (APPEND mode):
echo "[START] $(date +%H:%M:%S) Issue #124: TTFT variance plan" >> logs/worker-plan-124.log
... работа ...
echo "[DONE] $(date +%H:%M:%S) Issue #124: plan written" >> logs/worker-plan-124.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-124.log

WEBHOOK (после завершения):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P124 COMPLETE — проверь logs/worker-plan-124.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана
