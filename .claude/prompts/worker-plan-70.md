W-P70: Написать план реализации для issue #70 (Qdrant snapshots for backup)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 70 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-qdrant-snapshots-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/services/qdrant.py (QdrantService, client usage)
- src/ingestion/unified/pipeline.py (ingestion pipeline, before re-index)
- docker-compose.dev.yml (qdrant volumes)
- docker-compose.vps.yml (qdrant volumes)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Context7: resolve-library-id(libraryName="qdrant-client", query="snapshot create restore backup") затем query-docs(libraryId, "create_snapshot list_snapshots restore_snapshot collection backup")

ФОРМАТ ПЛАНА:
- Заголовок: "# Qdrant Snapshots for Backup — Implementation Plan"
- Goal, Issue link
- Текущее состояние: текущий backup процесс (или его отсутствие)
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-70.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #70" >> logs/worker-plan-70.log
echo "[DONE] $(date +%H:%M:%S) Issue #70: plan written" >> logs/worker-plan-70.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-70.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P70 COMPLETE — проверь logs/worker-plan-70.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
4. MCP tools ПЕРЕД написанием плана
