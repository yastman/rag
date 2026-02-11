W-OBS: Написать планы реализации для issue #103, #123, #91 (Observability stream)

Ты — воркер, пишущий ПЛАНЫ реализации (НЕ код). Для каждого issue:
1. Прочитай issue из GitHub: gh issue view {num} --json title,body,labels,milestone
2. Прочитай исходные файлы проекта, указанные ниже
3. Выполни ресерч через MCP tools (если указано)
4. Напиши план в docs/plans/2026-02-11-{topic}-plan.md
5. Залогируй прогресс

Рабочая директория: /repo

ФОРМАТ ПЛАНА (каждый файл):
- Заголовок: "# {Title} Implementation Plan"
- Goal: 1-2 предложения
- Architecture: какие модули затрагиваются
- Tech Stack: библиотеки, версии
- Issue: ссылка на GitHub issue
- Текущее состояние: таблица файлов с номерами строк, текущими значениями
- Шаги реализации: каждый шаг = 2-5 минут, точные файлы и строки, что менять
- Test Strategy: конкретные тест-файлы, что проверять
- Acceptance Criteria: измеримые критерии
- Effort Estimate: S/M/L + часы
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела для кода.

=== ISSUE #103: Cache hit scores + error spans in Langfuse ===

Файлы для чтения:
- telegram_bot/bot.py (_write_langfuse_scores method)
- telegram_bot/graph/state.py (GraphState fields)
- telegram_bot/graph/nodes/cache_check.py (cache check logic)
- telegram_bot/graph/nodes/retrieve.py (retrieve logic)
- telegram_bot/graph/nodes/rerank.py (rerank logic)
- telegram_bot/observability.py (Langfuse setup)

MCP TOOLS (обязательно):
- Context7: resolve-library-id(libraryName="langfuse", query="scores trace update numeric boolean") затем query-docs(libraryId, "how to write numeric scores to traces using langfuse SDK")
- Context7: query-docs(libraryId, "error spans exception tracking observe decorator")

Выходной файл: docs/plans/2026-02-11-langfuse-scores-plan.md

=== ISSUE #123: Orphan traces + propagate_attributes ===

Файлы для чтения:
- telegram_bot/observability.py (init_langfuse, observe usage)
- telegram_bot/bot.py (handle_query entry point)
- scripts/validate_traces.py (trace validation)
- telegram_bot/graph/builder.py (graph construction)
- tests/baseline/conftest.py (smoke test setup)

MCP TOOLS (обязательно):
- Context7: resolve-library-id(libraryName="langfuse", query="propagate_attributes session_id user_id trace context") затем query-docs(libraryId, "propagate_attributes context manager for session and user tracking")
- Context7: query-docs(libraryId, "observe decorator nested traces parent child relationship")

Выходной файл: docs/plans/2026-02-11-orphan-traces-plan.md

=== ISSUE #91: Audit remediation (CI + smoke tests) ===

Файлы для чтения:
- .github/workflows/ci.yml (CI pipeline)
- tests/smoke/test_zoo_smoke.py (legacy smoke tests)
- telegram_bot/integrations/cache.py (CacheLayerManager)
- Makefile (test targets)
- pyproject.toml (dependencies, test config)

MCP TOOLS: не требуется (локальный код, CI конфигурация)

Выходной файл: docs/plans/2026-02-11-audit-remediation-plan.md

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-obs.log (APPEND mode, >> для каждой записи):
[START] timestamp Issue #N: description
[DONE] timestamp Issue #N: result summary
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-OBS COMPLETE — проверь logs/worker-plan-obs.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документы
2. НЕ используй тройные бэктики в план-файлах — используй 4 пробела для кода
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана для соответствующего issue
