W-CODE: Validate Traces Script — Python code + tests + lint

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-10-validate-traces-implementation.md
Работай из /repo.

КОНТЕКСТ:
- Issue #110: rebuild containers + capture Langfuse traces для валидации
- Дизайн: docs/plans/2026-02-10-runtime-rebuild-trace-validation.md
- План содержит "Critical additions" блоки после code snippets в Tasks 2, 3, 4 — это ОБЯЗАТЕЛЬНЫЕ требования. Реализуй ВСЕ "Critical additions" в коде задачи.

ЗАДАЧИ (выполняй по порядку):
- Task 1: Create scripts/validate_queries.py (query definitions)
- Task 2: Create scripts/validate_traces.py (runner skeleton + preflight)
  CRITICAL: add check_langfuse_config(), detect_runner_mode(collection)
- Task 3: Add pipeline execution logic (run_single_query, run_collection_validation)
  CRITICAL: update_current_trace + scores INSIDE @observe context. aclose() for embeddings/sparse
- Task 4: Add metrics aggregation + report generation
  CRITICAL: add enrich_results_from_langfuse(run_id, results), fetch_reference_trace_metrics(REFERENCE_TRACE_ID), score_rate() with Langfuse-first fallback
- Task 5: Add main() CLI entrypoint
- Task 7: Unit tests for query module (tests/unit/test_validate_queries.py)
- Task 8: Unit tests for aggregation (tests/unit/test_validate_aggregates.py)
- Task 10: Linter + type checks + format

Функции, которых НЕТ в code snippets, но ТРЕБУЮТСЯ планом:
- check_langfuse_config() — preflight: проверить LANGFUSE_SECRET_KEY + LANGFUSE_HOST, fail-fast
- detect_runner_mode(collection) -> "langgraph_bge" | "voyage_compatible"
- enrich_results_from_langfuse(run_id, results) -> обогатить TraceResult.scores и .node_spans_ms из Langfuse API по trace_id
- fetch_reference_trace_metrics(REFERENCE_TRACE_ID) -> dict с latency_total_ms, rerank_applied и др.

Ключевые файлы для справки:
- telegram_bot/bot.py:39-65 — _write_langfuse_scores (12 scores)
- telegram_bot/bot.py:229-281 — handle_query (observe + propagate_attributes + graph.ainvoke)
- telegram_bot/graph/graph.py:17-43 — build_graph() signature
- telegram_bot/graph/state.py:42-69 — make_initial_state()
- telegram_bot/graph/config.py:61-85 — GraphConfig.from_env()
- telegram_bot/observability.py:102-137 — observe, get_client, propagate_attributes
- tests/baseline/collector.py — LangfuseMetricsCollector (reference for Langfuse API patterns)

Важно:
- lf.create_trace_id() — проверь через Context7 Langfuse SDK docs, что этот метод существует. Если нет — используй str(uuid4()) как fallback
- update_current_trace + _write_langfuse_scores ВНУТРИ @observe context
- score_rate() приоритет: r.scores (Langfuse) -> r.state (local fallback)

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName="langfuse", query="create trace id, fetch traces, get scores") затем query-docs(libraryId, query) для актуальной документации Langfuse Python SDK v3
- Exa: get_code_context_exa(query) для поиска примеров Langfuse SDK usage

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО тесты для файлов которые ты изменил:
  uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v
- НЕ запускай tests/ целиком, НЕ запускай tests/unit/ целиком
- Маппинг source -> test:
  scripts/validate_queries.py -> tests/unit/test_validate_queries.py
  scripts/validate_traces.py -> tests/unit/test_validate_aggregates.py
- Используй --lf для перезапуска только упавших
- Финальная проверка: только затронутые тест-файлы + ruff check + ruff format

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. ПЕРЕД реализацией Langfuse SDK API — Context7 для документации.
4. Ruff line-length = 100.

ЛОГИРОВАНИЕ в /repo/logs/worker-validate-code.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-validate-code.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-validate-code.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-validate-code.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:2" "W-CODE COMPLETE — проверь logs/worker-validate-code.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:2" Enter
