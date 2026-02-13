W-EMBED: Tenacity retry + granular timeout for BGEM3HybridEmbeddings (#210)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans -- для пошагового выполнения задач
2. /requesting-code-review -- code review ПОСЛЕ завершения, ПЕРЕД коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) -- просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion -- финальная проверка перед коммитом

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для актуальной документации SDK/API
- Exa: web_search_exa(query) или get_code_context_exa(query) для поиска решений, примеров кода

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-bge-m3-retry-resilience-plan.md
Работай из /home/user/projects/rag-fresh
Ветка: fix/210-bge-m3-retry-resilience (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ЗАДАЧА: Task 1 из плана -- Tenacity Retry + Granular Timeout on BGEM3HybridEmbeddings

Файлы для изменения:
- telegram_bot/integrations/embeddings.py (добавить tenacity retry + granular httpx.Timeout)
- tests/unit/integrations/test_embeddings.py (добавить тесты на retry и timeout)

ЧТО ДЕЛАТЬ (TDD по плану):

Step 1: Добавь тесты в tests/unit/integrations/test_embeddings.py
- Класс TestBGEM3HybridRetry: 4 теста (retry on RemoteProtocolError, raises after max retries, no retry on HTTPStatusError, retry on ConnectTimeout)
- Класс TestBGEM3HybridTimeout: 2 теста (granular timeout, custom timeout override)
- Смотри план для точного кода тестов

Step 2: Убедись что тесты ПАДАЮТ:
  uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridRetry tests/unit/integrations/test_embeddings.py::TestBGEM3HybridTimeout -v

Step 3: Реализуй в telegram_bot/integrations/embeddings.py:
- Добавь импорты tenacity (retry, retry_if_exception_type, wait_exponential_jitter, stop_after_attempt, before_sleep_log, reraise)
- Создай _RETRYABLE_ERRORS tuple и _embed_retry decorator
- Измени конструктор BGEM3HybridEmbeddings: timeout param -> float | httpx.Timeout | None, default None -> httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
- Добавь AsyncHTTPTransport(retries=1) в _get_client
- Добавь @_embed_retry decorator на aembed_hybrid и aembed_hybrid_batch МЕЖДУ @observe и async def
- КРИТИЧНО: порядок декораторов -- @observe (outer), @_embed_retry (inner)

Step 4: Убедись что тесты ПРОХОДЯТ:
  uv run pytest tests/unit/integrations/test_embeddings.py -v

Step 5: Запусти lint:
  uv run ruff check telegram_bot/integrations/embeddings.py tests/unit/integrations/test_embeddings.py
  uv run ruff format --check telegram_bot/integrations/embeddings.py tests/unit/integrations/test_embeddings.py

Step 6: Коммит (ТОЛЬКО эти файлы):
  git add telegram_bot/integrations/embeddings.py tests/unit/integrations/test_embeddings.py
  git diff --cached --stat
  git commit -m "fix(embeddings): add tenacity retry + granular timeout for BGE-M3 #210

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО: uv run pytest tests/unit/integrations/test_embeddings.py -v
- НЕ запускай tests/ целиком, НЕ запускай tests/unit/ целиком
- Маппинг: telegram_bot/integrations/embeddings.py -> tests/unit/integrations/test_embeddings.py

ПРАВИЛА:
1. git commit -- ТОЛЬКО конкретные файлы. НЕ git add -A. ПЕРЕД коммитом: git diff --cached --stat
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите
3. НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-embed-retry.log (APPEND):
Перед каждым шагом пиши в лог через Bash:
  echo "[START] $(date +%H:%M:%S) Step N: description" >> /home/user/projects/rag-fresh/logs/worker-embed-retry.log
После каждого шага:
  echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /home/user/projects/rag-fresh/logs/worker-embed-retry.log
В конце:
  echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-embed-retry.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-EMBED COMPLETE -- проверь logs/worker-embed-retry.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Используй ИМЯ окна "ORCH", НЕ индекс.
