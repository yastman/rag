# Audit Remediation: CI + Smoke Tests — Implementation Plan

**Goal:** Fix CI dependency installation gap and modernize smoke tests to use current CacheLayerManager API.
**Issue:** [#91](https://github.com/yastman/rag/issues/91) — fix: complete Issue #90 audit remediation (CI + smoke tests)
**Milestone:** Deferred: Post-Baseline

---

## Текущее состояние

### CI: двойная группа dev-зависимостей

В `pyproject.toml` ОДНОВРЕМЕННО существуют ДВЕ dev-группы с разным содержимым:

| Механизм | Секция | Содержимое |
|----------|--------|-----------|
| `--extra dev` | `[project.optional-dependencies].dev` (строки 52-64) | ruff, mypy, pylint, bandit, pytest, pytest-cov, pytest-asyncio, pytest-httpx, pre-commit |
| `--group dev` | `[dependency-groups].dev` (строки 392-399) | pre-commit, pytest-asyncio, pytest-httpx, pytest-timeout, pytest-xdist, telethon |

Текущее использование в CI (`ci.yml`):

| Job | Строка | Команда | Проблема |
|-----|--------|---------|----------|
| `lint` | 26 | `uv sync --frozen --extra dev` | OK — получает ruff, mypy |
| `test` | 53 | `uv sync --frozen --group dev` | НЕТ pytest напрямую (только транзитивно), нет pytest-cov |
| `baseline-compare` | 85 | `uv sync --group dev` | Та же проблема + нет --frozen |

**Ключевая проблема:** `pytest-timeout` (нужен для `--timeout=30` в CI) есть ТОЛЬКО в `[dependency-groups].dev`, а `pytest` и `pytest-cov` — ТОЛЬКО в `[project.optional-dependencies].dev`. Ни одна команда установки не покрывает всё.

### Smoke tests: уже мигрированы, но помечены legacy

`tests/smoke/test_zoo_smoke.py` содержит 3 test-класса:

| Класс | Маркер | API | Статус |
|-------|--------|-----|--------|
| `TestZooHealth` (строка 20) | нет | httpx (LiteLLM, user-base) | OK |
| `TestBgeM3` (строка 93) | нет | httpx (BGE-M3) | OK |
| `TestZooCache` (строка 136) | `@pytest.mark.legacy_api` | `CacheLayerManager.store_sparse_embedding`, `get_sparse_embedding` | API корректный, маркер лишний |
| `TestZooEndToEnd` (строка 167) | `@pytest.mark.legacy_api` | `CacheLayerManager.get_metrics()`, `get_exact()`, `store_exact()`, `make_hash()` | API корректный, маркер лишний |

Все вызовы в `TestZooCache` и `TestZooEndToEnd` используют СУЩЕСТВУЮЩИЕ методы `CacheLayerManager` (файл `telegram_bot/integrations/cache.py`):
- `store_sparse_embedding` (строка 346)
- `get_sparse_embedding` (строка 340)
- `get_metrics()` (строка 441)
- `get_exact()` (строка 278)
- `store_exact()` (строка 305)
- `make_hash()` (строка 462)

Нет вызовов несуществующих методов (`get_cached_sparse_embedding`, `store_analysis`, `.metrics`).
Маркер `legacy_api` неверно исключает эти тесты из CI run (`-m "not legacy_api"`).

---

## Шаги реализации

### Шаг 1: Консолидировать dev-зависимости в pyproject.toml (2 мин)

**Файл:** `pyproject.toml`

**Действие:** Объединить содержимое `[dependency-groups].dev` в `[project.optional-dependencies].dev`, удалить дубли.

Текущий `[project.optional-dependencies].dev` (строки 52-64) — добавить недостающие:
- `pytest-timeout>=2.4.0` (сейчас ТОЛЬКО в dependency-groups)
- `pytest-xdist>=3.8.0` (сейчас ТОЛЬКО в dependency-groups)
- Обновить `pytest-asyncio>=0.24.0` → `>=1.2.0` (выше минимум из dependency-groups)
- `telethon>=1.42.0` (E2E тесты, ТОЛЬКО в dependency-groups)

Текущий `[dependency-groups].dev` (строки 391-399) — изменить на ссылку:

    [dependency-groups]
    dev = [{include-group = "optional:dev"}]

Или просто: удалить `[dependency-groups].dev` целиком — CI будет использовать `--extra dev`.

**Предпочтительный вариант:** удалить `[dependency-groups].dev` (строки 391-399), перенести уникальные пакеты в `[project.optional-dependencies].dev`.

### Шаг 2: Унифицировать CI dependency installation (2 мин)

**Файл:** `.github/workflows/ci.yml`

**Действие 1:** Строка 53, job `test`:

    Было:  uv sync --frozen --group dev
    Стало: uv sync --frozen --extra dev

**Действие 2:** Строка 85, job `baseline-compare`:

    Было:  uv sync --group dev
    Стало: uv sync --frozen --extra dev

Добавить `--frozen` для consistency (baseline-compare на строке 85 не имеет `--frozen`).

### Шаг 3: Снять маркер legacy_api со smoke-тестов кеша (2 мин)

**Файл:** `tests/smoke/test_zoo_smoke.py`

**Действие 1:** Строка 135-136 — удалить маркер:

    Было:
    @pytest.mark.legacy_api
    class TestZooCache:

    Стало:
    class TestZooCache:

**Действие 2:** Строка 166-167 — удалить маркер:

    Было:
    @pytest.mark.legacy_api
    class TestZooEndToEnd:

    Стало:
    class TestZooEndToEnd:

**Действие 3:** Строка 142 — убрать алиас `as CacheService`, использовать `CacheLayerManager` напрямую:

    Было:  from telegram_bot.integrations.cache import CacheLayerManager as CacheService
    Стало: from telegram_bot.integrations.cache import CacheLayerManager

Аналогично строка 173. Обновить fixture yield variable name: `service` → `cache` (или оставить service, непринципиально).

**Действие 4:** Добавить маркер `@pytest.mark.smoke` к обоим классам (тесты требуют живой Redis):

    @pytest.mark.smoke
    class TestZooCache:

    @pytest.mark.smoke
    class TestZooEndToEnd:

### Шаг 4: Верификация (3 мин)

**Команда 1:** Collect-only для smoke tests:

    uv run pytest tests/smoke/test_zoo_smoke.py --collect-only -q

Ожидание: все тесты собираются без ошибок импорта.

**Команда 2:** Unit tests без legacy_api:

    uv run pytest tests/unit/ -q -x -m "not legacy_api" --timeout=30 2>&1 | tail -20

Ожидание: проходят без import errors.

**Команда 3:** Mypy статус:

    uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary 2>&1 | tail -5

Документировать результат (pass/fail + blockers) в issue #91 комментарием.

---

## Test Strategy

| Что проверяем | Команда | Ожидание |
|---------------|---------|----------|
| Smoke tests собираются | `pytest --collect-only tests/smoke/test_zoo_smoke.py` | 0 errors, 8+ tests collected |
| Unit tests проходят | `pytest tests/unit/ -q -x -m "not legacy_api" --timeout=30` | pass, no import errors |
| Mypy | `mypy src/ telegram_bot/ --ignore-missing-imports` | документировать статус |
| CI lint deps | `uv sync --frozen --extra dev && uv run ruff --version && uv run mypy --version` | обе утилиты доступны |

## Acceptance Criteria

- [ ] `[dependency-groups].dev` удалена или ссылается на `[project.optional-dependencies].dev`
- [ ] CI lint/test/baseline-compare единообразно используют `uv sync --frozen --extra dev`
- [ ] `TestZooCache` и `TestZooEndToEnd` не имеют маркера `legacy_api`
- [ ] `pytest --collect-only` проходит для smoke tests
- [ ] Unit tests проходят без import errors
- [ ] Mypy статус задокументирован

## Effort Estimate

~10 минут: 4 файла, ~15 строк правок + верификация.

## Риски

| Риск | Митигация |
|------|-----------|
| `--frozen` fail если uv.lock расходится | `uv lock` перед коммитом |
| Smoke cache-тесты падают без Redis | Маркер `@pytest.mark.smoke` + CI не запускает smoke |
| Удаление dependency-groups ломает что-то | Проверить нет ли других ссылок на `--group dev` в скриптах |
