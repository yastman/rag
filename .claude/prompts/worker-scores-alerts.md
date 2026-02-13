W-SCORES: Langfuse scores + Loki alerts for BGE-M3 embedding errors (#210)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans -- для пошагового выполнения задач
2. /requesting-code-review -- code review ПОСЛЕ завершения, ПЕРЕД коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) -- просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion -- финальная проверка перед коммитом

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для актуальной документации SDK/API
- Exa: web_search_exa(query) или get_code_context_exa(query) для поиска решений, примеров кода

ПЛАН: /repo/docs/plans/2026-02-12-bge-m3-retry-resilience-plan.md
Работай из /repo
Ветка: fix/210-bge-m3-retry-resilience (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ЗАДАЧИ: Task 3 + Task 4 из плана

-- TASK 3: Langfuse Scores for Embedding Errors --

Файлы:
- telegram_bot/bot.py (добавить 2 scores в _write_langfuse_scores)
- tests/unit/test_bot_handlers.py (добавить тест)

Step 1: Добавь тест в tests/unit/test_bot_handlers.py
- В класс TestWriteLangfuseScores добавь метод test_writes_embedding_error_score:
  - Импортируй _write_langfuse_scores из telegram_bot.bot
  - Создай mock_lf = MagicMock()
  - result dict с embedding_error=True, embedding_error_type="RemoteProtocolError", latency_stages с cache_check
  - Вызови _write_langfuse_scores(mock_lf, result)
  - Проверь что calls содержит bge_embed_error=1 и bge_embed_latency_ms

Step 2: Убедись что тест ПАДАЕТ:
  uv run pytest tests/unit/test_bot_handlers.py::TestWriteLangfuseScores::test_writes_embedding_error_score -v

Step 3: Реализуй в telegram_bot/bot.py
- После секции "Voice transcription scores (#151)" (около строки 155), добавь:
  - Комментарий: # --- Embedding resilience (#210) ---
  - bge_embed_error: BOOLEAN score (1 if embedding_error else 0)
  - bge_embed_latency_ms: NUMERIC score from latency_stages["cache_check"] * 1000 (если есть)

Step 4: Убедись что тесты ПРОХОДЯТ:
  uv run pytest tests/unit/test_bot_handlers.py::TestWriteLangfuseScores -v

Step 5: Lint:
  uv run ruff check telegram_bot/bot.py tests/unit/test_bot_handlers.py
  uv run ruff format --check telegram_bot/bot.py tests/unit/test_bot_handlers.py

Step 6: Коммит Task 3:
  git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
  git diff --cached --stat
  git commit -m "feat(observability): add Langfuse scores for BGE-M3 embedding errors #210

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

-- TASK 4: Loki Alert Rules --

Файл: docker/monitoring/rules/infrastructure.yaml

Step 7: В infrastructure.yaml, после секции EMBEDDING SERVICES (после alert EmbeddingServiceError, около строки 202), добавь 2 правила:

Правило 1 -- BGEEmbedRetryFromBot:
- expr: count_over_time вокруг {container="dev-bot"} |= "Retrying telegram_bot.integrations.embeddings" за 5m > 3
- for: 3m, severity: warning, service: bge-m3
- summary: "BGE-M3 embedding retries detected in bot"

Правило 2 -- BGEEmbedErrorFromBot:
- expr: count_over_time вокруг {container="dev-bot"} |= "Embedding failed after retries" за 5m > 0
- for: 1m, severity: critical, service: bge-m3
- summary: "BGE-M3 embedding failures in bot"

ВАЖНО: Используй |= (exact match) а НЕ |~ (regex). Exact match быстрее и надежнее для Loki.
ВАЖНО: Выровняй YAML строго по 6 пробелов для alert (на уровне siblings).

Step 8: Проверь YAML синтаксис:
  python -c "import yaml; yaml.safe_load(open('docker/monitoring/rules/infrastructure.yaml'))"

Step 9: Коммит Task 4:
  git add docker/monitoring/rules/infrastructure.yaml
  git diff --cached --stat
  git commit -m "feat(alerts): add Loki rules for BGE-M3 embed retries and failures #210

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

ТЕСТЫ (строго по файлам):
- Task 3: uv run pytest tests/unit/test_bot_handlers.py::TestWriteLangfuseScores -v
- Task 4: YAML validation only (no test runner for Loki rules)
- НЕ запускай tests/ целиком
- Маппинг: telegram_bot/bot.py -> tests/unit/test_bot_handlers.py

ПРАВИЛА:
1. git commit -- ТОЛЬКО конкретные файлы. НЕ git add -A. ПЕРЕД коммитом: git diff --cached --stat
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите
3. НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки

ЛОГИРОВАНИЕ в /repo/logs/worker-scores-alerts.log (APPEND):
Перед каждым шагом:
  echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-scores-alerts.log
После каждого шага:
  echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-scores-alerts.log
В конце:
  echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-scores-alerts.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-SCORES COMPLETE -- проверь logs/worker-scores-alerts.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Используй ИМЯ окна "ORCH", НЕ индекс.
