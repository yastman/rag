W-P75: Написать план реализации для issue #75 (LangGraph astream for Telegram)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 75 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-astream-plan.md
5. Залогируй результат

Рабочая директория: /home/user/projects/rag-fresh

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/bot.py (handle_query — текущий ainvoke)
- telegram_bot/graph/builder.py (graph construction)
- telegram_bot/graph/nodes/generate.py (generate node — LLM output)
- telegram_bot/graph/nodes/respond.py (respond node — Telegram send)
- telegram_bot/graph/state.py (GraphState)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Context7: resolve-library-id(libraryName="langgraph", query="astream streaming events tokens") затем query-docs(libraryId, "astream stream_mode messages events token streaming StateGraph")
- Context7: query-docs(libraryId, "streaming LLM tokens astream_events node output")

ФОРМАТ ПЛАНА:
- Заголовок: "# LangGraph astream for Telegram UX — Implementation Plan"
- Goal, Issue link
- Текущее состояние: текущий ainvoke flow
- Streaming architecture: astream -> message editing in Telegram
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-75.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #75" >> logs/worker-plan-75.log
echo "[DONE] $(date +%H:%M:%S) Issue #75: plan written" >> logs/worker-plan-75.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-75.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P75 COMPLETE — проверь logs/worker-plan-75.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
