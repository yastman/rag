W-VAL: Implement retry/resilience for validate_traces.py (issue #166)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения задач из плана
2. /requesting-code-review — code review ПОСЛЕ каждого коммита. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion — финальная проверка перед завершением

ПЛАН: /repo/docs/plans/2026-02-12-validation-retry-resilience-plan.md
Работай из /repo
Ветка: fix/166-validation-retry-resilience (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ЗАДАЧИ (выполняй по порядку, все 5 тасок):
- Task 1: Langfuse auth probe with retry (tenacity) — используй auth_check() вместо api.trace.list
- Task 2: Redis flush verification + SKIPPED status
- Task 3: Qdrant API collection discovery (get_collections + suffix matching)
- Task 4: EXTERNAL_DEPENDENCY_UNAVAILABLE status в Go/No-Go report
- Task 5: Final verification (full test suite + make check)

ВАЖНО ПО ПЛАНУ:
- План использует auth_check() (НЕ lf.api.trace.list). Существующий тест test_auth_probe_does_not_flush_client тоже нужно обновить — он проверял mock_lf.api.trace.list, теперь должен проверять mock_lf.auth_check
- Тест test_fails_on_invalid_credentials тоже нужно обновить на auth_check
- Для Task 3: патчить qdrant_client.AsyncQdrantClient (НЕ scripts.validate_traces.AsyncQdrantClient), потому что discover_collections импортирует AsyncQdrantClient внутри функции через from qdrant_client import AsyncQdrantClient

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для актуальной документации SDK/API
- Exa: web_search_exa(query) или get_code_context_exa(query) для поиска решений, примеров кода, свежих best practices

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО тесты для файлов которые ты изменил:
  uv run pytest tests/unit/test_validate_aggregates.py -v
  uv run pytest tests/unit/test_validate_queries.py -v
- НЕ запускай tests/ целиком, НЕ запускай tests/unit/ целиком
- Маппинг source -> test:
  scripts/validate_traces.py -> tests/unit/test_validate_aggregates.py
  scripts/validate_queries.py -> tests/unit/test_validate_queries.py
- Используй --lf для перезапуска только упавших
- Финальная проверка: make check (ruff + mypy)

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы (scripts/validate_traces.py, tests/unit/test_validate_aggregates.py). ЗАПРЕЩЕНО git add -A. ПЕРЕД коммитом: git diff --cached --stat — убедись что ТОЛЬКО нужные файлы.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. ПЕРЕД реализацией внешних SDK/API — Context7 для документации.

ЛОГИРОВАНИЕ в /repo/logs/worker-validation-resilience.log (APPEND):
Перед каждой таской:
echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-validation-resilience.log
После завершения:
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-validation-resilience.log
В конце:
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-validation-resilience.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-VAL COMPLETE — проверь logs/worker-validation-resilience.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Используй ИМЯ окна (claude:ORCH), НЕ индекс. Три ОТДЕЛЬНЫХ вызова Bash tool.
