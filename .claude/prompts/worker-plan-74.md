W-P74: Написать план реализации для issue #74 (PostgresSaver for LangGraph)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 74 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-postgres-saver-plan.md
5. Залогируй результат

Рабочая директория: /home/user/projects/rag-fresh

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/integrations/memory.py (текущий MemorySaver)
- telegram_bot/bot.py (graph compilation with checkpointer)
- telegram_bot/graph/builder.py (graph builder)
- pyproject.toml (langgraph-checkpoint-postgres dependency)
- docker-compose.dev.yml (postgres service)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Context7: resolve-library-id(libraryName="langgraph", query="PostgresSaver checkpoint persistence") затем query-docs(libraryId, "PostgresSaver setup connection_string async checkpoint persistence migration")
- Context7: query-docs(libraryId, "checkpointer PostgresSaver replace MemorySaver configuration")

ФОРМАТ ПЛАНА:
- Заголовок: "# PostgresSaver for LangGraph Persistence — Implementation Plan"
- Goal, Issue link
- Текущее состояние: MemorySaver usage, postgres service availability
- Migration path: MemorySaver -> PostgresSaver
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-74.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #74" >> logs/worker-plan-74.log
echo "[DONE] $(date +%H:%M:%S) Issue #74: plan written" >> logs/worker-plan-74.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-74.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P74 COMPLETE — проверь logs/worker-plan-74.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
