# Design: Full CI Green Sweep (#191)

**Issue:** [#191](https://github.com/yastman/rag/issues/191)
**Branch:** `fix/191-ci-green-sweep`
**Related:** #181 (mypy), #183 (redisvl gate), #186 (pipeline test env), #187 (extract_ground_truth), #188 (search_engines)

## Текущее состояние CI (verified 2026-02-12)

**Lint job (mypy) — 3 ошибки, блокирует unit tests:**

| Файл | Строка | Ошибка | Причина |
|-------|--------|--------|---------|
| `src/voice/sip_setup.py` | 38 | `no-any-return` | `result.sip_trunk_id` от LiveKit SDK untyped |
| `telegram_bot/graph/graph.py` | 150 | `no-any-return` | `summarize_wrapper` возвращает `result` типа `Any` |
| `telegram_bot/graph/graph.py` | 152 | `type-var` | `add_node("summarize", summarize_wrapper)` — LangGraph `NodeInputT` не принимает `dict[str, Any]` |

**Unit tests — 1 failure (когда lint пройден):**

| Тест | Ошибка | Issue |
|------|--------|-------|
| `test_pipeline.py::test_pipeline_init_default_settings` | `Settings()._validate_api_keys()` → `ValueError: ANTHROPIC_API_KEY not set` | #186 |
| `test_vectorizers.py` | SKIPPED (redisvl not installed) — корректно в CI | #183 |

**251 passed, 2 skipped, 1 failed** в последнем CI run.

## Scope: 5 фиксов

### Fix 1: mypy `sip_setup.py` — `no-any-return` (#181)

**Проблема:** LiveKit SDK `CreateSIPOutboundTrunkResponse.sip_trunk_id` не аннотирован.

**Решение:** `cast(str, result.sip_trunk_id)` — стандартный mypy-паттерн для untyped SDK returns ([mypy docs: no-any-return](https://mypy.readthedocs.io/en/stable/error_code_list2.html)).

```python
# src/voice/sip_setup.py:34-38
from typing import cast

trunk_id: str = cast(str, result.sip_trunk_id)
return trunk_id
```

**Риск:** Нулевой. `cast()` — compile-time hint, не меняет runtime.

### Fix 2: mypy `graph.py` — `no-any-return` + `type-var` (#181)

**Проблема:**
- Строка 150: `summarize_wrapper` возвращает `result` (тип `Any` от `ainvoke`)
- Строка 152: `workflow.add_node("summarize", summarize_wrapper)` — LangGraph `StateGraph.add_node` ожидает callable с аннотированным input type, но `summarize_wrapper` принимает `dict[str, Any]`

**Решение:** Комбинация `cast` + `type: ignore` для LangGraph type-var issue (известная проблема LangGraph, см. [langchain-ai/langgraph#1028](https://github.com/langchain-ai/langgraph/issues/1028)):

```python
# telegram_bot/graph/graph.py:149-152
from typing import cast

return cast(dict[str, Any], result)
...
workflow.add_node("summarize", summarize_wrapper)  # type: ignore[type-var]
```

**Обоснование `type: ignore`:** LangGraph's `add_node` type annotations не поддерживают `dict[str, Any]` callable signatures — это upstream issue. `# type: ignore[type-var]` с комментарием — принятая практика для known SDK limitations.

**Риск:** Нулевой. Runtime поведение не меняется.

### Fix 3: redisvl import gate (#183)

**Проблема:** `tests/unit/test_vectorizers.py` проверяет `import redisvl` перед импортом `vectorizers.py`. Но `test_redis_semantic_cache.py` инжектит `MagicMock()` для `redisvl` в `sys.modules`. При запуске полного suite, mock остаётся → `import redisvl` проходит → `from redisvl.utils.vectorize import BaseVectorizer` падает.

**В CI:** redisvl не установлен → тест корректно скипается. Проблема только при локальном запуске полного suite.

**Решение:** Заменить guard на проверку конкретного sub-import:

```python
# tests/unit/test_vectorizers.py:6-9
try:
    from redisvl.utils.vectorize import BaseVectorizer  # noqa: F401
except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
    pytest.skip("redisvl.utils.vectorize not available", allow_module_level=True)
```

**Best practice** (из [pytest monkeypatch docs](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)): guard должен проверять точный символ, используемый в production коде, а не top-level package.

**Дополнительно:** Добавить `AttributeError` в except — MagicMock может бросать его при доступе к несуществующим атрибутам.

**Риск:** Минимальный. Тест продолжает скипаться когда redisvl недоступен, но теперь корректно обрабатывает mock contamination.

### Fix 4: RAGPipeline test env-independence (#186)

**Проблема:** `test_pipeline_init_default_settings` вызывает `RAGPipeline()` без аргументов → `Settings()` → `_validate_api_keys()` → `ValueError` если `ANTHROPIC_API_KEY` не задан.

Тест патчит 6 downstream зависимостей (parser, chunker, indexer...), но НЕ патчит `Settings()` itself.

**Решение:** `monkeypatch.setenv` для API key перед вызовом:

```python
@patch("src.core.pipeline.get_sentence_transformer")
@patch("src.core.pipeline.create_search_engine")
@patch("src.core.pipeline.ClaudeContextualizer")
@patch("src.core.pipeline.DocumentIndexer")
@patch("src.core.pipeline.DocumentChunker")
@patch("src.core.pipeline.UniversalDocumentParser")
def test_pipeline_init_default_settings(self, mock_parser, ...):
    mock_transformer.return_value = MagicMock()
    mock_search_engine.return_value = MagicMock()

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-for-ci"}):
        pipeline = RAGPipeline()

    mock_transformer.assert_called_once()
    assert pipeline.settings is not None
```

**Альтернатива:** Передать `Settings(api_provider=APIProvider.OPENAI, openai_api_key="test")` напрямую. Но это меняет intent теста — тест проверяет default constructor path.

**Best practice** ([pydantic-settings](https://docs.pydantic.dev/2.5/concepts/pydantic_settings/), [functools.lru_cache pattern](https://www.davidmuraya.com/blog/centralizing-fastapi-configuration-with-pydantic-settings-and-env-files/)): env-based config testing через `monkeypatch.setenv` или `patch.dict(os.environ)` — стандартный подход.

**Риск:** Минимальный. Тест сохраняет оригинальный intent, добавляет env isolation.

### Fix 5: Evaluation import-time Settings() (#187, #188)

**Проблема:** `src/evaluation/extract_ground_truth.py` и `search_engines.py` вызывают `Settings()` на уровне модуля (строка 19-20 обоих файлов). `Settings()` имеет defaults для `qdrant_url`/`qdrant_api_key`, но `_validate_api_keys()` может упасть если `API_PROVIDER=claude` (default) и `ANTHROPIC_API_KEY` не задан.

**Текущее поведение:** В CI Settings() проходит (default provider имеет default key handling). Но это fragile — любое изменение validation logic может сломать CI.

**Решение:** Lazy initialization через `functools.lru_cache`:

```python
# src/evaluation/extract_ground_truth.py
from functools import lru_cache

@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return Settings()

def _qdrant_url() -> str:
    return _get_settings().qdrant_url

def _qdrant_api_key() -> str:
    return _get_settings().qdrant_api_key or ""
```

Все функции заменяют `QDRANT_URL` → `_qdrant_url()`, `QDRANT_API_KEY` → `_qdrant_api_key()`.

**Паттерн** (из [PEP 810](https://peps.python.org/pep-0810/) и [pydantic lazy facade](https://zalt.me/blog/2025/10/inside-pydantics-lazy-facade)): defer initialization until first use. `lru_cache` гарантирует singleton — Settings создаётся один раз при первом вызове.

Аналогичный фикс для `search_engines.py`. Constants из `HSNWParameters`, `RetrievalStages`, `ThresholdValues` — оставить module-level (они не зависят от env, это просто enums).

Также удалить legacy `sys.path.append("/home/admin/contextual_rag")` из обоих файлов — VPS artifact, не нужен в текущей структуре.

**Риск:** Низкий. `lru_cache` — стандартный Python паттерн. Поведение идентично, initialization отложена.

## Порядок выполнения

```
Fix 1 (sip_setup.py)        ← 1 строка, cast
Fix 2 (graph.py)             ← 2 строки, cast + type: ignore
Fix 3 (test_vectorizers.py)  ← 1 строка, точный import guard
Fix 4 (test_pipeline.py)     ← 3 строки, patch.dict env
Fix 5a (extract_ground_truth)← ~15 строк, lazy Settings
Fix 5b (search_engines)      ← ~15 строк, lazy Settings
```

Фиксы 1-4 — минимальные правки (< 5 строк каждый), независимые.
Фикс 5 — рефакторинг evaluation модулей, но isolated scope.

## Верификация

```bash
# mypy
uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary

# Unit tests (full suite, sequential)
uv run pytest tests/unit/ -q -x -m "not legacy_api" --timeout=30

# Targeted checks
uv run pytest tests/unit/core/test_pipeline.py -q
uv run pytest tests/unit/test_vectorizers.py -q
uv run pytest tests/unit/evaluation/ -q

# Simulate CI env (no API keys)
env -i HOME=$HOME PATH=$PATH uv run pytest tests/unit/ -q -x -m "not legacy_api" --timeout=30
```

## Closes

- #181 (mypy unblock) — fixes 1, 2
- #183 (redisvl gate) — fix 3
- #186 (pipeline test env) — fix 4
- #187 (extract_ground_truth) — fix 5a
- #188 (search_engines) — fix 5b
- #191 (umbrella) — all fixes
