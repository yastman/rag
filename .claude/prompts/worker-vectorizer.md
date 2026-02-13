W-VECTORIZER: Migrate vectorizers to redisvl 0.14.0 internal API

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /repo/docs/plans/2026-02-11-vectorizer-api-migration-design.md
Работай из /repo. GitHub Issue: #155.

ЗАДАЧИ (выполняй по порядку):

Task 1: Migrate UserBaseVectorizer (telegram_bot/services/vectorizers.py)
  - Заменить public overrides (embed, embed_many, aembed, aembed_many) на internal (_embed, _embed_many, _aembed, _aembed_many)
  - Сигнатуры: _embed(self, content: Any = "", text: Any = "", **kwargs: Any) -> list[float]
  - Используй str(content or text) для получения значения
  - Для _embed_many: _embed_many(self, contents: list[Any] | None = None, texts: list[Any] | None = None, batch_size: int = 10, **kwargs: Any)
  - Используй values = [str(c) for c in (contents or texts or [])]
  - Удали preprocess, as_buffer параметры — ими управляет base class
  - НЕ трогай __init__, _get_sync_client, _get_async_client, aclose — они остаются

Task 2: Migrate BgeM3CacheVectorizer (telegram_bot/services/vectorizers.py)
  - Заменить embed/embed_many на _embed/_embed_many (оба raise NotImplementedError)
  - Заменить aembed/aembed_many на _aembed/_aembed_many
  - Сигнатуры аналогичны UserBaseVectorizer
  - _aembed: str(content or text), потом POST /encode/dense
  - _aembed_many: [str(c) for c in (contents or texts or [])], потом POST /encode/dense

Task 3: Fix test guard (tests/unit/test_vectorizers.py)
  - Заменить except (ImportError, ModuleNotFoundError, ValueError) на except Exception as exc
  - Добавить # pragma: no cover - environment dependent
  - Использовать f-string в skip message: f"redisvl unavailable/broken import: {type(exc).__name__}: {exc}"

Task 4: Update unit tests (tests/unit/test_vectorizers.py)
  - Тесты сейчас мокают _async_client и _sync_client напрямую — это правильно
  - Но вызовы через public API (vectorizer.embed("тест")) уже не будут напрямую вызывать наш _sync_client
  - Base class маршрутизирует: embed(content) -> _embed(content=content)
  - СТРАТЕГИЯ: тестируй _embed/_aembed напрямую (unit test internal methods)
  - test_embed_sync_wrapper -> test_embed_internal: vectorizer._embed("тест") вместо vectorizer.embed("тест")
  - test_embed_many_sync_wrapper -> test_embed_many_internal: vectorizer._embed_many(texts=["т1","т2"])
  - test_aembed_single_text -> вызывай vectorizer._aembed("тестовый запрос")
  - test_aembed_many -> вызывай vectorizer._aembed_many(texts=texts)

Task 5: Add compatibility tests (tests/unit/test_vectorizers.py)
  Добавь новый класс TestVectorizerCompatibility:
  - test_user_embed_content_kwarg: UserBaseVectorizer._embed(content="тест") не падает TypeError
  - test_user_embed_text_kwarg: UserBaseVectorizer._embed(text="тест") работает
  - test_user_aembed_content_kwarg: await UserBaseVectorizer._aembed(content="тест") работает
  - test_bge_embed_raises_not_implemented: BgeM3CacheVectorizer._embed(content="тест") -> NotImplementedError
  - test_bge_aembed_content_kwarg: await BgeM3CacheVectorizer._aembed(content="тест") работает
  В каждом тесте мокай _sync_client/_async_client как в существующих тестах.
  Добавь import BgeM3CacheVectorizer если его нет.

Task 6: Run checks and tests
  - uv run ruff check telegram_bot/services/vectorizers.py tests/unit/test_vectorizers.py --fix
  - uv run ruff format telegram_bot/services/vectorizers.py tests/unit/test_vectorizers.py
  - uv run mypy telegram_bot/services/vectorizers.py --ignore-missing-imports
  - uv run pytest tests/unit/test_vectorizers.py -v

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName="redisvl", query="BaseVectorizer _embed internal methods") затем query-docs для актуальной документации
- Exa: get_code_context_exa(query="redisvl BaseVectorizer _embed override") для примеров

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО:
  uv run pytest tests/unit/test_vectorizers.py -v
- НЕ запускай tests/ целиком
- Маппинг source -> test:
  telegram_bot/services/vectorizers.py -> tests/unit/test_vectorizers.py
- Используй --lf для перезапуска только упавших

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы: telegram_bot/services/vectorizers.py tests/unit/test_vectorizers.py
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите
3. Один коммит на всю миграцию: fix(vectorizers): migrate to redisvl 0.14.0 internal API #155
4. Прочитай BaseVectorizer source ПЕРЕД реализацией: .venv/lib/python3.12/site-packages/redisvl/utils/vectorize/base.py

ЛОГИРОВАНИЕ в /repo/logs/worker-vectorizer.log (APPEND):
[START] timestamp Task N: description
[DONE] timestamp Task N: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:W-VERIFY" "W-VECTORIZER COMPLETE — проверь logs/worker-vectorizer.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:W-VERIFY" Enter
ВАЖНО: Используй ИМЯ окна W-VERIFY, НЕ индекс.
