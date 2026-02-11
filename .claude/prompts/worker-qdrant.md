W-QDRANT: Qdrant timeout + FormulaQuery (#122)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-11-qdrant-timeout-plan.md
Работай из /repo

ЗАДАЧИ (выполняй по плану):
- Task 1: Добавить explicit timeout=30 в AsyncQdrantClient
  telegram_bot/config.py: добавить qdrant_timeout: int = Field(default=30, ...)
  telegram_bot/services/qdrant.py: добавить timeout параметр в __init__, передать в AsyncQdrantClient
  Написать тесты TestQdrantServiceTimeout
- Task 2: Migrate search_with_score_boosting на FormulaQuery (server-side)
  Переписать метод: использовать models.FormulaQuery + models.Prefetch
  Обновить тесты в TestQdrantServiceScoreBoosting: удалить client-side tests, добавить FormulaQuery assertions
- Task 3: Bump bot qdrant-client>=1.14.0 в telegram_bot/pyproject.toml и telegram_bot/requirements.txt

MCP TOOLS (используй ПЕРЕД реализацией FormulaQuery):
- Context7: resolve-library-id("qdrant-client", "FormulaQuery prefetch score boosting") затем query-docs для актуального API
- Exa: get_code_context_exa("qdrant FormulaQuery ExpDecayExpression python example") для примеров

ТЕСТЫ (строго по файлам):
  uv run pytest tests/unit/test_qdrant_service.py -v
- Маппинг:
  telegram_bot/services/qdrant.py -> tests/unit/test_qdrant_service.py
  telegram_bot/config.py -> проверяется косвенно
- Финальная проверка: uv run ruff check telegram_bot/services/qdrant.py telegram_bot/config.py tests/unit/test_qdrant_service.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Два коммита: feat(qdrant): add explicit timeout=30 (#122) и feat(qdrant): migrate score boosting to FormulaQuery (#122)

ЛОГИРОВАНИЕ в /repo/logs/worker-qdrant.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-qdrant.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-qdrant.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-qdrant.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:2" "W-QDRANT COMPLETE — проверь logs/worker-qdrant.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:2" Enter
