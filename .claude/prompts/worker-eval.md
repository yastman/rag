W-EVAL: Fix Settings env-independence in tests + evaluation lazy init (#191)

SKILLS (вызывай В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения задач
2. /requesting-code-review — code review ПОСЛЕ всех фиксов, ПЕРЕД коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику
3. /verification-before-completion — финальная проверка перед коммитом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-ci-green-sweep-design.md
Работай из /home/user/projects/rag-fresh
Ветка: fix/191-ci-green-sweep (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ЗАДАЧИ (выполняй по порядку):

Task 4: Fix RAGPipeline test env-independence (#186)
  Файл: tests/unit/core/test_pipeline.py
  Проблема: test_pipeline_init_default_settings вызывает RAGPipeline() без аргументов.
  RAGPipeline() создает Settings() который вызывает _validate_api_keys() и падает с
  ValueError: ANTHROPIC_API_KEY not set and API_PROVIDER=claude.
  Тест патчит 6 downstream зависимостей но НЕ окружение для Settings.
  Фикс: оберни вызов RAGPipeline() в patch.dict для env:

  Добавь import os в начало файла (если его нет).
  В метод test_pipeline_init_default_settings, замени:
    pipeline = RAGPipeline()
  На:
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-for-ci"}):
        pipeline = RAGPipeline()

  Аналогично проверь другие тесты в этом файле которые создают RAGPipeline() без Settings.
  Каждый вызов RAGPipeline() без явного settings= должен быть обёрнут в patch.dict.

Task 5a: Lazy Settings() in extract_ground_truth.py (#187)
  Файл: src/evaluation/extract_ground_truth.py
  Проблема: строки 14-21 — module-level Settings() + module constants:
    sys.path.append("/home/admin/contextual_rag")
    from src.config import Settings
    _settings = Settings()
    QDRANT_URL = _settings.qdrant_url
    QDRANT_API_KEY = _settings.qdrant_api_key or ""

  Фикс:
  1. Удали строку sys.path.append("/home/admin/contextual_rag") — legacy VPS artifact.
  2. Оставь from src.config import Settings (он работает из текущего проекта).
  3. Замени module-level _settings на lazy:

  from functools import lru_cache

  @lru_cache(maxsize=1)
  def _get_settings() -> "Settings":
      return Settings()

  def _qdrant_url() -> str:
      return _get_settings().qdrant_url

  def _qdrant_api_key() -> str:
      return _get_settings().qdrant_api_key or ""

  4. Во всех функциях замени QDRANT_URL на _qdrant_url() и QDRANT_API_KEY на _qdrant_api_key().
     Используй grep/search чтобы найти все использования QDRANT_URL и QDRANT_API_KEY в файле.

  5. В тестах (tests/unit/evaluation/test_extract_ground_truth.py) обнови patches:
     @patch("src.evaluation.extract_ground_truth.QDRANT_API_KEY", "test_key")
     -> @patch("src.evaluation.extract_ground_truth._qdrant_api_key", return_value="test_key")
     @patch("src.evaluation.extract_ground_truth.QDRANT_URL", "http://localhost:6333")
     -> @patch("src.evaluation.extract_ground_truth._qdrant_url", return_value="http://localhost:6333")

Task 5b: Lazy Settings() in search_engines.py (#188)
  Файл: src/evaluation/search_engines.py
  Проблема: строки 15-22 — аналогично extract_ground_truth.py:
    sys.path.append("/home/admin/contextual_rag")
    from src.config import HSNWParameters, RetrievalStages, Settings, ThresholdValues
    _settings = Settings()
    QDRANT_URL = _settings.qdrant_url
    QDRANT_API_KEY = _settings.qdrant_api_key or ""

  Фикс: тот же паттерн что в Task 5a:
  1. Удали sys.path.append("/home/admin/contextual_rag").
  2. Замени module-level _settings на lazy lru_cache pattern.
  3. Оставь module-level constants из enums (HNSW_EF_HIGH_PRECISION, SCORE_THRESHOLD_HYBRID и т.д.)
     — они НЕ зависят от env, это просто значения из enums.
  4. Замени QDRANT_URL/QDRANT_API_KEY на _qdrant_url()/_qdrant_api_key() во всех функциях.
  5. В search_engines.py — найди ВСЕ использования QDRANT_URL и QDRANT_API_KEY через grep.
     Классы BaselineSearchEngine, HybridSearchEngine и др. используют эти переменные
     в __init__ и/или методах. Замени на вызовы _qdrant_url()/_qdrant_api_key().
  6. В тестах (tests/unit/evaluation/test_search_engines_eval.py) — если тесты патчат
     QDRANT_URL/QDRANT_API_KEY напрямую, обнови patches аналогично Task 5a.
     НО: тесты могут использовать lazy imports внутри тестов и не патчить эти переменные.
     Прочитай тестовый файл и определи нужны ли изменения.

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query)
  Используй для проверки functools.lru_cache pattern если не уверен
- Exa: get_code_context_exa(query) для поиска примеров lazy Settings initialization

ТЕСТЫ (строго по файлам):
- После Task 4: uv run pytest tests/unit/core/test_pipeline.py -v
- После Task 5a: uv run pytest tests/unit/evaluation/test_extract_ground_truth.py -v
- После Task 5b: uv run pytest tests/unit/evaluation/test_search_engines_eval.py -v
- Маппинг:
  tests/unit/core/test_pipeline.py -> uv run pytest tests/unit/core/test_pipeline.py -v
  src/evaluation/extract_ground_truth.py -> uv run pytest tests/unit/evaluation/test_extract_ground_truth.py -v
  src/evaluation/search_engines.py -> uv run pytest tests/unit/evaluation/test_search_engines_eval.py -v

ЗАПРЕЩЕНО: git add -A. ПЕРЕД коммитом: git diff --cached --stat — убедись что ТОЛЬКО нужные файлы.
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
Commit message: fix(ci): decouple test pipeline from env + lazy eval Settings (#191)
Scope коммита: tests/unit/core/test_pipeline.py, src/evaluation/extract_ground_truth.py, src/evaluation/search_engines.py, tests/unit/evaluation/test_extract_ground_truth.py, tests/unit/evaluation/test_search_engines_eval.py (если затронут)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-eval.log (APPEND):
Каждое действие логируй в файл через >> (append). Формат:
[START] timestamp Task N: description
[DONE] timestamp Task N: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:Claude2" "W-EVAL COMPLETE — проверь logs/worker-eval.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:Claude2" Enter
ВАЖНО: Используй ИМЯ окна "Claude2", НЕ индекс. Индекс сдвигается при kill-window.
