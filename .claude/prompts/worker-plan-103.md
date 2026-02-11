W-P103: Написать план реализации для issue #103 (Cache hit scores + error spans)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 103 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-langfuse-scores-plan.md
5. Залогируй результат

Рабочая директория: /home/user/projects/rag-fresh

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/bot.py (_write_langfuse_scores method — найди все 12 scores)
- telegram_bot/graph/state.py (GraphState fields)
- telegram_bot/graph/nodes/cache_check.py (cache check logic)
- telegram_bot/graph/nodes/retrieve.py (retrieve logic, search_cache_hit)
- telegram_bot/graph/nodes/rerank.py (rerank logic, rerank_cache_hit)
- telegram_bot/graph/nodes/grade.py (confidence_score)
- telegram_bot/observability.py (Langfuse setup, @observe)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Context7: resolve-library-id(libraryName="langfuse", query="scores trace update numeric boolean") затем query-docs(libraryId, "how to write numeric and boolean scores to traces using langfuse Python SDK")
- Context7: query-docs(libraryId, "observe decorator error tracking exception spans")

ФОРМАТ ПЛАНА:
- Заголовок: "# Langfuse Real Scores + Error Spans — Implementation Plan"
- Goal: 1-2 предложения
- Issue: https://github.com/yastman/rag/issues/103
- Текущее состояние: таблица всех 12 scores с текущим статусом (real/hardcoded 0.0)
- Шаги реализации: 2-5 минут каждый, точные файлы и строки
- Test Strategy: конкретные тест-файлы
- Acceptance Criteria: 12/12 scores real, error spans visible
- Effort Estimate: S/M/L + часы
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-103.log (APPEND mode):
echo "[START] $(date +%H:%M:%S) Issue #103: langfuse scores plan" >> logs/worker-plan-103.log
... работа ...
echo "[DONE] $(date +%H:%M:%S) Issue #103: plan written" >> logs/worker-plan-103.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-103.log

WEBHOOK (после завершения):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P103 COMPLETE — проверь logs/worker-plan-103.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана
