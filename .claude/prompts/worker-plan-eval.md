W-EVAL: Написать планы реализации для issue #126, #127, #129, #102 (Quality-Eval stream)

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

=== ISSUE #126: Gold-set dataset in Langfuse ===

Файлы для чтения:
- scripts/validate_traces.py (текущий validation runner)
- scripts/golden_queries.py (query goldset если есть)
- tests/baseline/conftest.py (baseline fixtures)
- pyproject.toml (langfuse dependency version)

MCP TOOLS (обязательно):
- Exa: web_search_exa("Langfuse dataset experiment SDK evaluation pipeline 2026") для best practices
- Context7: resolve-library-id(libraryName="langfuse", query="dataset experiment run items SDK") затем query-docs(libraryId, "create dataset items run experiment programmatically SDK Python")
- Context7: query-docs(libraryId, "dataset experiment expected_output scoring evaluation")

Выходной файл: docs/plans/2026-02-11-gold-set-dataset-plan.md

=== ISSUE #127: LLM-as-a-Judge calibration + regression gate ===

Файлы для чтения:
- scripts/validate_traces.py (текущий scoring)
- telegram_bot/integrations/prompt_manager.py (промт менеджмент)
- pyproject.toml (langfuse version)

MCP TOOLS (обязательно):
- Exa: web_search_exa("LLM as a Judge evaluation calibration methodology risks 2026") для методологии
- Exa: get_code_context_exa("Langfuse managed evaluator LLM judge configuration Python") для примеров
- Context7: resolve-library-id(libraryName="langfuse", query="evaluator LLM judge managed configuration") затем query-docs(libraryId, "managed evaluators LLM as a judge setup configuration template")

Выходной файл: docs/plans/2026-02-11-llm-judge-plan.md

=== ISSUE #129: Concise-answer UX ===

Файлы для чтения:
- telegram_bot/integrations/prompt_manager.py (prompt loading)
- telegram_bot/graph/nodes/generate.py (generate_node, prompt construction)
- telegram_bot/graph/state.py (GraphState)
- prompts/ (prompt templates directory, if exists)

MCP TOOLS: не требуется (промт-инжиниринг, локальный код)

Выходной файл: docs/plans/2026-02-11-concise-answer-plan.md

=== ISSUE #102: Contingency A/B (reasoning_effort, split models) ===

Файлы для чтения:
- telegram_bot/services/llm.py (LLM service, model config)
- telegram_bot/graph/nodes/generate.py (generate call)
- telegram_bot/graph/nodes/rewrite.py (rewrite call)
- telegram_bot/graph/config.py (GraphConfig)

MCP TOOLS (обязательно):
- Exa: web_search_exa("reasoning_effort parameter LLM API split models fast rewrite strong generate 2026") для актуальных паттернов
- Exa: get_code_context_exa("LiteLLM reasoning_effort parameter model routing") для примеров

Выходной файл: docs/plans/2026-02-11-contingency-ab-plan.md

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-eval.log (APPEND mode, >> для каждой записи):
[START] timestamp Issue #N: description
[DONE] timestamp Issue #N: result summary
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-EVAL COMPLETE — проверь logs/worker-plan-eval.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документы
2. НЕ используй тройные бэктики в план-файлах — используй 4 пробела для кода
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана для соответствующего issue
