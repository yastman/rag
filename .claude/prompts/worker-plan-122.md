W-P122: Написать план реализации для issue #122 (Qdrant timeout + FormulaQuery)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 122 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-qdrant-timeout-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/services/qdrant.py (QdrantService, search methods, client init)
- src/retrieval/search_engines.py (search variants, score boosting)
- pyproject.toml (qdrant-client version)
- docker-compose.dev.yml (qdrant service config)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Context7: resolve-library-id(libraryName="qdrant-client", query="timeout query API FormulaQuery") затем query-docs(libraryId, "AsyncQdrantClient timeout configuration grpc rest options")
- Context7: query-docs(libraryId, "FormulaQuery server-side score boosting formula rescore query API")

ФОРМАТ ПЛАНА:
- Заголовок: "# Qdrant Timeout + FormulaQuery Score Boosting — Implementation Plan"
- Goal, Issue link, Architecture, Tech Stack
- Текущее состояние: таблица client init params, search methods
- Шаги реализации: 2-5 минут каждый, точные файлы и строки
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-122.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #122" >> logs/worker-plan-122.log
echo "[DONE] $(date +%H:%M:%S) Issue #122: plan written" >> logs/worker-plan-122.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-122.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P122 COMPLETE — проверь logs/worker-plan-122.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
