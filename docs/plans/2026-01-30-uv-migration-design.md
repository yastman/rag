# UV Migration Design

**Дата:** 2026-01-30
**Статус:** Approved
**Автор:** Claude + User brainstorming session

---

## 1. Executive Summary

Миграция dependency management с pip/requirements.txt на **uv + PEP 735 dependency groups**.

**Ключевые решения:**
- Один источник истины: `pyproject.toml` + `uv.lock`
- Режим: **no-install-project** (deps only, запуск через `uv run`)
- ML-сервисы: отдельные `pyproject.toml` + `uv.lock` (multi-lock)
- Python version: `>=3.11`

---

## 2. Scope

### В scope

| Компонент | Изменения |
|-----------|-----------|
| `/pyproject.toml` | Добавить `[dependency-groups]`, поднять requires-python до >=3.11 |
| `/uv.lock` | Создать (новый файл) |
| `/Makefile` | Заменить pip команды на uv |
| `/telegram_bot/Dockerfile` | Переписать на uv |
| `/services/bge-m3-api/` | Создать pyproject.toml + uv.lock, переписать Dockerfile |
| `/.github/workflows/ci.yml` | Вернуть из disabled, адаптировать под uv |
| `/CLAUDE.md` | Обновить правила работы с зависимостями |

### Вне scope

- `services/bm42/`, `services/user-base/` — оставить как есть (inline pip в Dockerfile)
- Публикация пакета на PyPI
- Multi-stage Docker builds

---

## 3. Архитектура зависимостей

### 3.1 Структура после миграции

```
rag-fresh/
├── pyproject.toml          # Единственный источник истины
├── uv.lock                  # Universal lockfile (коммитится в git)
│
├── services/
│   └── bge-m3-api/
│       ├── pyproject.toml  # Отдельный проект
│       └── uv.lock         # Отдельный lock
│
├── requirements.txt        # УДАЛИТЬ или legacy export
├── telegram_bot/
│   └── requirements.txt    # УДАЛИТЬ
└── requirements-e2e.txt    # УДАЛИТЬ
```

### 3.2 Dependency Groups (PEP 735)

```toml
# pyproject.toml

[project]
name = "contextual-rag"
version = "2.13.0"
requires-python = ">=3.11"  # Поднято с >=3.9
dependencies = [
    # Runtime deps (текущий [project].dependencies)
]

[project.optional-dependencies]
# ОСТАЮТСЯ для совместимости с pip install .[dev]
dev = ["ruff>=0.6.0", "pytest>=8.3.0", ...]

[dependency-groups]
# НОВОЕ: для uv sync --group
dev = [
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "pytest>=8.3.0",
    "pytest-cov>=5.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-httpx>=0.35.0",
    "pre-commit>=3.8.0",
    "bandit>=1.7.9",
]
docs = [
    "mkdocs>=1.6.0",
    "mkdocs-material>=9.5.0",
    "mkdocstrings[python]>=0.25.0",
]
bot = [
    "aiogram>=3.15.0",
    "httpx>=0.28.0",
    "redis>=5.0.0",
    "redisvl>=0.3.0",
    "cachetools>=5.3.0",
]
e2e = [
    "telethon>=1.36.0",
]
```

### 3.3 Политика extras vs groups

| Тип | Использование | Когда удалить |
|-----|---------------|---------------|
| `[project.optional-dependencies]` (extras) | `pip install .[dev]` — legacy/совместимость | Когда полностью стандартизировали uv везде |
| `[dependency-groups]` (PEP 735) | `uv sync --group dev` — основной workflow | Никогда |

---

## 4. Режим работы: no-install-project

### Выбор

**Режим B: no-install-project** — проект НЕ устанавливается как пакет.

### Обоснование

- Проект — app/сервис, не библиотека для PyPI
- Убирает зависимость от корректного `[build-system]`
- Упрощает Docker сборку
- `uv run` автоматически добавляет текущую директорию в PYTHONPATH

### Команды

```bash
# Локальная разработка
uv sync --group dev --group bot --no-install-project

# Docker
uv sync --frozen --group bot --no-install-project

# Запуск
uv run python -m telegram_bot.main
uv run pytest tests/unit -v
```

### PYTHONPATH

В `pyproject.toml` уже есть:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

Для других инструментов `uv run` автоматически добавляет project root.

---

## 5. Makefile

```makefile
# =============================================================================
# DEPENDENCY MANAGEMENT (uv)
# =============================================================================

.PHONY: install install-dev install-all lock sync sync-frozen \
        upgrade upgrade-package clean-venv export-requirements-legacy \
        print-deps doctor

# --- Установка ---
install:
	uv sync --no-install-project

install-dev:
	uv sync --group dev --group bot --no-install-project

install-all:
	uv sync --all-groups --no-install-project

# --- Lock & Sync ---
lock: pyproject.toml
	uv lock

sync:
	uv sync --no-install-project

sync-frozen:
	uv sync --frozen --no-install-project

# --- Обновление зависимостей ---
upgrade:
	uv lock --upgrade

upgrade-package:
	uv lock --upgrade-package $(PKG)

# --- Утилиты ---
clean-venv:
	rm -rf .venv
	uv sync --group dev --group bot --no-install-project

export-requirements-legacy:
	uv export --format requirements.txt --no-hashes -o requirements.txt

print-deps:
	uv tree

doctor:
	@echo "=== uv version ==="
	@uv --version
	@echo "=== Python version ==="
	@uv run python --version
	@echo "=== Lock status ==="
	@uv lock --check && echo "Lock is up-to-date" || echo "Lock is outdated, run: make lock"
```

### Правила

1. **Изменение зависимостей:** редактируем `pyproject.toml`, затем `make lock`
2. **Локальная разработка:** `make install-dev`
3. **CI/VPS/Docker:** `make sync-frozen`
4. **Никогда:** `pip install <package>` напрямую в окружение

---

## 6. Docker

### 6.1 Bot (telegram_bot/Dockerfile)

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Установка uv (пинить версию!)
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv

# Кэширование: сначала только файлы зависимостей
COPY pyproject.toml uv.lock ./

# Синхронизация runtime + bot группы (без установки проекта)
RUN uv sync --frozen --group bot --no-install-project

# Копируем код
COPY telegram_bot/ ./telegram_bot/
COPY src/ ./src/

ENV PYTHONUNBUFFERED=1

# Healthcheck (опционально)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD uv run python -c "print('ok')"

CMD ["uv", "run", "python", "-m", "telegram_bot.main"]
```

### 6.2 BGE-M3 API (services/bge-m3-api/Dockerfile)

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Установка uv (пинить версию!)
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv

# Кэширование зависимостей
COPY pyproject.toml uv.lock ./

# Синхронизация (frozen = использовать lock как есть)
RUN uv sync --frozen --no-install-project

# Копируем код
COPY app.py config.py ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"

CMD ["uv", "run", "python", "app.py"]
```

### 6.3 Принципы Docker

| Принцип | Реализация |
|---------|------------|
| Версия uv пинится | `ghcr.io/astral-sh/uv:0.5.14` |
| Кэширование слоёв | COPY pyproject.toml + uv.lock перед кодом |
| Воспроизводимость | `--frozen` — падает если lock устарел |
| Без установки проекта | `--no-install-project` |
| Без pip | Только uv |

---

## 7. CI (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.5.14"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --frozen --group dev --no-install-project

      - name: Lint
        run: uv run ruff check src telegram_bot

      - name: Format check
        run: uv run ruff format --check src telegram_bot

      - name: Type check
        run: uv run mypy src telegram_bot --ignore-missing-imports

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.5.14"

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --frozen --group dev --group bot --no-install-project

      - name: Run tests
        run: uv run pytest tests/unit -v

  lock-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.5.14"

      - name: Check lock is up-to-date
        run: uv lock --check
```

### Принципы CI

- Версия uv пинится: `0.5.14`
- Lock проверяется: `uv lock --check` падает если устарел
- Установка строгая: `--frozen`
- Matrix: Python 3.11 и 3.12

---

## 8. Порядок миграции

### Этап 1: BGE-M3 API (изолированно)

1. Создать `services/bge-m3-api/pyproject.toml`
2. Сгенерировать `services/bge-m3-api/uv.lock`
3. Обновить `services/bge-m3-api/Dockerfile`
4. Протестировать: `docker compose build bge-m3 && docker compose up bge-m3`

**DoD:** сервис стартует, healthcheck зелёный.

### Этап 2: Root проект

1. Добавить `[dependency-groups]` в pyproject.toml
2. Поднять `requires-python` до `>=3.11`
3. Сгенерировать `uv.lock`
4. Обновить Makefile
5. Протестировать: `make clean-venv && make install-dev && make test`

**DoD:** все unit-тесты проходят, `make doctor` зелёный.

### Этап 3: Docker bot

1. Обновить `telegram_bot/Dockerfile`
2. Протестировать: `docker compose build bot && docker compose up bot`

**DoD:** бот стартует, healthcheck зелёный.

### Этап 4: CI

1. Переместить workflow из `.github/workflows.disabled/` в `.github/workflows/`
2. Адаптировать под uv
3. Создать PR, проверить что CI зелёный

**DoD:** CI проходит на PR.

### Этап 5: Cleanup

1. Пометить как legacy: `requirements.txt`, `telegram_bot/requirements.txt`, `requirements-e2e.txt`
2. Обновить CLAUDE.md
3. Обновить docs/LOCAL-DEVELOPMENT.md

**DoD:** документация актуальна, команда знает новый workflow.

---

## 9. Definition of Done (общий)

- [ ] `uv sync --frozen --no-install-project` в чистом окружении устанавливает все зависимости
- [ ] `make test` проходит (unit tests)
- [ ] `docker compose up -d` поднимает стек, healthcheck зелёный у bot, bge-m3, qdrant, redis
- [ ] CI workflow проходит на PR
- [ ] `uv lock --check` проходит (lock актуален)
- [ ] CLAUDE.md обновлён с новыми правилами

---

## 10. Правила на будущее (добавить в CLAUDE.md)

```markdown
## Dependency Management (uv + PEP 735)

**Режим:** no-install-project (deps only, запуск через `uv run`)

**Правила:**
1. Зависимости только в `pyproject.toml` — никогда не редактировать requirements*.txt вручную
2. `uv.lock` обязателен в каждом PR — `uv lock --check` проверяется в CI
3. Docker/CI используют `--frozen` — гарантия воспроизводимости
4. Никогда `pip install <package>` напрямую — только через pyproject.toml + uv lock

**Команды разработки:**
- `make install-dev` — установить runtime + dev + bot
- `make lock` — обновить lock после изменения pyproject.toml
- `make upgrade-package PKG=httpx` — обновить конкретный пакет
- `make doctor` — проверка окружения

**Структура:**
- Root: `/pyproject.toml` + `/uv.lock`
- ML-сервисы: `services/*/pyproject.toml` + `services/*/uv.lock` (независимые)
```

---

## 11. Риски и митигация

| Риск | Митигация |
|------|-----------|
| uv breaking changes | Пинить версию uv везде (Dockerfile, CI, Makefile) |
| Lock конфликты в PR | `uv lock --check` в CI, rebase перед merge |
| Dependabot не поддерживает groups | Экспортировать requirements.txt для Dependabot (legacy) |
| VPS без uv | Устанавливать uv через `curl -LsSf https://astral.sh/uv/install.sh | sh` |
