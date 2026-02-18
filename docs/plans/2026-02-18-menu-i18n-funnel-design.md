# Design: Меню, i18n, Воронка продаж, CRM (PropertyBot)

**Дата:** 2026-02-18
**Статус:** Draft
**Scope:** Обновление существующего PropertyBot — добавление меню, мультиязычности, продающей воронки и CRM-интеграции

---

## 1. Обзор

Расширяем PropertyBot двумя ролями с разным UI и набором tools:

| Роль | UI | Supervisor Tools | Storage |
|------|----|--------------------|---------|
| **Клиент** | Меню (aiogram-dialog) + свободный текст | `rag_search`, `history_search`, `faq_search`, `direct_response` | Postgres: users, leads, funnel_events |
| **Менеджер** | Менеджерское меню + свободный текст | `rag_search`, `crm_search`, `crm_create_deal`, `client_history`, `handoff`, `direct_response` | Postgres: users + Kommo API |

Определение роли: по `admin_ids` (конфиг) или по `users.role` (БД).

---

## 2. Архитектура

```
/start → определяем роль (client | manager | admin)
       → показываем главное меню (aiogram-dialog) на языке пользователя

Клиент:
  Кнопка → aiogram-dialog обрабатывает (воронка, FAQ, настройки)
  Текст  → supervisor с client-tools → RAG pipeline → ответ

Менеджер:
  Кнопка → aiogram-dialog обрабатывает (CRM, клиенты, сводка)
  Текст  → supervisor с manager-tools → RAG/CRM → ответ
```

### Поток данных

```
User Input
    │
    ├── [callback_query] → aiogram-dialog Router → Dialog/Window
    │                       ├── Воронка: Select/Radio → сохраняем preferences
    │                       ├── Настройки: смена языка → PG + Redis
    │                       ├── FAQ: статичный контент из .ftl
    │                       └── Результаты: запуск RAG с фильтрами из preferences
    │
    └── [text/voice] → существующий flow:
                        ThrottlingMW → ErrorMW → i18nMW (NEW)
                        → handle_query() → supervisor (role-based tools)
                        → RAG pipeline → respond
```

---

## 3. Структура файлов (добавления к telegram_bot/)

```
telegram_bot/
├── bot.py                          # Обновляем: + dialog setup, + role routing, + i18n MW
├── dialogs/                        # NEW
│   ├── __init__.py
│   ├── states.py                   # Все StatesGroup в одном месте
│   ├── client_menu.py              # Главное меню клиента (6 кнопок)
│   ├── manager_menu.py             # Главное меню менеджера
│   ├── settings.py                 # Настройки (язык, уведомления)
│   ├── funnel.py                   # BANT-воронка (4-5 шагов)
│   ├── results.py                  # Показ результатов поиска
│   └── faq.py                      # FAQ подменю
├── middlewares/
│   ├── throttling.py               # Существующий
│   ├── error_handler.py            # Существующий
│   └── i18n.py                     # NEW: загрузка locale из Redis/PG
├── locales/                        # NEW
│   ├── en/
│   │   ├── messages.ftl            # Основные тексты
│   │   └── buttons.ftl             # Тексты кнопок
│   ├── ru/
│   │   ├── messages.ftl
│   │   └── buttons.ftl
│   └── uk/
│       ├── messages.ftl
│       └── buttons.ftl
├── services/
│   ├── user_service.py             # NEW: CRUD users/leads (asyncpg)
│   ├── crm_client.py              # NEW: CRM protocol + Kommo impl (Phase 4)
│   └── ...                         # Существующие без изменений
├── agents/
│   ├── supervisor.py               # Существующий (без изменений)
│   ├── tools.py                    # Обновляем: + role-based tool sets
│   ├── rag_agent.py                # Существующий
│   ├── history_agent.py            # Существующий
│   └── crm_tools.py               # NEW: crm_search, crm_create_deal (Phase 4)
└── models/
    └── user.py                     # NEW: dataclasses User, Lead, FunnelEvent
```

---

## 4. Стек и зависимости

### Новые зависимости

```toml
# pyproject.toml
"aiogram-dialog>=2.4.0",          # GUI framework (meню, навигация, виджеты)
"fluentogram>=1.2.0",             # i18n (Fluent .ftl, stub generator, fallback chains)
```

### Существующие (переиспользуем)

| Компонент | Что используем |
|-----------|---------------|
| `asyncpg>=0.31.0` | Уже в deps — прямые SQL-запросы к PG |
| `redis>=7.1.0` | Кэш locale, nav_stack, FSM storage для dialog |
| `aiogram>=3.25.0` | Dispatcher, Router, Middleware |
| LangGraph supervisor | Role-based tool sets |

### НЕ добавляем (YAGNI)

- ~~SQLAlchemy~~ — для 3-4 таблиц asyncpg напрямую проще
- ~~Alembic~~ — init-скрипт в docker/postgres/init/ (паттерн уже есть)
- ~~Supabase~~ — Postgres уже в docker-compose

---

## 5. Storage

### PostgreSQL (новая БД `realestate` в том же контейнере)

```sql
-- docker/postgres/init/05-realestate-schema.sql

CREATE DATABASE realestate;
\c realestate;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    locale VARCHAR(5) DEFAULT 'ru',        -- en, ru, uk
    role VARCHAR(20) DEFAULT 'client',     -- client, manager, admin
    first_name VARCHAR(100),
    telegram_language_code VARCHAR(10),    -- автодетект из Telegram API
    notifications_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE leads (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    stage VARCHAR(30) DEFAULT 'new',       -- new, qualified, hot, warm, cold, converted
    score INTEGER DEFAULT 0,               -- 0-100
    preferences JSONB DEFAULT '{}',        -- {type, area, budget, timeline, ...}
    kommo_lead_id BIGINT,                  -- Phase 4: synced lead ID
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE funnel_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event_type VARCHAR(50) NOT NULL,       -- started_funnel, selected_type, selected_area, etc.
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_leads_user_id ON leads(user_id);
CREATE INDEX idx_leads_stage ON leads(stage);
CREATE INDEX idx_funnel_events_user_id ON funnel_events(user_id);
CREATE INDEX idx_funnel_events_created ON funnel_events(created_at DESC);
```

### Redis (горячий кэш)

```
user:{tg_id}:locale      → "uk"           # Быстрый доступ (TTL 24h)
user:{tg_id}:role         → "client"       # Роль (TTL 24h)
dialog:{tg_id}:nav       → JSON stack     # aiogram-dialog FSM (managed by library)
```

**Паттерн:** PG = source of truth. Redis = read cache. Write-through при изменениях.

---

## 6. i18n (fluentogram)

### Конфигурация

```python
# telegram_bot/middlewares/i18n.py
from fluentogram import TranslatorHub, FluentTranslator

hub = TranslatorHub(
    locales_map={
        "en": ("en",),
        "ru": ("ru", "en"),        # fallback: ru → en
        "uk": ("uk", "ru", "en"),  # fallback: uk → ru → en
    },
    translators=[
        FluentTranslator("en", translator=FluentBundle.from_files("en-US", ["locales/en/"])),
        FluentTranslator("ru", translator=FluentBundle.from_files("ru", ["locales/ru/"])),
        FluentTranslator("uk", translator=FluentBundle.from_files("uk", ["locales/uk/"])),
    ],
)
```

### Middleware

```python
class I18nMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            locale = await get_user_locale(user.id)  # Redis → PG fallback
            if not locale:
                locale = detect_locale(user.language_code)  # Telegram API
                await save_user_locale(user.id, locale)
            data["i18n"] = hub.get_translator_by_locale(locale)
        return await handler(event, data)
```

### Файлы переводов

```ftl
# locales/ru/messages.ftl
hello = Привет, { $name }! Я бот-помощник по недвижимости.
menu-search = 🔍 Подобрать недвижимость
menu-favorites = 📋 Мои подборки
menu-booking = 📅 Записаться на показ
menu-manager = 💬 Связаться с менеджером
menu-faq = ❓ Полезная информация
menu-settings = ⚙️ Настройки
settings-language = 🌐 Язык
settings-notifications = 🔔 Уведомления
back = ⬅️ Назад

# Воронка
funnel-what-looking = Расскажите, что ищете?
funnel-buy-apartment = 🏠 Купить квартиру
funnel-buy-house = 🏢 Купить дом
funnel-rent = 🔑 Арендовать
funnel-just-looking = 💬 Просто посмотреть

funnel-area = Какой район вас интересует?
funnel-budget = Какой бюджет рассматриваете?
funnel-timeline = Когда планируете заселиться?
funnel-timeline-asap = 🔥 В ближайший месяц
funnel-timeline-3m = 📅 В течение 3 месяцев
funnel-timeline-looking = 🔍 Просто присматриваюсь
```

---

## 7. Меню (aiogram-dialog)

### States

```python
# telegram_bot/dialogs/states.py
from aiogram.fsm.state import StatesGroup, State

class ClientMenuSG(StatesGroup):
    main = State()

class ManagerMenuSG(StatesGroup):
    main = State()

class SettingsSG(StatesGroup):
    main = State()
    language = State()
    notifications = State()

class FunnelSG(StatesGroup):
    property_type = State()
    area = State()
    budget = State()
    timeline = State()
    results = State()

class FaqSG(StatesGroup):
    main = State()
    mortgage = State()
    documents = State()
    process = State()
```

### Главное меню клиента

```python
# telegram_bot/dialogs/client_menu.py
from aiogram_dialog import Dialog, Window, LaunchMode
from aiogram_dialog.widgets.kbd import Start, Column
from aiogram_dialog.widgets.text import Format

async def get_menu_text(i18n, **kwargs):
    return {"greeting": i18n.hello(name=kwargs.get("event_from_user").first_name)}

client_menu = Dialog(
    Window(
        Format("{greeting}"),
        Column(
            Start(Format("{i18n.menu_search}"), id="search", state=FunnelSG.property_type),
            Start(Format("{i18n.menu_favorites}"), id="favs", state=FavoritesSG.main),
            Start(Format("{i18n.menu_booking}"), id="book", state=BookingSG.main),
            Start(Format("{i18n.menu_manager}"), id="mgr", state=HandoffSG.main),
            Start(Format("{i18n.menu_faq}"), id="faq", state=FaqSG.main),
            Start(Format("{i18n.menu_settings}"), id="set", state=SettingsSG.main),
        ),
        getter=get_menu_text,
        state=ClientMenuSG.main,
    ),
    launch_mode=LaunchMode.ROOT,  # Всегда корневой — /start сбрасывает стек
)
```

### Воронка BANT

```python
# telegram_bot/dialogs/funnel.py
funnel_dialog = Dialog(
    # Этап 1: Тип (SPIN: Situation)
    Window(
        Format("{i18n.funnel_what_looking}"),
        Select(
            Format("{item[0]}"),
            id="property_type",
            item_id_getter=operator.itemgetter(1),
            items="property_types",  # из getter
            on_click=on_property_type_selected,
        ),
        Cancel(Format("{i18n.back}")),
        getter=get_property_types,
        state=FunnelSG.property_type,
    ),
    # Этап 2: Район (BANT: Need)
    Window(
        Format("{i18n.funnel_area}"),
        Select(...),
        Back(Format("{i18n.back}")),
        state=FunnelSG.area,
    ),
    # Этап 3: Бюджет (BANT: Budget)
    Window(
        Format("{i18n.funnel_budget}"),
        Radio(...),  # Radio сохраняет выбор
        Back(Format("{i18n.back}")),
        state=FunnelSG.budget,
    ),
    # Этап 4: Сроки (BANT: Timeline)
    Window(
        Format("{i18n.funnel_timeline}"),
        Select(...),
        Back(Format("{i18n.back}")),
        state=FunnelSG.timeline,
    ),
    # Этап 5: Результаты → RAG поиск с фильтрами
    Window(
        Format("{results_text}"),
        # Кнопки зависят от скоринга (горячий/холодный)
        SwitchTo(Format("{i18n.booking}"), id="book", state=...),  # горячий
        SwitchTo(Format("{i18n.subscribe}"), id="sub", state=...),  # холодный
        Cancel(Format("{i18n.back}")),
        getter=get_search_results,  # вызывает RAG pipeline
        state=FunnelSG.results,
    ),
    on_start=on_funnel_start,  # логируем funnel_event
)
```

### Callback data (короткие, в пределах 64 байт)

aiogram-dialog генерирует callback_data автоматически — **не нужно руками**. Формат: `{dialog_id}:{widget_id}:{item_id}` — всё в пределах лимита.

---

## 8. Role-based Supervisor Tools

### Текущий flow (сохраняем)

```python
# handle_query → supervisor → tools
USE_SUPERVISOR=true
```

### Расширение: tool sets по роли

```python
# telegram_bot/agents/tools.py

def get_tools_for_role(role: str, *, services) -> list:
    """Возвращает набор tools по роли пользователя."""
    base_tools = [
        create_rag_agent(**services),
        direct_response,
    ]

    if role == "client":
        return base_tools + [
            create_history_search_tool(history_service=services["history"]),
        ]

    if role in ("manager", "admin"):
        return base_tools + [
            create_history_search_tool(history_service=services["history"]),
            create_crm_search_tool(crm=services["crm"]),         # Phase 4
            create_crm_create_deal_tool(crm=services["crm"]),     # Phase 4
            create_client_history_tool(db=services["db"]),         # Phase 4
        ]

    return base_tools
```

### Обновление handle_query

```python
async def handle_query(self, message: Message):
    user_role = await self._user_service.get_role(message.from_user.id)
    tools = get_tools_for_role(user_role, services=self._services)

    if self._config.use_supervisor:
        graph = build_supervisor_graph(supervisor_llm=self._llm, tools=tools)
        # ... invoke с role-specific tools
    else:
        # Прямой RAG pipeline (как сейчас)
        ...
```

---

## 9. Lead Scoring

Простой rule-based скоринг по ответам воронки:

```python
SCORING_RULES = {
    "timeline": {
        "asap": 40,       # 🔥 В ближайший месяц
        "3months": 25,    # 📅 В течение 3 месяцев
        "looking": 5,     # 🔍 Просто присматриваюсь
    },
    "budget_defined": 20,  # Указал конкретный бюджет
    "area_defined": 15,    # Указал район
    "type_defined": 10,    # Указал тип недвижимости
    "booking_requested": 30,  # Нажал "Записаться на показ"
}

# score >= 60 → горячий → уведомить менеджера
# score 30-59 → тёплый → nurturing
# score < 30  → холодный → подписка на обновления
```

---

## 10. Интеграция с существующим кодом

### Что меняем в bot.py

```python
class PropertyBot:
    def __init__(self, config):
        # ... существующая инициализация ...

        # NEW: i18n
        self._i18n_hub = create_translator_hub()

        # NEW: user service
        self._user_service = UserService(pg_pool=self._pg_pool)

        # NEW: aiogram-dialog
        setup_dialogs(self.dp)

    def _register_handlers(self):
        # Существующие (без изменений)
        self.dp.message(Command("start"))(self.cmd_start)  # обновляем: + menu
        self.dp.message(F.voice)(self.handle_voice)
        self.dp.message(F.text)(self.handle_query)
        self.dp.callback_query(F.data.startswith("fb:"))(self.handle_feedback)

        # NEW: регистрация диалогов
        self.dp.include_router(client_menu)
        self.dp.include_router(manager_menu)
        self.dp.include_router(settings_dialog)
        self.dp.include_router(funnel_dialog)
        self.dp.include_router(faq_dialog)

    def _register_middlewares(self):
        # Существующие
        setup_throttling_middleware(self.dp, ...)
        setup_error_middleware(self.dp, ...)
        # NEW
        setup_i18n_middleware(self.dp, self._i18n_hub, self._user_service)

    async def cmd_start(self, message: Message, dialog_manager: DialogManager):
        """Обновлённый /start — определяет роль и показывает меню."""
        user = await self._user_service.get_or_create(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name,
            language_code=message.from_user.language_code,
        )

        if user.role in ("manager", "admin"):
            await dialog_manager.start(ManagerMenuSG.main, mode=StartMode.RESET_STACK)
        else:
            await dialog_manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)
```

### Что НЕ меняем

- `telegram_bot/graph/` — весь RAG pipeline без изменений
- `telegram_bot/agents/supervisor.py` — логика не меняется
- `telegram_bot/agents/rag_agent.py` — без изменений
- `telegram_bot/agents/history_agent.py` — без изменений
- `telegram_bot/observability.py` — без изменений
- `telegram_bot/services/` — существующие сервисы без изменений

---

## 11. Фазы реализации (GitHub Issues)

### Phase 1: Foundation — Menu + i18n
**~800 LOC, 3-4 дня**

- [ ] Добавить `aiogram-dialog`, `fluentogram` в pyproject.toml
- [ ] Создать `docker/postgres/init/05-realestate-schema.sql`
- [ ] Создать `telegram_bot/models/user.py` (dataclasses)
- [ ] Создать `telegram_bot/services/user_service.py` (asyncpg CRUD)
- [ ] Создать `telegram_bot/middlewares/i18n.py` (locale loading)
- [ ] Создать `locales/{en,ru,uk}/messages.ftl` (основные строки)
- [ ] Создать `telegram_bot/dialogs/states.py`
- [ ] Создать `telegram_bot/dialogs/client_menu.py` (главное меню)
- [ ] Создать `telegram_bot/dialogs/settings.py` (язык, уведомления)
- [ ] Обновить `bot.py`: dialog setup, i18n middleware, cmd_start с меню
- [ ] Тесты: menu rendering, locale switching, user CRUD

### Phase 2: Sales Funnel
**~600 LOC, 2-3 дня**

- [ ] Создать `telegram_bot/dialogs/funnel.py` (BANT 4-5 шагов)
- [ ] Создать `telegram_bot/dialogs/results.py` (показ результатов)
- [ ] Интеграция: funnel results → RAG pipeline с фильтрами из preferences
- [ ] Lead scoring (rule-based)
- [ ] Сохранение lead + funnel_events в PG
- [ ] FAQ dialog
- [ ] Тесты: funnel flow, scoring, PG writes

### Phase 3: Manager Role
**~400 LOC, 2 дня**

- [ ] Создать `telegram_bot/dialogs/manager_menu.py`
- [ ] Role-based tool sets в `tools.py`
- [ ] Менеджерский dashboard (сводка лидов, горячие/тёплые)
- [ ] Уведомление менеджера о горячем лиде (Telegram message)
- [ ] Handoff: клиент → менеджер (кнопка "Связаться с менеджером")
- [ ] Тесты: role routing, manager tools

### Phase 4: CRM Integration (Kommo)
**~500 LOC, 3 дня (когда CRM будет настроена)**

- [ ] Создать `telegram_bot/services/crm_client.py` (protocol + Kommo impl)
- [ ] CRM tools: `crm_search`, `crm_create_deal`, `crm_update_deal`
- [ ] Синхронизация leads PG → Kommo
- [ ] Тесты: CRM API mocks

### Phase 5: Nurturing + Analytics
**~300 LOC, 2 дня**

- [ ] Scheduled подборки по preferences (Qdrant query)
- [ ] Полезный контент из RAG базы
- [ ] Аналитика воронки: конверсия по этапам, drop-off
- [ ] BotFather локализация (имя, описание, команды на 3 языках)

---

## 12. Риски и ограничения

| Риск | Митигация |
|------|-----------|
| aiogram-dialog конфликт с существующими callback handlers | Dialog router регистрируется ДО `F.data.startswith("fb:")` — приоритет по порядку |
| FSM storage для dialog (нужен persistent) | `RedisStorage` (aiogram) — уже есть Redis |
| fluentogram не работает с aiogram-dialog Format | Передаём translator через getter, Format использует данные из getter |
| Postgres init-скрипт не перезапускается на существующем volume | Добавить `IF NOT EXISTS` / idempotent DDL (паттерн из 03-unified) |
| Менеджер и клиент в одном боте — разный UX | Role check в cmd_start + middleware, разные StatesGroup |

---

## 13. Тестирование

```bash
# Unit: меню, i18n, user service
uv run pytest tests/unit/dialogs/ -n auto
uv run pytest tests/unit/services/test_user_service.py -n auto
uv run pytest tests/unit/middlewares/test_i18n.py -n auto

# Integration: PG writes, locale switching
uv run pytest tests/integration/test_user_flow.py -v

# Existing tests: НЕ ломаются (RAG pipeline без изменений)
uv run pytest tests/unit/ -n auto
```

---

## 14. Конфигурация (BotConfig additions)

```python
# telegram_bot/config.py
class BotConfig(BaseSettings):
    # ... существующие поля ...

    # NEW
    realestate_database_url: str = Field(
        default="postgresql://postgres:postgres@postgres:5432/realestate",
        alias=AliasChoices("REALESTATE_DATABASE_URL"),
    )
    supported_locales: list[str] = Field(default=["ru", "en", "uk"])
    default_locale: str = Field(default="ru")
    manager_ids: list[int] = Field(default=[])  # Telegram IDs менеджеров
```
