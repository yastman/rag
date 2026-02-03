# Design: Автозагрузка .env для ingestion pipeline

**Date:** 2026-02-03
**Status:** Draft
**Author:** Claude

## Problem Statement

Ingestion pipeline (`uv run python -m src.ingestion.gdrive_flow --once`) падает с ошибкой "Нужен VOYAGE_API_KEY" при запуске из cron, systemd или clean shell, потому что переменные из `.env` не загружаются автоматически.

## Current State

| Модуль | load_dotenv() | Проблема |
|--------|---------------|----------|
| `src/config/settings.py` | В `Settings.__init__()` | GDriveFlow не использует Settings |
| `telegram_bot/config.py` | На уровне модуля | Отдельный модуль |
| `src/ingestion/gdrive_flow.py` | **Нет** | Читает `os.getenv()` напрямую |

## Requirements

1. Не требовать `source .env` или `export` в shell
2. Работать одинаково: локально, cron, systemd, docker
3. Минимальные изменения (1-2 файла)
4. Unit-тест для проверки загрузки

## Solution

### Approach: load_dotenv() в entrypoint

Добавить `load_dotenv()` в начало `main()` функции в `src/ingestion/gdrive_flow.py`.

**Почему это место:**
- Минимальный diff (2 строки)
- Загружает `.env` до создания `GDriveFlowConfig()`
- Не влияет на импорты в тестах
- Паттерн уже используется в `telegram_bot/config.py`

**Альтернативы отклонены:**
- На уровне модуля — загружает при любом импорте, влияет на тесты
- Использовать Settings — требует рефакторинг GDriveFlowConfig

### Implementation

#### File: `src/ingestion/gdrive_flow.py`

```python
def main():
    """CLI entry point."""
    from dotenv import load_dotenv
    load_dotenv()  # Load .env before config initialization

    import argparse
    # ... rest unchanged
```

#### File: `tests/unit/ingestion/test_gdrive_flow_dotenv.py` (new)

```python
"""Test .env loading in gdrive_flow."""

from pathlib import Path


class TestDotenvLoading:
    """Test that .env is loaded before config initialization."""

    def test_voyage_api_key_loaded_from_dotenv(self, tmp_path: Path, monkeypatch):
        """Config should see VOYAGE_API_KEY from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("VOYAGE_API_KEY=test-key-from-dotenv\n")

        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)

        from src.ingestion.gdrive_flow import GDriveFlowConfig
        config = GDriveFlowConfig()

        assert config.voyage_api_key == "test-key-from-dotenv"

    def test_explicit_env_var_precedence(self, tmp_path: Path, monkeypatch):
        """Explicit env var should override .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("VOYAGE_API_KEY=from-dotenv\n")

        monkeypatch.setenv("VOYAGE_API_KEY", "from-explicit-env")

        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)

        from src.ingestion.gdrive_flow import GDriveFlowConfig
        config = GDriveFlowConfig()

        assert config.voyage_api_key == "from-explicit-env"
```

## Verification

```bash
# Unit tests
uv run pytest tests/unit/ingestion/test_gdrive_flow_dotenv.py -v
uv run pytest tests/unit/ingestion/test_gdrive_flow.py -v

# Integration (clean shell, no export)
uv run python -m src.ingestion.gdrive_flow --once --sync-dir ~/drive-sync

# Full test suite
make test-unit
```

## Files Changed

| File | Change |
|------|--------|
| `src/ingestion/gdrive_flow.py` | Add 2 lines in `main()` |
| `tests/unit/ingestion/test_gdrive_flow_dotenv.py` | New file, ~30 lines |

## Risks

| Risk | Mitigation |
|------|------------|
| python-dotenv not installed | Already a dependency (used in settings.py, telegram_bot/config.py) |
| Breaks existing tests | load_dotenv() only in main(), not at import time |
| Docker behavior changes | No change — docker-compose passes env vars directly |

## Out of Scope

- Refactoring GDriveFlowConfig to use Settings class
- Adding .env validation/schema
- Other ingestion entrypoints (cocoindex_flow.py uses Settings already)
