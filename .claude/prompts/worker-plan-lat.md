W-LAT: Написать планы реализации для issue #124, #106, #108 (Latency stream)

Ты — воркер, пишущий ПЛАНЫ реализации (НЕ код). Для каждого issue:
1. Прочитай issue из GitHub: gh issue view {num} --json title,body,labels,milestone
2. Прочитай исходные файлы проекта, указанные ниже
3. Выполни ресерч через MCP tools (если указано)
4. Напиши план в docs/plans/2026-02-11-{topic}-plan.md
5. Залогируй прогресс

Рабочая директория: /home/user/projects/rag-fresh

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

=== ISSUE #124: TTFT variance + provider metadata ===

Файлы для чтения:
- telegram_bot/services/llm.py (LLM service, callbacks)
- telegram_bot/bot.py (_write_langfuse_scores)
- telegram_bot/observability.py (Langfuse integration)
- telegram_bot/graph/nodes/generate.py (LLM call node)
- telegram_bot/graph/nodes/rewrite.py (rewrite LLM call)

MCP TOOLS (обязательно):
- Exa: web_search_exa("LiteLLM callback provider metadata TTFT latency 2026") для актуальных паттернов
- Exa: get_code_context_exa("LiteLLM success callback provider model latency metadata") для примеров кода
- Context7: resolve-library-id(libraryName="litellm", query="callback provider metadata TTFT") затем query-docs для SDK документации

Выходной файл: docs/plans/2026-02-11-ttft-variance-plan.md

=== ISSUE #106: BGE-M3 cold start + ONNX spike ===

Файлы для чтения:
- telegram_bot/integrations/embeddings.py (embedding client)
- services/bge-m3-api/app.py (BGE-M3 API server)
- docker/bge-m3/Dockerfile (Docker image)
- docker-compose.dev.yml (compose config)
- telegram_bot/graph/nodes/retrieve.py (retrieve node)

MCP TOOLS (обязательно):
- Exa: web_search_exa("BGE-M3 ONNX INT8 CPU inference optimization 2026") для deployment patterns
- Exa: get_code_context_exa("ONNX Runtime BGE-M3 ORTModelForCustomTasks int8 quantization") для примеров
- Context7: resolve-library-id(libraryName="optimum", query="ONNX runtime model export INT8") затем query-docs
- Context7: resolve-library-id(libraryName="onnxruntime", query="session options intra_op CPU optimization") затем query-docs

План должен включать ДВА этапа:
- Quick fix: prewarm при старте + keep-warm ping (до Gate 1)
- ONNX spike: исследование + POC (после Gate 1)

Выходной файл: docs/plans/2026-02-11-bge-cold-start-plan.md

=== ISSUE #108: Rewrite stop-guard ===

Файлы для чтения:
- telegram_bot/graph/nodes/grade.py (route_grade, grade logic)
- telegram_bot/graph/nodes/rewrite.py (rewrite_node)
- telegram_bot/graph/state.py (GraphState, rewrite_count)
- telegram_bot/graph/config.py (GraphConfig, max_rewrite_attempts)
- telegram_bot/graph/builder.py (graph edges)

MCP TOOLS: не требуется (локальный код)

Выходной файл: docs/plans/2026-02-11-rewrite-guard-plan.md

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-lat.log (APPEND mode, >> для каждой записи):
[START] timestamp Issue #N: description
[DONE] timestamp Issue #N: result summary
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-LAT COMPLETE — проверь logs/worker-plan-lat.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документы
2. НЕ используй тройные бэктики в план-файлах — используй 4 пробела для кода
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана для соответствующего issue
