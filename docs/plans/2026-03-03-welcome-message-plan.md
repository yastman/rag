# Welcome Message Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Заменить маркетинговый welcome на персонализированное приветствие с описанием возможностей бота, обновить ReplyKeyboard (убрать Акции, добавить "Задать вопрос"), добавить second-level inline FAQ menu.

**Architecture:** Только текстовые изменения в .ftl + обновление клавиатуры в `client_keyboard.py` + новый handler `_handle_ask` в `bot.py` с InlineKeyboard для FAQ. Callback `ask:*` прокидывает текст в существующий `handle_query`.

**Tech Stack:** aiogram 3, Fluent i18n (.ftl), aiogram InlineKeyboardMarkup

**Design doc:** `docs/plans/2026-03-03-welcome-message-design.md`

---

### Task 1: Обновить ReplyKeyboard — тесты

**Files:**
- Modify: `tests/unit/keyboards/test_client_keyboard.py`

**Step 1: Обновить тесты клавиатуры под новую структуру**

Заменить все упоминания `promotions` на `ask`. Обновить fallback-тексты.
Проверить что кнопки соответствуют новому layout:

```python
# В MENU_BUTTONS теперь:
# "🏠 Подобрать квартиру": "search",
# "🔑 Услуги": "services",
# "📅 Запись на осмотр": "viewing",
# "👤 Менеджер": "manager",
# "💬 Задать вопрос": "ask",
# "📌 Мои закладки": "bookmarks",

# Обновить test_parse_menu_button_known:
def test_parse_menu_button_known():
    assert parse_menu_button("🏠 Подобрать квартиру") == "search"
    assert parse_menu_button("🔑 Услуги") == "services"
    assert parse_menu_button("📅 Запись на осмотр") == "viewing"
    assert parse_menu_button("👤 Менеджер") == "manager"
    assert parse_menu_button("💬 Задать вопрос") == "ask"
    assert parse_menu_button("📌 Мои закладки") == "bookmarks"

# Обновить test_build_with_i18n — заменить kb-promotions на kb-ask
# Обновить test_parse_with_i18n_hub — заменить kb-promotions на kb-ask
# Обновить test_get_menu_button_texts_includes_localized_labels — заменить promotions на ask
```

**Step 2: Запустить тесты — убедиться что FAIL**

Run: `uv run pytest tests/unit/keyboards/test_client_keyboard.py -v`
Expected: FAIL — старые тексты кнопок не совпадают

---

### Task 2: Обновить ReplyKeyboard — реализация

**Files:**
- Modify: `telegram_bot/keyboards/client_keyboard.py:12-32`

**Step 1: Обновить MENU_BUTTONS и _ACTION_IDS**

```python
# Было:
MENU_BUTTONS: dict[str, str] = {
    "🏠 Подбор апартаментов": "search",
    "🔑 Услуги": "services",
    "📅 Запись на осмотр": "viewing",
    "📌 Мои закладки": "bookmarks",
    "🎁 Акции": "promotions",
    "👤 Связь с менеджером": "manager",
}

# Стало:
MENU_BUTTONS: dict[str, str] = {
    "🏠 Подобрать квартиру": "search",
    "🔑 Услуги": "services",
    "📅 Запись на осмотр": "viewing",
    "👤 Менеджер": "manager",
    "💬 Задать вопрос": "ask",
    "📌 Мои закладки": "bookmarks",
}

# Было:
_ACTION_IDS: dict[str, str] = {
    "kb-search": "search",
    "kb-services": "services",
    "kb-viewing": "viewing",
    "kb-bookmarks": "bookmarks",
    "kb-promotions": "promotions",
    "kb-manager": "manager",
}

# Стало:
_ACTION_IDS: dict[str, str] = {
    "kb-search": "search",
    "kb-services": "services",
    "kb-viewing": "viewing",
    "kb-manager": "manager",
    "kb-ask": "ask",
    "kb-bookmarks": "bookmarks",
}
```

**Step 2: Запустить тесты — убедиться что PASS**

Run: `uv run pytest tests/unit/keyboards/test_client_keyboard.py -v`
Expected: PASS

**Step 3: Коммит**

```bash
git add telegram_bot/keyboards/client_keyboard.py tests/unit/keyboards/test_client_keyboard.py
git commit -m "feat(keyboard): replace Promotions with Ask Question button

Update ReplyKeyboard layout: remove 🎁 Акции, add 💬 Задать вопрос,
shorten button labels (Подобрать квартиру, Менеджер).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Обновить i18n (.ftl) — 3 локали

**Files:**
- Modify: `telegram_bot/locales/ru/messages.ftl:2,154-176`
- Modify: `telegram_bot/locales/en/messages.ftl:2,154-176`
- Modify: `telegram_bot/locales/uk/messages.ftl:2,162-176`

**Step 1: Обновить ru/messages.ftl**

Заменить:
```fluent
# Строка 2 — оставить как есть (hello используется в client_menu_dialog)
hello = Привет, { $name }! Я бот-помощник по недвижимости в Болгарии.

# Строки 154-160 — обновить ReplyKeyboard ключи:
kb-search = 🏠 Подобрать квартиру
kb-services = 🔑 Услуги
kb-viewing = 📅 Запись на осмотр
kb-manager = 👤 Менеджер
kb-ask = 💬 Задать вопрос
kb-bookmarks = 📌 Мои закладки

# Строки 162-176 — заменить welcome-text:
welcome-text =
    Привет, { $name }! 👋

    Я бот FortNoks Estate — помогу с недвижимостью
    в Болгарии. Вот что умею:

    🏠 Подобрать апартаменты по вашим параметрам
    🔑 Рассказать об услугах агентства
    📅 Записать на осмотр или инфотур
    👤 Связать с менеджером
    💬 Ответить на вопросы о покупке, документах,
       ценах и жизни в Болгарии

    Выберите действие внизу или просто напишите вопрос 👇

# Новые ключи — добавить после welcome-text:
ask-prompt =
    💬 Напишите вопрос — мы с радостью ответим!

    Или выберите популярную тему:
ask-docs = 📋 Какие документы нужны для покупки?
ask-costs = 💰 Сколько стоит оформление сделки?
ask-vnzh = 📋 Как получить ВНЖ в Болгарии?
ask-installment = 💳 Какие условия рассрочки?
```

**Step 2: Обновить en/messages.ftl — аналогично на английском**

```fluent
kb-search = 🏠 Find Apartment
kb-services = 🔑 Services
kb-viewing = 📅 Book a Viewing
kb-manager = 👤 Manager
kb-ask = 💬 Ask a Question
kb-bookmarks = 📌 My Bookmarks

welcome-text =
    Hi, { $name }! 👋

    I'm the FortNoks Estate bot — I'll help with
    real estate in Bulgaria. Here's what I can do:

    🏠 Find apartments matching your criteria
    🔑 Tell you about our services
    📅 Book a viewing or info tour
    👤 Connect you with a manager
    💬 Answer questions about buying, documents,
       prices and living in Bulgaria

    Choose an action below or just type your question 👇

ask-prompt =
    💬 Type your question — we'll be happy to help!

    Or choose a popular topic:
ask-docs = 📋 What documents are needed to buy?
ask-costs = 💰 How much does the transaction cost?
ask-vnzh = 📋 How to get a residence permit in Bulgaria?
ask-installment = 💳 What are the installment terms?
```

**Step 3: Обновить uk/messages.ftl — аналогично на украинском**

```fluent
kb-search = 🏠 Підібрати квартиру
kb-services = 🔑 Послуги
kb-viewing = 📅 Запис на огляд
kb-manager = 👤 Менеджер
kb-ask = 💬 Задати питання
kb-bookmarks = 📌 Мої закладки

welcome-text =
    Привіт, { $name }! 👋

    Я бот FortNoks Estate — допоможу з нерухомістю
    в Болгарії. Ось що вмію:

    🏠 Підібрати апартаменти за вашими параметрами
    🔑 Розповісти про послуги агентства
    📅 Записати на огляд або інфотур
    👤 З'єднати з менеджером
    💬 Відповісти на питання про купівлю, документи,
       ціни та життя в Болгарії

    Оберіть дію внизу або просто напишіть питання 👇

ask-prompt =
    💬 Напишіть питання — ми з радістю відповімо!

    Або оберіть популярну тему:
ask-docs = 📋 Які документи потрібні для купівлі?
ask-costs = 💰 Скільки коштує оформлення угоди?
ask-vnzh = 📋 Як отримати ВНЖ в Болгарії?
ask-installment = 💳 Які умови розстрочки?
```

**Step 4: Обновить services.yaml welcome fallback**

В `telegram_bot/config/services.yaml:130-144` — заменить `welcome.text` на новый текст
(без `{name}` т.к. yaml fallback не поддерживает Fluent-переменные).

**Step 5: Коммит**

```bash
git add telegram_bot/locales/ telegram_bot/config/services.yaml
git commit -m "feat(i18n): update welcome text and keyboard labels for 3 locales

Replace marketing welcome with personalized greeting listing bot capabilities.
Add ask-* keys for FAQ inline menu. Update kb-* labels.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Обновить cmd_start — передать name в welcome-text

**Files:**
- Modify: `telegram_bot/bot.py:731-740`

**Step 1: Написать тест**

В `tests/unit/test_bot_handlers.py` обновить `test_cmd_start_sends_reply_keyboard`:

```python
async def test_cmd_start_sends_personalized_welcome(self, mock_config):
    """Test /start sends welcome with user's first_name."""
    bot, _ = _create_bot(mock_config)
    message = _make_text_message()
    # message.from_user.first_name = "TestUser" (уже в _make_text_message)

    await bot.cmd_start(message)

    message.answer.assert_called_once()
    call_args = message.answer.call_args
    text = call_args[0][0]
    # Fallback path (no i18n) uses services.yaml welcome text
    assert "Привет" in text or "FortNoks" in text
```

**Step 2: Обновить cmd_start в bot.py**

```python
# Было (bot.py:731-740):
else:
    # Client: persistent ReplyKeyboard (#628)
    if i18n is not None:
        welcome = i18n.get("welcome-text")
    else:
        from .services.content_loader import load_services_config
        cfg = load_services_config()
        welcome = cfg.get("welcome", {}).get("text", "Добро пожаловать!")
    await message.answer(welcome, reply_markup=build_client_keyboard(i18n=i18n))

# Стало:
else:
    # Client: persistent ReplyKeyboard (#628)
    name = message.from_user.first_name or ""
    if i18n is not None:
        welcome = i18n.get("welcome-text", name=name)
    else:
        from .services.content_loader import load_services_config
        cfg = load_services_config()
        welcome = cfg.get("welcome", {}).get("text", "Добро пожаловать!")
    await message.answer(welcome, reply_markup=build_client_keyboard(i18n=i18n))
```

**Step 3: Запустить тесты**

Run: `uv run pytest tests/unit/test_bot_handlers.py::TestBotCommands::test_cmd_start_sends_reply_keyboard -v`
Expected: PASS (или обновлённый тест)

**Step 4: Коммит**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "feat(welcome): pass user name to welcome-text i18n key

Personalize /start greeting with first_name from Telegram profile.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Добавить _handle_ask handler — тест

**Files:**
- Modify: `tests/unit/test_bot_handlers.py`

**Step 1: Написать тест для _handle_ask**

```python
async def test_handle_ask_sends_inline_keyboard(self, mock_config):
    """Test 💬 Задать вопрос shows FAQ inline menu."""
    bot, _ = _create_bot(mock_config)
    message = _make_text_message(text="💬 Задать вопрос")
    state = AsyncMock()
    state.get_state.return_value = None

    await bot._handle_ask(message)

    message.answer.assert_called_once()
    call_args = message.answer.call_args
    # Проверяем что отправлен InlineKeyboard
    from aiogram.types import InlineKeyboardMarkup
    assert isinstance(call_args[1]["reply_markup"], InlineKeyboardMarkup)
```

**Step 2: Написать тест для handle_ask_callback**

```python
async def test_handle_ask_callback_triggers_query(self, mock_config):
    """Test ask:docs callback sends query to RAG pipeline."""
    bot, _ = _create_bot(mock_config)
    callback = AsyncMock()
    callback.data = "ask:docs"
    callback.message = _make_text_message()
    callback.from_user = callback.message.from_user

    await bot.handle_ask_callback(callback)

    callback.answer.assert_called_once()
    # handle_query вызывается с текстом вопроса
```

**Step 3: Запустить — убедиться что FAIL**

Run: `uv run pytest tests/unit/test_bot_handlers.py -k "test_handle_ask" -v`
Expected: FAIL — `_handle_ask` не существует

---

### Task 6: Добавить _handle_ask handler — реализация

**Files:**
- Modify: `telegram_bot/bot.py`

**Step 1: Добавить маппинг ask-вопросов и keyboard builder**

В `bot.py`, рядом с другими handler-ами (~после `_handle_promotions`):

```python
# Маппинг callback -> текст вопроса для RAG
_ASK_QUERIES: dict[str, str] = {
    "ask:docs": "Какие документы нужны для покупки?",
    "ask:costs": "Сколько стоит оформление сделки?",
    "ask:vnzh": "Как получить ВНЖ в Болгарии?",
    "ask:installment": "Какие условия рассрочки?",
}

async def _handle_ask(self, message: Message, i18n: Any = None) -> None:
    """Show FAQ inline menu with popular questions."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    if i18n is not None:
        prompt = i18n.get("ask-prompt")
        buttons = [
            [InlineKeyboardButton(text=i18n.get("ask-docs"), callback_data="ask:docs")],
            [InlineKeyboardButton(text=i18n.get("ask-costs"), callback_data="ask:costs")],
            [InlineKeyboardButton(text=i18n.get("ask-vnzh"), callback_data="ask:vnzh")],
            [InlineKeyboardButton(
                text=i18n.get("ask-installment"), callback_data="ask:installment",
            )],
        ]
    else:
        prompt = (
            "💬 Напишите вопрос — мы с радостью ответим!\n\n"
            "Или выберите популярную тему:"
        )
        buttons = [
            [InlineKeyboardButton(
                text="📋 Какие документы нужны для покупки?", callback_data="ask:docs",
            )],
            [InlineKeyboardButton(
                text="💰 Сколько стоит оформление сделки?", callback_data="ask:costs",
            )],
            [InlineKeyboardButton(
                text="📋 Как получить ВНЖ в Болгарии?", callback_data="ask:vnzh",
            )],
            [InlineKeyboardButton(
                text="💳 Какие условия рассрочки?", callback_data="ask:installment",
            )],
        ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(prompt, reply_markup=kb)

async def handle_ask_callback(self, callback: CallbackQuery) -> None:
    """Handle ask:* callback — route FAQ question to RAG pipeline."""
    await callback.answer()
    query_text = self._ASK_QUERIES.get(callback.data or "")
    if not query_text or callback.message is None:
        return
    await self.handle_menu_action_text(callback.message, query_text)
```

**Step 2: Зарегистрировать в handle_menu_button и _register_handlers**

В `handle_menu_button` (`bot.py:1060-1066`) добавить `"ask"` в handlers dict:

```python
handlers: dict[str, Any] = {
    "search": self._handle_search,
    "services": self._handle_services,
    "viewing": self._handle_viewing,
    "bookmarks": self._handle_bookmarks,
    "ask": self._handle_ask,          # NEW
    "manager": self._handle_manager,
}
```

В `_register_handlers` (`bot.py:694-697`) добавить callback handler:

```python
self.dp.callback_query(F.data.startswith("ask:"))(self.handle_ask_callback)
```

**Step 3: Убрать promotions handler из dispatch**

В `handle_menu_button` (`bot.py:1060-1066`) убрать строку:
```python
"promotions": self._handle_promotions,
```

**Step 4: Запустить тесты**

Run: `uv run pytest tests/unit/test_bot_handlers.py -k "test_handle_ask" -v`
Expected: PASS

Run: `uv run pytest tests/unit/keyboards/test_client_keyboard.py -v`
Expected: PASS

**Step 5: Коммит**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "feat(welcome): add Ask Question handler with FAQ inline menu

New _handle_ask shows InlineKeyboard with 4 popular questions.
ask:* callbacks route to RAG pipeline via handle_query.
Remove promotions from menu dispatch.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Обновить существующие тесты

**Files:**
- Modify: `tests/unit/test_bot_handlers.py`
- Modify: `tests/unit/test_bot_menu_handlers.py` (если есть ссылки на promotions)
- Modify: `tests/unit/dialogs/test_client_menu.py`

**Step 1: Найти и обновить все тесты ссылающиеся на promotions/старые тексты кнопок**

```bash
# Поиск упоминаний старых кнопок
uv run grep -rn "promotions\|Акции\|Подбор апартаментов\|Связь с менеджером" tests/unit/
```

Обновить все найденные тесты под новые тексты кнопок.

**Step 2: Запустить полный набор тестов**

Run: `uv run pytest tests/unit/ -n auto --timeout=30 -m "not legacy_api" -q`
Expected: PASS

**Step 3: Коммит**

```bash
git add tests/
git commit -m "test(welcome): update existing tests for new keyboard layout

Replace promotions references with ask, update button texts.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 8: Lint + type check + финальная верификация

**Files:** Все изменённые

**Step 1: Lint и форматирование**

Run: `make check`
Expected: PASS (ruff + mypy)

**Step 2: Полный прогон unit-тестов**

Run: `uv run pytest tests/unit/ -n auto --timeout=30 -m "not legacy_api" -q`
Expected: ALL PASS

**Step 3: Если есть ошибки — фиксить итеративно**

**Step 4: Финальный коммит (если были фиксы)**

```bash
git add -u
git commit -m "fix(welcome): lint and type fixes

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Порядок выполнения

```
Task 1 (тесты keyboard)
  → Task 2 (реализация keyboard)  → commit
    → Task 3 (i18n .ftl)          → commit
      → Task 4 (cmd_start name)   → commit
        → Task 5 (тесты ask)
          → Task 6 (реализация ask) → commit
            → Task 7 (обновить существующие тесты) → commit
              → Task 8 (lint + verify) → commit
```

8 задач, ~5 коммитов, линейная зависимость.
