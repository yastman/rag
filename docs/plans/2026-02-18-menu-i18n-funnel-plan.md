# Menu + i18n + Funnel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Добавить в существующий PropertyBot интерактивное меню (aiogram-dialog), мультиязычность (fluentogram), и продающую воронку (BANT) — максимально используя SDK, минимум кастомного кода.

**Architecture:** aiogram-dialog управляет всей навигацией (меню, воронка, настройки) через StatesGroup/Window/Dialog. fluentogram загружает переводы из .ftl файлов с fallback-цепочкой. User preferences хранятся в PostgreSQL (новая БД `realestate`), горячий кэш в Redis. Существующий RAG pipeline и supervisor — без изменений.

**Tech Stack:** aiogram-dialog 2.x, fluentogram 1.2, asyncpg (уже в root deps), PostgreSQL (существующий контейнер), Redis (существующий)

**Design doc:** `docs/plans/2026-02-18-menu-i18n-funnel-design.md`

---

## Phase 1: Foundation — Dependencies + Storage + i18n + Menu

### Task 1: Добавить зависимости

**Files:**
- Modify: `pyproject.toml:6-34` (root deps)
- Modify: `telegram_bot/pyproject.toml:6-25` (Docker deps)

**Step 1: Добавить aiogram-dialog и fluentogram в root pyproject.toml**

В секцию `[project.dependencies]` после строки `"aiogram>=3.25.0",` добавить:

```python
    "aiogram-dialog>=2.4.0",            # Dialog framework (menus, navigation, widgets)
    "fluentogram>=1.2.0",               # i18n (Fluent .ftl files, stub generator)
```

**Step 2: Добавить в telegram_bot/pyproject.toml**

В секцию `dependencies` после строки `"aiogram>=3.15.0",` добавить:

```python
    "aiogram-dialog>=2.4.0",
    "fluentogram>=1.2.0",
    "asyncpg>=0.31.0",
```

**Step 3: Синхронизировать lock-файлы**

Run: `cd /home/user/projects/rag-fresh && uv lock`
Run: `cd /home/user/projects/rag-fresh/telegram_bot && uv lock`
Expected: lock-файлы обновлены без конфликтов

**Step 4: Проверить установку**

Run: `cd /home/user/projects/rag-fresh && uv sync`
Run: `uv run python -c "import aiogram_dialog; import fluentogram; print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock telegram_bot/pyproject.toml telegram_bot/uv.lock
git commit -m "feat(deps): add aiogram-dialog and fluentogram for menu+i18n"
```

---

### Task 2: PostgreSQL schema для realestate

**Files:**
- Modify: `docker/postgres/init/00-init-databases.sql`
- Create: `docker/postgres/init/05-realestate-schema.sql`

**Step 1: Добавить CREATE DATABASE realestate**

В файл `docker/postgres/init/00-init-databases.sql` после последней строки добавить:

```sql

-- Database for Real Estate CRM/Funnel
CREATE DATABASE realestate;
GRANT ALL PRIVILEGES ON DATABASE realestate TO postgres;
```

**Step 2: Создать schema file**

Создать `docker/postgres/init/05-realestate-schema.sql`:

```sql
-- Real Estate: users, leads, funnel events
-- Runs in default postgres DB (tables created there, not in realestate DB)
-- because init scripts run against default DB

\c realestate;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    locale VARCHAR(5) DEFAULT 'ru',
    role VARCHAR(20) DEFAULT 'client',
    first_name VARCHAR(100),
    telegram_language_code VARCHAR(10),
    notifications_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    stage VARCHAR(30) DEFAULT 'new',
    score INTEGER DEFAULT 0,
    preferences JSONB DEFAULT '{}',
    kommo_lead_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS funnel_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event_type VARCHAR(50) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_leads_user_id ON leads(user_id);
CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
CREATE INDEX IF NOT EXISTS idx_funnel_events_user_id ON funnel_events(user_id);
CREATE INDEX IF NOT EXISTS idx_funnel_events_created ON funnel_events(created_at DESC);
```

**Step 3: Commit**

```bash
git add docker/postgres/init/00-init-databases.sql docker/postgres/init/05-realestate-schema.sql
git commit -m "feat(db): add realestate database schema (users, leads, funnel_events)"
```

> **Примечание:** Если PostgreSQL volume уже существует, init-скрипты не перезапустятся автоматически. Нужно либо `docker compose down -v postgres` (потеряет данные!), либо выполнить SQL вручную через `docker exec`.

---

### Task 3: User dataclass model

**Files:**
- Create: `telegram_bot/models/__init__.py`
- Create: `telegram_bot/models/user.py`
- Create: `tests/unit/models/__init__.py`
- Create: `tests/unit/models/test_user_model.py`

**Step 1: Написать тест для User dataclass**

Создать `tests/unit/models/__init__.py` (пустой) и `tests/unit/models/test_user_model.py`:

```python
"""Tests for user model dataclasses."""

from telegram_bot.models.user import Lead, User


def test_user_defaults():
    user = User(telegram_id=123456)
    assert user.locale == "ru"
    assert user.role == "client"
    assert user.notifications_enabled is True
    assert user.id is None


def test_user_with_all_fields():
    user = User(
        id=1,
        telegram_id=123456,
        locale="uk",
        role="manager",
        first_name="Ярослав",
        telegram_language_code="uk",
        notifications_enabled=False,
    )
    assert user.role == "manager"
    assert user.first_name == "Ярослав"


def test_lead_defaults():
    lead = Lead(user_id=1)
    assert lead.stage == "new"
    assert lead.score == 0
    assert lead.preferences == {}


def test_lead_with_preferences():
    lead = Lead(
        user_id=1,
        stage="qualified",
        score=65,
        preferences={"type": "apartment", "area": "Sunny Beach", "budget": "80000"},
    )
    assert lead.score == 65
    assert lead.preferences["type"] == "apartment"
```

**Step 2: Запустить тест — должен упасть**

Run: `uv run pytest tests/unit/models/test_user_model.py -v`
Expected: FAIL (ImportError — модуль не существует)

**Step 3: Создать модель**

Создать `telegram_bot/models/__init__.py`:

```python
"""Data models for real estate bot."""
```

Создать `telegram_bot/models/user.py`:

```python
"""User and Lead data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class User:
    """Bot user (client or manager)."""

    telegram_id: int
    id: int | None = None
    locale: str = "ru"
    role: str = "client"  # client, manager, admin
    first_name: str | None = None
    telegram_language_code: str | None = None
    notifications_enabled: bool = True


@dataclass
class Lead:
    """Sales lead with qualification data."""

    user_id: int
    id: int | None = None
    stage: str = "new"  # new, qualified, hot, warm, cold, converted
    score: int = 0
    preferences: dict = field(default_factory=dict)
    kommo_lead_id: int | None = None
```

**Step 4: Запустить тест — должен пройти**

Run: `uv run pytest tests/unit/models/test_user_model.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add telegram_bot/models/ tests/unit/models/
git commit -m "feat(models): add User and Lead dataclasses"
```

---

### Task 4: UserService (asyncpg CRUD)

**Files:**
- Create: `telegram_bot/services/user_service.py`
- Create: `tests/unit/services/test_user_service.py`

**Step 1: Написать тест с мок-пулом**

Создать `tests/unit/services/test_user_service.py`:

```python
"""Tests for UserService (asyncpg CRUD)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.models.user import User
from telegram_bot.services.user_service import UserService


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    return pool


@pytest.fixture
def service(mock_pool):
    return UserService(pool=mock_pool)


@pytest.mark.asyncio
async def test_get_or_create_existing_user(service, mock_pool):
    """Existing user returned from DB."""
    row = {
        "id": 1,
        "telegram_id": 123,
        "locale": "uk",
        "role": "client",
        "first_name": "Test",
        "telegram_language_code": "uk",
        "notifications_enabled": True,
    }
    mock_pool.fetchrow.return_value = row

    user = await service.get_or_create(telegram_id=123, first_name="Test")
    assert user.telegram_id == 123
    assert user.locale == "uk"
    mock_pool.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_new_user(service, mock_pool):
    """New user created when not found."""
    # First call (SELECT) returns None, second call (INSERT) returns new row
    mock_pool.fetchrow.side_effect = [
        None,  # SELECT
        {
            "id": 2,
            "telegram_id": 456,
            "locale": "ru",
            "role": "client",
            "first_name": "New",
            "telegram_language_code": "ru",
            "notifications_enabled": True,
        },  # INSERT ... RETURNING
    ]

    user = await service.get_or_create(telegram_id=456, first_name="New", language_code="ru")
    assert user.telegram_id == 456
    assert user.locale == "ru"
    assert mock_pool.fetchrow.call_count == 2


@pytest.mark.asyncio
async def test_get_role(service, mock_pool):
    """Get user role by telegram_id."""
    mock_pool.fetchval.return_value = "manager"
    role = await service.get_role(telegram_id=123)
    assert role == "manager"


@pytest.mark.asyncio
async def test_get_role_unknown_user(service, mock_pool):
    """Unknown user returns 'client' as default."""
    mock_pool.fetchval.return_value = None
    role = await service.get_role(telegram_id=999)
    assert role == "client"


@pytest.mark.asyncio
async def test_set_locale(service, mock_pool):
    """Set user locale (PG + Redis cache concept)."""
    mock_pool.execute.return_value = "UPDATE 1"
    await service.set_locale(telegram_id=123, locale="en")
    mock_pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_locale(service, mock_pool):
    """Get user locale."""
    mock_pool.fetchval.return_value = "uk"
    locale = await service.get_locale(telegram_id=123)
    assert locale == "uk"


@pytest.mark.asyncio
async def test_get_locale_default(service, mock_pool):
    """Unknown user returns default locale."""
    mock_pool.fetchval.return_value = None
    locale = await service.get_locale(telegram_id=999)
    assert locale == "ru"
```

**Step 2: Запустить тест — должен упасть**

Run: `uv run pytest tests/unit/services/test_user_service.py -v`
Expected: FAIL (ImportError)

**Step 3: Реализовать UserService**

Создать `telegram_bot/services/user_service.py`:

```python
"""User CRUD service (asyncpg)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from telegram_bot.models.user import User

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

# Locale detection from Telegram language_code
_LOCALE_MAP = {
    "ru": "ru",
    "uk": "uk",
    "en": "en",
    "be": "ru",  # Belarusian → Russian fallback
}
_DEFAULT_LOCALE = "ru"


def detect_locale(language_code: str | None) -> str:
    """Detect locale from Telegram API language_code."""
    if not language_code:
        return _DEFAULT_LOCALE
    # Try exact match, then 2-char prefix
    code = language_code.lower().strip()
    return _LOCALE_MAP.get(code, _LOCALE_MAP.get(code[:2], _DEFAULT_LOCALE))


class UserService:
    """CRUD operations for users table (asyncpg)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_or_create(
        self,
        *,
        telegram_id: int,
        first_name: str | None = None,
        language_code: str | None = None,
    ) -> User:
        """Get existing user or create new one."""
        row = await self._pool.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id,
        )
        if row is not None:
            return self._row_to_user(row)

        locale = detect_locale(language_code)
        row = await self._pool.fetchrow(
            """INSERT INTO users (telegram_id, locale, first_name, telegram_language_code)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (telegram_id) DO UPDATE SET updated_at = NOW()
               RETURNING *""",
            telegram_id,
            locale,
            first_name,
            language_code,
        )
        return self._row_to_user(row)

    async def get_role(self, *, telegram_id: int) -> str:
        """Get user role. Returns 'client' for unknown users."""
        role = await self._pool.fetchval(
            "SELECT role FROM users WHERE telegram_id = $1",
            telegram_id,
        )
        return role or "client"

    async def get_locale(self, *, telegram_id: int) -> str:
        """Get user locale. Returns 'ru' for unknown users."""
        locale = await self._pool.fetchval(
            "SELECT locale FROM users WHERE telegram_id = $1",
            telegram_id,
        )
        return locale or _DEFAULT_LOCALE

    async def set_locale(self, *, telegram_id: int, locale: str) -> None:
        """Update user locale."""
        await self._pool.execute(
            "UPDATE users SET locale = $1, updated_at = NOW() WHERE telegram_id = $2",
            locale,
            telegram_id,
        )

    @staticmethod
    def _row_to_user(row: Any) -> User:
        """Convert asyncpg Row to User dataclass."""
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            locale=row["locale"],
            role=row["role"],
            first_name=row["first_name"],
            telegram_language_code=row.get("telegram_language_code"),
            notifications_enabled=row["notifications_enabled"],
        )
```

**Step 4: Запустить тест — должен пройти**

Run: `uv run pytest tests/unit/services/test_user_service.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add telegram_bot/services/user_service.py tests/unit/services/test_user_service.py
git commit -m "feat(services): add UserService with asyncpg CRUD"
```

---

### Task 5: Fluent locale files (.ftl)

**Files:**
- Create: `telegram_bot/locales/ru/messages.ftl`
- Create: `telegram_bot/locales/en/messages.ftl`
- Create: `telegram_bot/locales/uk/messages.ftl`

**Step 1: Создать структуру директорий и файлы переводов**

Создать `telegram_bot/locales/ru/messages.ftl`:

```ftl
# Главное меню
hello = Привет, { $name }! Я бот-помощник по недвижимости в Болгарии.
menu-search = Подобрать недвижимость
menu-favorites = Мои подборки
menu-faq = Полезная информация
menu-settings = Настройки
menu-manager = Связаться с менеджером

# Настройки
settings-title = Настройки
settings-language = Язык
settings-notifications = Уведомления
settings-notifications-on = Вкл
settings-notifications-off = Выкл

# Языки
lang-ru = Русский
lang-en = English
lang-uk = Українська

# Навигация
back = Назад
close = Закрыть

# Воронка
funnel-what-looking = Что вас интересует?
funnel-buy-apartment = Купить квартиру
funnel-buy-house = Купить дом
funnel-rent = Арендовать
funnel-just-looking = Просто посмотреть

funnel-area = Какой район интересует?
funnel-budget = Какой бюджет рассматриваете?
funnel-budget-low = До 50 000 €
funnel-budget-mid = 50 000 – 100 000 €
funnel-budget-high = 100 000 – 200 000 €
funnel-budget-premium = Более 200 000 €

funnel-timeline = Когда планируете?
funnel-timeline-asap = В ближайший месяц
funnel-timeline-3m = В течение 3 месяцев
funnel-timeline-6m = В течение полугода
funnel-timeline-looking = Просто присматриваюсь

funnel-results-title = Подобрали для вас:
funnel-results-empty = Пока не нашли подходящих вариантов. Попробуйте изменить параметры.
funnel-booking = Записаться на показ
funnel-subscribe = Подписаться на обновления

# Команды
cmd-help = Задавайте вопросы о недвижимости или используйте меню.
cmd-clear-done = История диалога очищена.
```

Создать `telegram_bot/locales/en/messages.ftl`:

```ftl
# Main menu
hello = Hi, { $name }! I'm a real estate assistant for Bulgaria.
menu-search = Find property
menu-favorites = My selections
menu-faq = Useful info
menu-settings = Settings
menu-manager = Contact manager

# Settings
settings-title = Settings
settings-language = Language
settings-notifications = Notifications
settings-notifications-on = On
settings-notifications-off = Off

# Languages
lang-ru = Русский
lang-en = English
lang-uk = Українська

# Navigation
back = Back
close = Close

# Funnel
funnel-what-looking = What are you looking for?
funnel-buy-apartment = Buy an apartment
funnel-buy-house = Buy a house
funnel-rent = Rent
funnel-just-looking = Just browsing

funnel-area = Which area interests you?
funnel-budget = What is your budget?
funnel-budget-low = Up to €50,000
funnel-budget-mid = €50,000 – €100,000
funnel-budget-high = €100,000 – €200,000
funnel-budget-premium = Over €200,000

funnel-timeline = When are you planning?
funnel-timeline-asap = Within a month
funnel-timeline-3m = Within 3 months
funnel-timeline-6m = Within 6 months
funnel-timeline-looking = Just looking around

funnel-results-title = We found for you:
funnel-results-empty = No matching properties found. Try changing your criteria.
funnel-booking = Book a viewing
funnel-subscribe = Subscribe to updates

# Commands
cmd-help = Ask questions about real estate or use the menu.
cmd-clear-done = Chat history cleared.
```

Создать `telegram_bot/locales/uk/messages.ftl`:

```ftl
# Головне меню
hello = Привіт, { $name }! Я бот-помічник з нерухомості в Болгарії.
menu-search = Підібрати нерухомість
menu-favorites = Мої добірки
menu-faq = Корисна інформація
menu-settings = Налаштування
menu-manager = Зв'язатися з менеджером

# Налаштування
settings-title = Налаштування
settings-language = Мова
settings-notifications = Сповіщення
settings-notifications-on = Увімк
settings-notifications-off = Вимк

# Мови
lang-ru = Русский
lang-en = English
lang-uk = Українська

# Навігація
back = Назад
close = Закрити

# Воронка
funnel-what-looking = Що вас цікавить?
funnel-buy-apartment = Купити квартиру
funnel-buy-house = Купити будинок
funnel-rent = Орендувати
funnel-just-looking = Просто переглядаю

funnel-area = Який район цікавить?
funnel-budget = Який бюджет розглядаєте?
funnel-budget-low = До 50 000 €
funnel-budget-mid = 50 000 – 100 000 €
funnel-budget-high = 100 000 – 200 000 €
funnel-budget-premium = Понад 200 000 €

funnel-timeline = Коли плануєте?
funnel-timeline-asap = Найближчим часом
funnel-timeline-3m = Протягом 3 місяців
funnel-timeline-6m = Протягом півроку
funnel-timeline-looking = Просто придивляюсь

funnel-results-title = Підібрали для вас:
funnel-results-empty = Поки не знайшли відповідних варіантів. Спробуйте змінити параметри.
funnel-booking = Записатися на перегляд
funnel-subscribe = Підписатися на оновлення

# Команди
cmd-help = Ставте питання про нерухомість або використовуйте меню.
cmd-clear-done = Історію діалогу очищено.
```

**Step 2: Commit**

```bash
git add telegram_bot/locales/
git commit -m "feat(i18n): add Fluent locale files (ru, en, uk)"
```

---

### Task 6: i18n Middleware (fluentogram)

**Files:**
- Create: `telegram_bot/middlewares/i18n.py`
- Create: `tests/unit/middlewares/test_i18n.py`
- Modify: `telegram_bot/middlewares/__init__.py`

**Step 1: Написать тест для i18n middleware**

Создать `tests/unit/middlewares/test_i18n.py`:

```python
"""Tests for i18n middleware (fluentogram)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.middlewares.i18n import (
    I18nMiddleware,
    create_translator_hub,
    setup_i18n_middleware,
)


@pytest.fixture
def locales_dir():
    return Path(__file__).resolve().parents[3] / "telegram_bot" / "locales"


@pytest.fixture
def hub(locales_dir):
    return create_translator_hub(locales_dir=locales_dir)


def test_create_translator_hub(hub):
    """TranslatorHub created with 3 locales."""
    translator = hub.get_translator_by_locale("ru")
    assert translator is not None


def test_translator_ru(hub):
    """Russian translation works."""
    t = hub.get_translator_by_locale("ru")
    result = t.get("hello", name="Тест")
    assert "Тест" in result
    assert "бот-помощник" in result


def test_translator_en(hub):
    """English translation works."""
    t = hub.get_translator_by_locale("en")
    result = t.get("hello", name="Test")
    assert "Test" in result
    assert "real estate" in result


def test_translator_uk(hub):
    """Ukrainian translation works."""
    t = hub.get_translator_by_locale("uk")
    result = t.get("hello", name="Тест")
    assert "Тест" in result
    assert "бот-помічник" in result


def test_translator_fallback_unknown_locale(hub):
    """Unknown locale falls back to 'ru'."""
    t = hub.get_translator_by_locale("ru")  # fallback
    result = t.get("hello", name="X")
    assert "X" in result


def test_translator_menu_keys(hub):
    """All menu keys exist in all locales."""
    keys = ["menu-search", "menu-settings", "menu-faq", "back", "close"]
    for locale in ("ru", "en", "uk"):
        t = hub.get_translator_by_locale(locale)
        for key in keys:
            result = t.get(key)
            assert result, f"Missing key '{key}' in locale '{locale}'"
```

**Step 2: Запустить тест — должен упасть**

Run: `uv run pytest tests/unit/middlewares/test_i18n.py -v`
Expected: FAIL (ImportError)

**Step 3: Реализовать i18n middleware**

Создать `telegram_bot/middlewares/i18n.py`:

```python
"""i18n middleware using fluentogram (Fluent .ftl files)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from aiogram import BaseMiddleware, Dispatcher
from fluent_compiler.bundle import FluentBundle
from fluentogram import FluentTranslator, TranslatorHub

if TYPE_CHECKING:
    from aiogram.types import TelegramObject

    from telegram_bot.services.user_service import UserService

logger = logging.getLogger(__name__)


def create_translator_hub(
    *,
    locales_dir: Path | None = None,
) -> TranslatorHub:
    """Create TranslatorHub with all supported locales.

    Args:
        locales_dir: Path to locales directory. Defaults to telegram_bot/locales/.
    """
    if locales_dir is None:
        locales_dir = Path(__file__).resolve().parent.parent / "locales"

    hub = TranslatorHub(
        locales_map={
            "en": ("en",),
            "ru": ("ru", "en"),
            "uk": ("uk", "ru", "en"),
        },
        translators=[
            FluentTranslator(
                locale="en",
                translator=FluentBundle.from_files(
                    "en-US",
                    filenames=[str(p) for p in (locales_dir / "en").glob("*.ftl")],
                ),
            ),
            FluentTranslator(
                locale="ru",
                translator=FluentBundle.from_files(
                    "ru",
                    filenames=[str(p) for p in (locales_dir / "ru").glob("*.ftl")],
                ),
            ),
            FluentTranslator(
                locale="uk",
                translator=FluentBundle.from_files(
                    "uk",
                    filenames=[str(p) for p in (locales_dir / "uk").glob("*.ftl")],
                ),
            ),
        ],
    )
    return hub


class I18nMiddleware(BaseMiddleware):
    """Inject translator (i18n) into handler data based on user locale."""

    def __init__(
        self,
        hub: TranslatorHub,
        user_service: UserService | None = None,
        default_locale: str = "ru",
    ) -> None:
        super().__init__()
        self._hub = hub
        self._user_service = user_service
        self._default_locale = default_locale

    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        locale = self._default_locale

        if user is not None:
            # Try loading from DB/cache via UserService
            if self._user_service is not None:
                try:
                    locale = await self._user_service.get_locale(telegram_id=user.id)
                except Exception:
                    logger.debug("Failed to get locale for user %s", user.id, exc_info=True)

            # Fallback: detect from Telegram language_code
            if locale == self._default_locale and user.language_code:
                from telegram_bot.services.user_service import detect_locale

                locale = detect_locale(user.language_code)

        data["i18n"] = self._hub.get_translator_by_locale(locale)
        data["locale"] = locale
        return await handler(event, data)


def setup_i18n_middleware(
    dp: Dispatcher,
    hub: TranslatorHub,
    user_service: UserService | None = None,
) -> None:
    """Register i18n middleware on all routers."""
    middleware = I18nMiddleware(hub=hub, user_service=user_service)
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
```

**Step 4: Обновить telegram_bot/middlewares/__init__.py**

Добавить экспорт:

```python
"""Middlewares for bot."""

from .error_handler import ErrorHandlerMiddleware, setup_error_middleware
from .i18n import I18nMiddleware, create_translator_hub, setup_i18n_middleware
from .throttling import ThrottlingMiddleware, setup_throttling_middleware


__all__ = [
    "ErrorHandlerMiddleware",
    "I18nMiddleware",
    "ThrottlingMiddleware",
    "create_translator_hub",
    "setup_error_middleware",
    "setup_i18n_middleware",
    "setup_throttling_middleware",
]
```

**Step 5: Запустить тест — должен пройти**

Run: `uv run pytest tests/unit/middlewares/test_i18n.py -v`
Expected: 7 passed

**Step 6: Запустить существующие тесты middlewares**

Run: `uv run pytest tests/unit/test_middlewares.py -v`
Expected: все тесты проходят (без регрессии)

**Step 7: Commit**

```bash
git add telegram_bot/middlewares/i18n.py telegram_bot/middlewares/__init__.py tests/unit/middlewares/test_i18n.py
git commit -m "feat(i18n): add I18nMiddleware with fluentogram TranslatorHub"
```

---

### Task 7: Dialog States (StatesGroup)

**Files:**
- Create: `telegram_bot/dialogs/__init__.py`
- Create: `telegram_bot/dialogs/states.py`

**Step 1: Создать states**

Создать `telegram_bot/dialogs/__init__.py`:

```python
"""aiogram-dialog dialogs for PropertyBot."""
```

Создать `telegram_bot/dialogs/states.py`:

```python
"""FSM states for all dialogs (aiogram-dialog)."""

from aiogram.fsm.state import State, StatesGroup


class ClientMenuSG(StatesGroup):
    """Client main menu."""

    main = State()


class ManagerMenuSG(StatesGroup):
    """Manager main menu."""

    main = State()


class SettingsSG(StatesGroup):
    """User settings dialog."""

    main = State()
    language = State()


class FunnelSG(StatesGroup):
    """BANT sales funnel."""

    property_type = State()
    area = State()
    budget = State()
    timeline = State()
    results = State()


class FaqSG(StatesGroup):
    """FAQ submenu."""

    main = State()
```

**Step 2: Commit**

```bash
git add telegram_bot/dialogs/
git commit -m "feat(dialogs): add StatesGroup for all dialog flows"
```

---

### Task 8: Client Menu Dialog (aiogram-dialog)

**Files:**
- Create: `telegram_bot/dialogs/client_menu.py`
- Create: `tests/unit/dialogs/__init__.py`
- Create: `tests/unit/dialogs/test_client_menu.py`

**Step 1: Написать тест для client menu**

Создать `tests/unit/dialogs/__init__.py` (пустой) и `tests/unit/dialogs/test_client_menu.py`:

```python
"""Tests for client menu dialog."""

from telegram_bot.dialogs.client_menu import client_menu_dialog
from telegram_bot.dialogs.states import ClientMenuSG


def test_client_menu_dialog_exists():
    """Client menu dialog is a valid Dialog."""
    from aiogram_dialog import Dialog

    assert isinstance(client_menu_dialog, Dialog)


def test_client_menu_has_main_window():
    """Client menu has window for ClientMenuSG.main state."""
    windows = client_menu_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert ClientMenuSG.main in states
```

**Step 2: Запустить тест — должен упасть**

Run: `uv run pytest tests/unit/dialogs/test_client_menu.py -v`
Expected: FAIL (ImportError)

**Step 3: Создать client menu dialog**

Создать `telegram_bot/dialogs/client_menu.py`:

```python
"""Client main menu dialog (aiogram-dialog)."""

from __future__ import annotations

from typing import Any

from aiogram_dialog import Dialog, LaunchMode, Window
from aiogram_dialog.widgets.kbd import Column, Start
from aiogram_dialog.widgets.text import Const, Format

from .states import ClientMenuSG, FaqSG, FunnelSG, SettingsSG


async def get_menu_data(
    callback: Any = None,
    event_from_user: Any = None,
    i18n: Any = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Getter: provide localized menu text."""
    name = ""
    if event_from_user is not None:
        name = getattr(event_from_user, "first_name", "") or ""

    if i18n is None:
        # Fallback if i18n not injected (e.g., tests)
        return {
            "greeting": f"Привет, {name}!",
            "btn_search": "Подобрать недвижимость",
            "btn_faq": "Полезная информация",
            "btn_settings": "Настройки",
            "btn_manager": "Связаться с менеджером",
        }

    return {
        "greeting": i18n.get("hello", name=name),
        "btn_search": i18n.get("menu-search"),
        "btn_faq": i18n.get("menu-faq"),
        "btn_settings": i18n.get("menu-settings"),
        "btn_manager": i18n.get("menu-manager"),
    }


client_menu_dialog = Dialog(
    Window(
        Format("{greeting}"),
        Column(
            Start(
                Format("{btn_search}"),
                id="funnel",
                state=FunnelSG.property_type,
            ),
            Start(
                Format("{btn_faq}"),
                id="faq",
                state=FaqSG.main,
            ),
            Start(
                Format("{btn_settings}"),
                id="settings",
                state=SettingsSG.main,
            ),
        ),
        getter=get_menu_data,
        state=ClientMenuSG.main,
    ),
    launch_mode=LaunchMode.ROOT,
)
```

**Step 4: Запустить тест — должен пройти**

Run: `uv run pytest tests/unit/dialogs/test_client_menu.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add telegram_bot/dialogs/client_menu.py tests/unit/dialogs/
git commit -m "feat(dialogs): add client main menu dialog (aiogram-dialog)"
```

---

### Task 9: Settings Dialog (язык + уведомления)

**Files:**
- Create: `telegram_bot/dialogs/settings.py`
- Create: `tests/unit/dialogs/test_settings.py`

**Step 1: Написать тест**

Создать `tests/unit/dialogs/test_settings.py`:

```python
"""Tests for settings dialog."""

from telegram_bot.dialogs.settings import settings_dialog
from telegram_bot.dialogs.states import SettingsSG


def test_settings_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(settings_dialog, Dialog)


def test_settings_has_main_and_language():
    windows = settings_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert SettingsSG.main in states
    assert SettingsSG.language in states
```

**Step 2: Запустить тест — должен упасть**

Run: `uv run pytest tests/unit/dialogs/test_settings.py -v`
Expected: FAIL

**Step 3: Создать settings dialog**

Создать `telegram_bot/dialogs/settings.py`:

```python
"""Settings dialog: language switch, notifications (aiogram-dialog)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Column, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from .states import SettingsSG

logger = logging.getLogger(__name__)

_SUPPORTED_LOCALES = [
    ("ru", "lang-ru"),
    ("en", "lang-en"),
    ("uk", "lang-uk"),
]


async def get_settings_data(i18n: Any = None, **kwargs: Any) -> dict[str, str]:
    """Getter for settings main window."""
    if i18n is None:
        return {"title": "Настройки", "btn_language": "Язык", "btn_back": "Назад"}
    return {
        "title": i18n.get("settings-title"),
        "btn_language": i18n.get("settings-language"),
        "btn_back": i18n.get("back"),
    }


async def get_language_data(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for language selection window."""
    if i18n is None:
        return {"title": "Язык", "btn_back": "Назад", "languages": _SUPPORTED_LOCALES}

    languages = [(code, i18n.get(label_key)) for code, label_key in _SUPPORTED_LOCALES]
    return {
        "title": i18n.get("settings-language"),
        "btn_back": i18n.get("back"),
        "languages": languages,
    }


async def on_language_selected(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Handle language selection button click."""
    locale = button.widget_id  # widget_id = locale code (ru, en, uk)
    user_service = manager.middleware_data.get("user_service")
    if user_service is not None and callback.from_user:
        try:
            await user_service.set_locale(
                telegram_id=callback.from_user.id,
                locale=locale,
            )
        except Exception:
            logger.warning("Failed to save locale for user %s", callback.from_user.id, exc_info=True)
    # Restart dialog to apply new locale
    await manager.done()


settings_dialog = Dialog(
    # Main settings window
    Window(
        Format("{title}"),
        Column(
            SwitchTo(
                Format("{btn_language}"),
                id="lang",
                state=SettingsSG.language,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_settings_data,
        state=SettingsSG.main,
    ),
    # Language selection window
    Window(
        Format("{title}"),
        Column(
            Button(Const("Русский"), id="ru", on_click=on_language_selected),
            Button(Const("English"), id="en", on_click=on_language_selected),
            Button(Const("Українська"), id="uk", on_click=on_language_selected),
        ),
        SwitchTo(Format("{btn_back}"), id="back_to_settings", state=SettingsSG.main),
        getter=get_language_data,
        state=SettingsSG.language,
    ),
)
```

**Step 4: Запустить тест — должен пройти**

Run: `uv run pytest tests/unit/dialogs/test_settings.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add telegram_bot/dialogs/settings.py tests/unit/dialogs/test_settings.py
git commit -m "feat(dialogs): add settings dialog with language switch"
```

---

### Task 10: BotConfig additions + bot.py integration

**Files:**
- Modify: `telegram_bot/config.py:354-358` (add new fields)
- Modify: `telegram_bot/bot.py` (dialog setup, i18n, cmd_start)

**Step 1: Добавить новые поля в BotConfig**

В `telegram_bot/config.py` после поля `judge_model` (строка ~358) добавить:

```python
    # Real Estate Database (realestate DB in shared Postgres)
    realestate_database_url: str = Field(
        default="postgresql://postgres:postgres@postgres:5432/realestate",
        validation_alias=AliasChoices("realestate_database_url", "REALESTATE_DATABASE_URL"),
    )

    # i18n
    supported_locales: list[str] = Field(
        default=["ru", "en", "uk"],
        validation_alias=AliasChoices("supported_locales", "SUPPORTED_LOCALES"),
    )
    default_locale: str = Field(
        default="ru",
        validation_alias=AliasChoices("default_locale", "DEFAULT_LOCALE"),
    )

    # Manager IDs (comma-separated Telegram user IDs)
    manager_ids: list[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices("manager_ids", "MANAGER_IDS"),
    )

    @field_validator("manager_ids", mode="before")
    @classmethod
    def parse_manager_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []
```

**Step 2: Обновить bot.py — __init__**

В `telegram_bot/bot.py`, в классе `PropertyBot.__init__` (после инициализации `_history_service`), добавить:

```python
        # i18n hub (fluentogram)
        self._i18n_hub: Any = None

        # User service (asyncpg) — initialized in start()
        self._user_service: Any = None

        # PostgreSQL pool — initialized in start()
        self._pg_pool: Any = None
```

**Step 3: Обновить bot.py — start()**

В методе `start()` (после инициализации history service, перед preflight), добавить:

```python
        # Initialize PostgreSQL pool for realestate DB
        try:
            import asyncpg

            self._pg_pool = await asyncpg.create_pool(
                self.config.realestate_database_url,
                min_size=1,
                max_size=5,
            )
            logger.info("PostgreSQL pool ready (realestate)")

            from .services.user_service import UserService

            self._user_service = UserService(pool=self._pg_pool)
        except Exception:
            logger.warning("PostgreSQL pool init failed, user features disabled", exc_info=True)

        # Initialize i18n (fluentogram)
        from .middlewares.i18n import create_translator_hub, setup_i18n_middleware

        self._i18n_hub = create_translator_hub()
        setup_i18n_middleware(self.dp, self._i18n_hub, self._user_service)
        logger.info("i18n middleware ready")

        # Setup aiogram-dialog
        from aiogram_dialog import setup_dialogs as aiogram_setup_dialogs

        from .dialogs.client_menu import client_menu_dialog
        from .dialogs.settings import settings_dialog
        from .dialogs.states import ClientMenuSG

        self.dp.include_router(client_menu_dialog)
        self.dp.include_router(settings_dialog)
        aiogram_setup_dialogs(self.dp)
        logger.info("aiogram-dialog setup complete")
```

**Step 4: Обновить cmd_start — запуск меню**

Заменить тело `cmd_start` в `bot.py`:

```python
    async def cmd_start(self, message: Message):
        """Handle /start command — show role-based menu."""
        from aiogram_dialog import DialogManager, StartMode

        # Get or inject DialogManager
        # Note: aiogram-dialog injects DialogManager automatically via middleware
        # We need to get it from the handler's kwargs
        pass  # Will be handled via dialog router
```

> **ВАЖНО:** aiogram-dialog перехватывает /start через свой механизм. Нужно зарегистрировать отдельный handler для /start, который запускает диалог. Это реализуется так:

Вместо замены cmd_start, добавить новый handler ДО регистрации текстового handler'а:

В `_register_handlers` заменить строку с `/start`:

```python
    def _register_handlers(self):
        """Register message handlers."""
        self.dp.message(Command("start"))(self.cmd_start)
        # ... остальные handlers
```

А в `cmd_start` обновить тело:

```python
    async def cmd_start(self, message: Message, dialog_manager: Any = None):
        """Handle /start command — launch menu dialog."""
        if dialog_manager is not None:
            from aiogram_dialog import StartMode

            from .dialogs.states import ClientMenuSG

            # Determine role for future manager menu routing
            await dialog_manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)
        else:
            # Fallback (dialog not initialized)
            domain = self.config.domain
            await message.answer(
                f"Привет! Я бот-помощник по теме: {domain}.\n"
                "Используй /help для помощи."
            )
```

**Step 5: Обновить stop() — закрытие PG pool**

В методе `stop()` перед `await self.bot.session.close()` добавить:

```python
        if self._pg_pool is not None:
            await self._pg_pool.close()
            logger.info("PostgreSQL pool closed")
```

**Step 6: Проверить lint**

Run: `uv run ruff check telegram_bot/bot.py telegram_bot/config.py`
Run: `uv run ruff format telegram_bot/bot.py telegram_bot/config.py`

**Step 7: Запустить существующие тесты**

Run: `uv run pytest tests/unit/test_bot_handlers.py -v`
Expected: все тесты проходят

**Step 8: Commit**

```bash
git add telegram_bot/config.py telegram_bot/bot.py
git commit -m "feat(bot): integrate aiogram-dialog, i18n middleware, PG pool in PropertyBot"
```

---

## Phase 2: Sales Funnel

### Task 11: FAQ Dialog

**Files:**
- Create: `telegram_bot/dialogs/faq.py`
- Create: `tests/unit/dialogs/test_faq.py`

**Step 1: Написать тест**

Создать `tests/unit/dialogs/test_faq.py`:

```python
"""Tests for FAQ dialog."""

from telegram_bot.dialogs.faq import faq_dialog
from telegram_bot.dialogs.states import FaqSG


def test_faq_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(faq_dialog, Dialog)


def test_faq_has_main_window():
    windows = faq_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert FaqSG.main in states
```

**Step 2: Создать FAQ dialog**

Создать `telegram_bot/dialogs/faq.py`:

```python
"""FAQ dialog — static info pages (aiogram-dialog)."""

from __future__ import annotations

from typing import Any

from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Format

from .states import FaqSG


async def get_faq_data(i18n: Any = None, **kwargs: Any) -> dict[str, str]:
    """Getter for FAQ content."""
    if i18n is None:
        return {"title": "FAQ", "btn_back": "Назад"}
    return {
        "title": i18n.get("menu-faq"),
        "btn_back": i18n.get("back"),
    }


faq_dialog = Dialog(
    Window(
        Format("{title}"),
        Cancel(Format("{btn_back}")),
        getter=get_faq_data,
        state=FaqSG.main,
    ),
)
```

**Step 3: Запустить тест**

Run: `uv run pytest tests/unit/dialogs/test_faq.py -v`
Expected: 2 passed

**Step 4: Commit**

```bash
git add telegram_bot/dialogs/faq.py tests/unit/dialogs/test_faq.py
git commit -m "feat(dialogs): add FAQ dialog"
```

---

### Task 12: Funnel Dialog (BANT 4 шага)

**Files:**
- Create: `telegram_bot/dialogs/funnel.py`
- Create: `tests/unit/dialogs/test_funnel.py`

**Step 1: Написать тест**

Создать `tests/unit/dialogs/test_funnel.py`:

```python
"""Tests for BANT funnel dialog."""

from telegram_bot.dialogs.funnel import funnel_dialog
from telegram_bot.dialogs.states import FunnelSG


def test_funnel_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(funnel_dialog, Dialog)


def test_funnel_has_all_windows():
    windows = funnel_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert FunnelSG.property_type in states
    assert FunnelSG.budget in states
    assert FunnelSG.timeline in states
    assert FunnelSG.results in states
```

**Step 2: Создать funnel dialog**

Создать `telegram_bot/dialogs/funnel.py`:

```python
"""BANT sales funnel dialog (aiogram-dialog)."""

from __future__ import annotations

import logging
import operator
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Back, Cancel, Column, Select
from aiogram_dialog.widgets.text import Const, Format

from .states import FunnelSG

logger = logging.getLogger(__name__)


# --- Getters (provide data to windows) ---


async def get_property_types(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for property type selection."""
    if i18n is None:
        items = [
            ("Купить квартиру", "apartment"),
            ("Купить дом", "house"),
            ("Арендовать", "rent"),
            ("Просто посмотреть", "looking"),
        ]
    else:
        items = [
            (i18n.get("funnel-buy-apartment"), "apartment"),
            (i18n.get("funnel-buy-house"), "house"),
            (i18n.get("funnel-rent"), "rent"),
            (i18n.get("funnel-just-looking"), "looking"),
        ]

    title = i18n.get("funnel-what-looking") if i18n else "Что вас интересует?"
    back = i18n.get("back") if i18n else "Назад"
    return {"title": title, "items": items, "btn_back": back}


async def get_budget_options(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for budget selection."""
    if i18n is None:
        items = [
            ("До 50 000 €", "low"),
            ("50 000 – 100 000 €", "mid"),
            ("100 000 – 200 000 €", "high"),
            ("Более 200 000 €", "premium"),
        ]
    else:
        items = [
            (i18n.get("funnel-budget-low"), "low"),
            (i18n.get("funnel-budget-mid"), "mid"),
            (i18n.get("funnel-budget-high"), "high"),
            (i18n.get("funnel-budget-premium"), "premium"),
        ]

    title = i18n.get("funnel-budget") if i18n else "Какой бюджет?"
    back = i18n.get("back") if i18n else "Назад"
    return {"title": title, "items": items, "btn_back": back}


async def get_timeline_options(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for timeline selection."""
    if i18n is None:
        items = [
            ("В ближайший месяц", "asap"),
            ("В течение 3 месяцев", "3months"),
            ("В течение полугода", "6months"),
            ("Просто присматриваюсь", "looking"),
        ]
    else:
        items = [
            (i18n.get("funnel-timeline-asap"), "asap"),
            (i18n.get("funnel-timeline-3m"), "3months"),
            (i18n.get("funnel-timeline-6m"), "6months"),
            (i18n.get("funnel-timeline-looking"), "looking"),
        ]

    title = i18n.get("funnel-timeline") if i18n else "Когда планируете?"
    back = i18n.get("back") if i18n else "Назад"
    return {"title": title, "items": items, "btn_back": back}


async def get_results_data(
    dialog_manager: DialogManager,
    i18n: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for results window — compiles funnel answers."""
    data = dialog_manager.dialog_data
    title = i18n.get("funnel-results-title") if i18n else "Подобрали для вас:"
    empty_msg = i18n.get("funnel-results-empty") if i18n else "Пока не нашли вариантов."
    back = i18n.get("back") if i18n else "Назад"
    return {
        "title": title,
        "property_type": data.get("property_type", ""),
        "budget": data.get("budget", ""),
        "timeline": data.get("timeline", ""),
        "results_text": empty_msg,  # Placeholder — Phase 2 integrates RAG
        "btn_back": back,
    }


# --- Handlers (on_click) ---


async def on_property_type_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save property type and advance to budget."""
    manager.dialog_data["property_type"] = item_id
    await manager.switch_to(FunnelSG.budget)


async def on_budget_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save budget and advance to timeline."""
    manager.dialog_data["budget"] = item_id
    await manager.switch_to(FunnelSG.timeline)


async def on_timeline_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save timeline and show results."""
    manager.dialog_data["timeline"] = item_id
    await manager.switch_to(FunnelSG.results)


# --- Dialog ---


funnel_dialog = Dialog(
    # Step 1: Property type (SPIN: Situation)
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="property_type",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_property_type_selected,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_property_types,
        state=FunnelSG.property_type,
    ),
    # Step 2: Budget (BANT: Budget)
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="budget",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_budget_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_budget_options,
        state=FunnelSG.budget,
    ),
    # Step 3: Timeline (BANT: Timeline)
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="timeline",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_timeline_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_timeline_options,
        state=FunnelSG.timeline,
    ),
    # Step 4: Results
    Window(
        Format("{title}\n\n{results_text}"),
        Cancel(Format("{btn_back}")),
        getter=get_results_data,
        state=FunnelSG.results,
    ),
)
```

**Step 3: Запустить тест**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py -v`
Expected: 2 passed

**Step 4: Зарегистрировать funnel в bot.py**

В `start()` метод, где регистрируются диалоги, добавить:

```python
        from .dialogs.funnel import funnel_dialog
        from .dialogs.faq import faq_dialog

        self.dp.include_router(funnel_dialog)
        self.dp.include_router(faq_dialog)
```

**Step 5: Commit**

```bash
git add telegram_bot/dialogs/funnel.py tests/unit/dialogs/test_funnel.py telegram_bot/bot.py
git commit -m "feat(funnel): add BANT sales funnel dialog (4 steps)"
```

---

### Task 13: Lead Scoring

**Files:**
- Create: `telegram_bot/services/lead_scoring.py`
- Create: `tests/unit/services/test_lead_scoring.py`

**Step 1: Написать тест**

Создать `tests/unit/services/test_lead_scoring.py`:

```python
"""Tests for lead scoring (rule-based)."""

from telegram_bot.services.lead_scoring import compute_lead_score, classify_lead


def test_hot_lead():
    """ASAP timeline + defined budget + type = hot."""
    score = compute_lead_score(
        property_type="apartment",
        budget="mid",
        timeline="asap",
    )
    assert score >= 60  # Hot threshold


def test_cold_lead():
    """Just looking = cold."""
    score = compute_lead_score(
        property_type="looking",
        budget=None,
        timeline="looking",
    )
    assert score < 30


def test_warm_lead():
    """Defined type + 3 months = warm."""
    score = compute_lead_score(
        property_type="house",
        budget="high",
        timeline="3months",
    )
    assert 30 <= score < 60 or score >= 60  # warm or hot


def test_classify_hot():
    assert classify_lead(65) == "hot"


def test_classify_warm():
    assert classify_lead(45) == "warm"


def test_classify_cold():
    assert classify_lead(15) == "cold"
```

**Step 2: Реализовать scoring**

Создать `telegram_bot/services/lead_scoring.py`:

```python
"""Rule-based lead scoring for sales funnel."""

from __future__ import annotations

# Points per funnel answer
_TIMELINE_SCORES = {
    "asap": 40,
    "3months": 25,
    "6months": 15,
    "looking": 5,
}

_BUDGET_BONUS = 20  # Any defined budget
_TYPE_BONUS = 10    # Any defined property type (not "looking")


def compute_lead_score(
    *,
    property_type: str | None = None,
    budget: str | None = None,
    timeline: str | None = None,
) -> int:
    """Compute lead score (0-100) from funnel answers."""
    score = 0

    if timeline:
        score += _TIMELINE_SCORES.get(timeline, 0)

    if budget:
        score += _BUDGET_BONUS

    if property_type and property_type != "looking":
        score += _TYPE_BONUS

    return min(score, 100)


def classify_lead(score: int) -> str:
    """Classify lead by score: hot (>=60), warm (30-59), cold (<30)."""
    if score >= 60:
        return "hot"
    if score >= 30:
        return "warm"
    return "cold"
```

**Step 3: Запустить тест**

Run: `uv run pytest tests/unit/services/test_lead_scoring.py -v`
Expected: 6 passed

**Step 4: Commit**

```bash
git add telegram_bot/services/lead_scoring.py tests/unit/services/test_lead_scoring.py
git commit -m "feat(scoring): add rule-based lead scoring (BANT)"
```

---

### Task 14: Lint + полный test suite

**Step 1: Lint всего проекта**

Run: `uv run ruff check telegram_bot/ tests/ --fix`
Run: `uv run ruff format telegram_bot/ tests/`

**Step 2: Type check**

Run: `uv run mypy telegram_bot/models/ telegram_bot/services/user_service.py telegram_bot/services/lead_scoring.py telegram_bot/middlewares/i18n.py telegram_bot/dialogs/ --ignore-missing-imports`

**Step 3: Полный unit test suite**

Run: `uv run pytest tests/unit/ -n auto -v`
Expected: все тесты проходят (новые + существующие)

**Step 4: Commit (если были авто-фиксы)**

```bash
git add -u
git commit -m "style: fix lint issues in menu/i18n/funnel code"
```

---

## Phase 3: Manager Role + Role-based Tools (отдельный issue)

> **Scope:** Task 15-17. Отложено до Phase 1-2 готовы и протестированы.

### Task 15: Manager Menu Dialog
- Create: `telegram_bot/dialogs/manager_menu.py`
- Кнопки: Лиды, Поиск по CRM, Сводка, Настройки

### Task 16: Role-based tool sets в tools.py
- Modify: `telegram_bot/agents/tools.py`
- Функция `get_tools_for_role(role, services)` → разные наборы tools

### Task 17: Hot lead notification
- При score >= 60 → отправить Telegram-сообщение менеджерам из `manager_ids`

---

## Phase 4: CRM Integration (Kommo) — отдельный issue

> **Scope:** Task 18-20. Отложено до настройки CRM.

### Task 18: CRM Protocol + Kommo client
### Task 19: CRM supervisor tools
### Task 20: Lead sync PG → Kommo

---

## Phase 5: Nurturing + Analytics — отдельный issue

> **Scope:** Task 21-22. Отложено.

### Task 21: Scheduled property updates
### Task 22: Funnel analytics (conversion, drop-off)

---

## Порядок GitHub Issues

| Issue | Title | Phase | Tasks |
|-------|-------|-------|-------|
| #1 | `feat(bot): menu + i18n foundation (aiogram-dialog, fluentogram)` | Phase 1 | Tasks 1-10 |
| #2 | `feat(bot): BANT sales funnel + lead scoring` | Phase 2 | Tasks 11-14 |
| #3 | `feat(bot): manager role + role-based tools` | Phase 3 | Tasks 15-17 |
| #4 | `feat(bot): CRM integration (Kommo)` | Phase 4 | Tasks 18-20 |
| #5 | `feat(bot): nurturing + funnel analytics` | Phase 5 | Tasks 21-22 |
