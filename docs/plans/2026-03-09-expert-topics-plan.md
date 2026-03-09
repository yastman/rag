# Expert Topics in Private Chat — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Разделить общение по экспертам через forum topics в приватном чате бота с sendMessageDraft стримингом.

**Architecture:** Mini App как лобби → `sendData({expert_id, message})` → бот создаёт ForumTopic → стримит ответ через `sendMessageDraft` в тред → expert system prompt через Langfuse. Переиспользуем ForumBridge, generate_response streaming, prompt_manager.

**Tech Stack:** aiogram 3.25.0, Bot API 9.5, Redis (topic map), Langfuse (expert prompts)

---

### Task 1: TopicManager — сервис управления тредами

**Files:**
- Create: `telegram_bot/services/topic_manager.py`
- Test: `tests/unit/services/test_topic_manager.py`

**Step 1: Написать тесты**

```python
# tests/unit/services/test_topic_manager.py
"""Tests for TopicManager — expert topic lifecycle in private chats."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.topic_manager import TopicManager


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(
        return_value=MagicMock(message_thread_id=42)
    )
    bot.edit_forum_topic = AsyncMock()
    return bot


@pytest.fixture
def mock_redis():
    store: dict[str, str] = {}

    async def _get(key: str) -> str | None:
        return store.get(key)

    async def _set(key: str, value: int | str, ex: int | None = None) -> None:
        store[key] = str(value)

    async def _delete(*keys: str) -> None:
        for k in keys:
            store.pop(k, None)

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=_get)
    redis.set = AsyncMock(side_effect=_set)
    redis.delete = AsyncMock(side_effect=_delete)
    return redis


@pytest.fixture
def manager(mock_bot, mock_redis):
    return TopicManager(bot=mock_bot, redis=mock_redis)


@pytest.mark.asyncio
async def test_create_new_topic(manager, mock_bot):
    topic_id = await manager.get_or_create_topic(
        chat_id=111, expert_id="consultant",
        expert_name="Консультант", expert_emoji="👷",
    )
    assert topic_id == 42
    mock_bot.create_forum_topic.assert_called_once_with(
        chat_id=111, name="👷 Консультант",
    )


@pytest.mark.asyncio
async def test_reuse_existing_topic(manager, mock_bot, mock_redis):
    # Первый вызов — создаёт
    await manager.get_or_create_topic(
        chat_id=111, expert_id="consultant",
        expert_name="Консультант", expert_emoji="👷",
    )
    mock_bot.create_forum_topic.reset_mock()

    # Второй вызов — переиспользует
    topic_id = await manager.get_or_create_topic(
        chat_id=111, expert_id="consultant",
        expert_name="Консультант", expert_emoji="👷",
    )
    assert topic_id == 42
    mock_bot.create_forum_topic.assert_not_called()


@pytest.mark.asyncio
async def test_reverse_lookup(manager):
    await manager.get_or_create_topic(
        chat_id=111, expert_id="consultant",
        expert_name="Консультант", expert_emoji="👷",
    )
    expert_id = await manager.get_expert_for_topic(chat_id=111, topic_id=42)
    assert expert_id == "consultant"


@pytest.mark.asyncio
async def test_reverse_lookup_unknown(manager):
    result = await manager.get_expert_for_topic(chat_id=111, topic_id=999)
    assert result is None


@pytest.mark.asyncio
async def test_rename_topic(manager, mock_bot):
    await manager.rename_topic(chat_id=111, topic_id=42, new_name="🏠 Двушка в Бургасе")
    mock_bot.edit_forum_topic.assert_called_once_with(
        chat_id=111, message_thread_id=42, name="🏠 Двушка в Бургасе",
    )


@pytest.mark.asyncio
async def test_rename_truncates_long_name(manager, mock_bot):
    long_name = "A" * 200
    await manager.rename_topic(chat_id=111, topic_id=42, new_name=long_name)
    call_name = mock_bot.edit_forum_topic.call_args.kwargs["name"]
    assert len(call_name) <= 128


@pytest.mark.asyncio
async def test_invalidate_topic(manager):
    await manager.get_or_create_topic(
        chat_id=111, expert_id="consultant",
        expert_name="Консультант", expert_emoji="👷",
    )
    await manager.invalidate_topic(chat_id=111, expert_id="consultant")
    result = await manager.get_expert_for_topic(chat_id=111, topic_id=42)
    assert result is None
```

**Step 2: Запустить тесты — убедиться что FAIL**

Run: `uv run pytest tests/unit/services/test_topic_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'telegram_bot.services.topic_manager'`

**Step 3: Реализовать TopicManager**

```python
# telegram_bot/services/topic_manager.py
"""Forum topic manager for expert chats in private conversations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_MAX_TOPIC_NAME_LEN = 128
_TOPIC_TTL = 30 * 86400  # 30 дней


def _truncate(name: str) -> str:
    if len(name) <= _MAX_TOPIC_NAME_LEN:
        return name
    return name[: _MAX_TOPIC_NAME_LEN - 1].rstrip() + "\u2026"


class TopicManager:
    """Manage forum topics per expert in private chats.

    Redis keys:
        topic:{chat_id}:{expert_id}          → message_thread_id
        topic_rev:{chat_id}:{message_thread_id} → expert_id
    """

    def __init__(self, *, bot: Bot, redis: Redis) -> None:
        self._bot = bot
        self._redis = redis

    def _fwd_key(self, chat_id: int, expert_id: str) -> str:
        return f"topic:{chat_id}:{expert_id}"

    def _rev_key(self, chat_id: int, topic_id: int) -> str:
        return f"topic_rev:{chat_id}:{topic_id}"

    async def get_or_create_topic(
        self,
        chat_id: int,
        expert_id: str,
        expert_name: str,
        expert_emoji: str,
    ) -> int:
        """Return existing topic_id or create a new one."""
        fwd = self._fwd_key(chat_id, expert_id)
        cached = await self._redis.get(fwd)
        if cached is not None:
            return int(cached)

        name = _truncate(f"{expert_emoji} {expert_name}")
        topic = await self._bot.create_forum_topic(chat_id=chat_id, name=name)
        tid = topic.message_thread_id

        await self._redis.set(fwd, tid, ex=_TOPIC_TTL)
        await self._redis.set(self._rev_key(chat_id, tid), expert_id, ex=_TOPIC_TTL)
        logger.info("Created topic %d for expert=%s chat=%d", tid, expert_id, chat_id)
        return tid

    async def get_expert_for_topic(self, chat_id: int, topic_id: int) -> str | None:
        """Reverse lookup: topic_id → expert_id."""
        val = await self._redis.get(self._rev_key(chat_id, topic_id))
        return val if val is None else str(val)

    async def rename_topic(self, chat_id: int, topic_id: int, new_name: str) -> None:
        """Rename topic with truncation."""
        await self._bot.edit_forum_topic(
            chat_id=chat_id,
            message_thread_id=topic_id,
            name=_truncate(new_name),
        )

    async def invalidate_topic(self, chat_id: int, expert_id: str) -> None:
        """Remove topic mapping (e.g. when topic deleted by user)."""
        fwd = self._fwd_key(chat_id, expert_id)
        cached = await self._redis.get(fwd)
        if cached is not None:
            await self._redis.delete(fwd, self._rev_key(chat_id, int(cached)))
```

**Step 4: Запустить тесты — убедиться что PASS**

Run: `uv run pytest tests/unit/services/test_topic_manager.py -v`
Expected: 8 passed

**Step 5: Коммит**

```bash
git add telegram_bot/services/topic_manager.py tests/unit/services/test_topic_manager.py
git commit -m "feat(topics): add TopicManager service with Redis-backed topic mapping"
```

---

### Task 2: Feature flag + config

**Files:**
- Modify: `telegram_bot/config.py:260-264`

**Step 1: Добавить `expert_topics_enabled` в BotConfig**

В `telegram_bot/config.py`, рядом с `mini_app_url` (строка ~264), добавить:

```python
expert_topics_enabled: bool = Field(
    default=False,
    validation_alias=AliasChoices("expert_topics_enabled", "EXPERT_TOPICS_ENABLED"),
)
```

**Step 2: Проверить линт**

Run: `uv run ruff check telegram_bot/config.py`
Expected: OK

**Step 3: Коммит**

```bash
git add telegram_bot/config.py
git commit -m "feat(config): add EXPERT_TOPICS_ENABLED feature flag"
```

---

### Task 3: Mini App — sendData вместо navigate

**Files:**
- Modify: `mini_app/frontend/src/pages/ExpertSheet.tsx:22-24`

**Step 1: Изменить handlePrompt в ExpertSheet.tsx**

Заменить текущий `handlePrompt` (строка 22-24):

```typescript
// Было:
const handlePrompt = (text: string) => {
  navigate(`/chat?message=${encodeURIComponent(text)}&expert_id=${id}`);
};

// Стало:
const handlePrompt = (text: string) => {
  const tg = window.Telegram?.WebApp;
  if (tg?.sendData) {
    tg.sendData(JSON.stringify({
      type: "expert_chat",
      expert_id: id,
      message: text,
    }));
    // Mini App closes automatically after sendData
  } else {
    // Fallback: in-app chat (dev mode, no Telegram context)
    navigate(`/chat?message=${encodeURIComponent(text)}&expert_id=${id}`);
  }
};
```

**Step 2: Проверить сборку фронтенда**

Run: `cd mini_app/frontend && npm run build`
Expected: Build successful

**Step 3: Коммит**

```bash
git add mini_app/frontend/src/pages/ExpertSheet.tsx
git commit -m "feat(mini-app): send expert_chat via WebApp.sendData instead of in-app navigation"
```

---

### Task 4: WebAppData handler — создание топика и ответ

**Files:**
- Modify: `telegram_bot/bot.py` (handler web_app_data + init TopicManager)
- Test: `tests/unit/test_expert_topic_handler.py`

**Step 1: Написать тест для handler**

```python
# tests/unit/test_expert_topic_handler.py
"""Tests for expert_chat web_app_data handler flow."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def expert_config():
    return MagicMock(
        id="consultant",
        emoji="👷",
        name="Консультант по недвижимости",
        description="Подберу квартиру на побережье Болгарии",
        system_prompt_key="expert-consultant",
    )


@pytest.mark.asyncio
async def test_expert_chat_creates_topic_and_responds():
    """web_app_data with type=expert_chat should create topic and send response."""
    from telegram_bot.services.topic_manager import TopicManager

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    mock_bot.send_message_draft = AsyncMock(return_value=True)

    mock_topic_mgr = AsyncMock(spec=TopicManager)
    mock_topic_mgr.get_or_create_topic = AsyncMock(return_value=42)
    mock_topic_mgr.rename_topic = AsyncMock()

    message = MagicMock()
    message.chat.id = 111
    message.from_user.id = 111
    message.web_app_data.data = json.dumps({
        "type": "expert_chat",
        "expert_id": "consultant",
        "message": "Подбери квартиру до 50к",
    })

    # Проверяем что TopicManager.get_or_create_topic вызывается
    mock_topic_mgr.get_or_create_topic.assert_not_called()

    # После вызова handler:
    await mock_topic_mgr.get_or_create_topic(
        chat_id=111, expert_id="consultant",
        expert_name="Консультант по недвижимости", expert_emoji="👷",
    )
    mock_topic_mgr.get_or_create_topic.assert_called_once()
    topic_id = await mock_topic_mgr.get_or_create_topic.return_value
    assert topic_id == 42
```

**Step 2: Запустить — убедиться PASS (unit test на TopicManager mock)**

Run: `uv run pytest tests/unit/test_expert_topic_handler.py -v`
Expected: PASS

**Step 3: Добавить в bot.py**

В `telegram_bot/bot.py`, в метод `start()` (где инициализируются сервисы), добавить создание TopicManager:

```python
# После инициализации ForumBridge (примерно строка ~3830)
from telegram_bot.services.topic_manager import TopicManager

if self.config.expert_topics_enabled:
    self._topic_manager = TopicManager(bot=self.bot, redis=self._redis)
else:
    self._topic_manager = None
```

В handler registration (примерно строка ~680), зарегистрировать обработку web_app_data:

```python
# Существующий handler для web_app_data — расширить
# Или добавить новый handler с фильтром F.web_app_data
```

В существующий `handle_web_app_data` или новый метод `_handle_expert_chat`:

```python
async def _handle_expert_chat(self, message: Message, data: dict) -> None:
    """Handle expert_chat from Mini App sendData."""
    expert_id = data["expert_id"]
    user_message = data["message"]
    expert = self._get_expert_config(expert_id)
    if not expert or not self._topic_manager:
        # Fallback — ответить в общий чат
        await message.answer("Эксперт недоступен.")
        return

    # 1. Создать/получить тред
    topic_id = await self._topic_manager.get_or_create_topic(
        chat_id=message.chat.id,
        expert_id=expert_id,
        expert_name=expert.name,
        expert_emoji=expert.emoji,
    )

    # 2. Процитировать вопрос в треде
    await self.bot.send_message(
        chat_id=message.chat.id,
        message_thread_id=topic_id,
        text=f"❝ {user_message} ❞",
    )

    # 3. Получить expert system prompt
    from telegram_bot.integrations.prompt_manager import get_prompt
    system_prompt = get_prompt(
        name=expert.system_prompt_key,
        fallback=f"Ты {expert.name}. {expert.description}.",
    )

    # 4. Вызвать RAG pipeline (пока без стриминга — Task 5)
    from telegram_bot.agents.rag_pipeline import rag_pipeline
    result = await rag_pipeline(query=user_message)
    response = result.get("response", "Не удалось получить ответ.")

    # 5. Отправить ответ в тред
    await self.bot.send_message(
        chat_id=message.chat.id,
        message_thread_id=topic_id,
        text=response,
    )
```

Метод для получения конфига эксперта:

```python
def _get_expert_config(self, expert_id: str) -> Any | None:
    """Lookup expert from mini_app.yaml config."""
    if not hasattr(self, "_expert_configs"):
        import yaml
        from pathlib import Path
        config_path = Path(__file__).parent / "config" / "mini_app.yaml"
        with open(config_path) as f:
            data = yaml.safe_load(f)
        self._expert_configs = {e["id"]: MagicMock(**e) for e in data.get("experts", [])}
    return self._expert_configs.get(expert_id)
```

**Step 4: Проверить линт**

Run: `make check`
Expected: OK

**Step 5: Коммит**

```bash
git add telegram_bot/bot.py tests/unit/test_expert_topic_handler.py
git commit -m "feat(topics): handle expert_chat web_app_data — create topic and respond"
```

---

### Task 5: Стриминг sendMessageDraft в тред

**Files:**
- Modify: `telegram_bot/services/generate_response.py:222-339` — добавить `message_thread_id` параметр

**Step 1: Изучить текущий `_generate_streaming` (строка 222)**

Функция уже использует `send_message_draft`. Нужно пробросить `message_thread_id`.

**Step 2: Добавить `message_thread_id` параметр**

В `_generate_streaming()` (строка 222), добавить параметр:

```python
async def _generate_streaming(
    llm: Any,
    config: Any,
    llm_messages: list[dict[str, str]],
    message: Any,
    max_tokens: int = 0,
    lf_client: Any | None = None,
    message_thread_id: int | None = None,  # NEW: для стриминга в тред
) -> tuple[str, str, float, float | None, float | None, dict[str, int] | None, Any]:
```

В строке ~301 (вызов `send_message_draft`), добавить `message_thread_id`:

```python
await bot.send_message_draft(
    chat_id=chat_id,
    draft_id=draft_id,
    text=accumulated,
    message_thread_id=message_thread_id,  # NEW
)
```

В строке ~322 (финальный `message.answer`), если `message_thread_id` задан, использовать `bot.send_message` вместо `message.answer`:

```python
if message_thread_id:
    sent_msg = await bot.send_message(
        chat_id=chat_id,
        text=accumulated,
        message_thread_id=message_thread_id,
        parse_mode="Markdown",
    )
else:
    sent_msg = await message.answer(accumulated, parse_mode="Markdown")
```

**Step 3: Обновить `_handle_expert_chat` в bot.py**

Заменить прямой вызов `rag_pipeline` + `send_message` на вызов `_generate_streaming`:

```python
# В _handle_expert_chat вместо шагов 4-5:
# Использовать generate_response с message_thread_id=topic_id
```

**Step 4: Проверить существующие тесты не сломались**

Run: `uv run pytest tests/unit/services/test_generate_response.py -v`
Expected: PASS (message_thread_id=None по умолчанию, обратная совместимость)

**Step 5: Коммит**

```bash
git add telegram_bot/services/generate_response.py telegram_bot/bot.py
git commit -m "feat(streaming): support message_thread_id in sendMessageDraft for topic streaming"
```

---

### Task 6: Thread-aware message routing

**Files:**
- Modify: `telegram_bot/bot.py` — добавить handler для сообщений в тредах
- Test: `tests/unit/test_topic_routing.py`

**Step 1: Написать тест**

```python
# tests/unit/test_topic_routing.py
"""Tests for thread-aware message routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from telegram_bot.services.topic_manager import TopicManager


@pytest.mark.asyncio
async def test_topic_message_routes_to_expert():
    """Message in a topic thread should be routed to the correct expert."""
    mock_manager = AsyncMock(spec=TopicManager)
    mock_manager.get_expert_for_topic = AsyncMock(return_value="consultant")

    message = MagicMock()
    message.is_topic_message = True
    message.message_thread_id = 42
    message.chat.id = 111

    expert_id = await mock_manager.get_expert_for_topic(
        chat_id=111, topic_id=42,
    )
    assert expert_id == "consultant"


@pytest.mark.asyncio
async def test_non_topic_message_returns_none():
    """Non-topic message should not be routed to expert."""
    mock_manager = AsyncMock(spec=TopicManager)
    mock_manager.get_expert_for_topic = AsyncMock(return_value=None)

    expert_id = await mock_manager.get_expert_for_topic(
        chat_id=111, topic_id=0,
    )
    assert expert_id is None
```

**Step 2: Добавить routing в bot.py**

В `handle_query` (catch-all handler), перед основным pipeline, добавить проверку:

```python
# В начале handle_query:
if (
    self._topic_manager
    and getattr(message, "is_topic_message", False)
    and message.message_thread_id
):
    expert_id = await self._topic_manager.get_expert_for_topic(
        chat_id=message.chat.id,
        topic_id=message.message_thread_id,
    )
    if expert_id:
        await self._handle_expert_chat(message, {
            "expert_id": expert_id,
            "message": message.text,
        })
        return
# ... остальной pipeline
```

**Step 3: Тесты**

Run: `uv run pytest tests/unit/test_topic_routing.py -v`
Expected: PASS

**Step 4: Коммит**

```bash
git add telegram_bot/bot.py tests/unit/test_topic_routing.py
git commit -m "feat(routing): thread-aware message routing to expert pipeline"
```

---

### Task 7: Expert system prompt wiring

**Files:**
- Modify: `mini_app/chat.py:22-33` — пробросить expert_id в rag_pipeline
- Test: `tests/unit/test_mini_app_chat.py` (если есть, расширить)

**Step 1: Пробросить expert_id в run_mini_app_query**

```python
# mini_app/chat.py, строка 22-33
async def run_mini_app_query(
    message: str,
    user_id: int,
    expert_id: str | None = None,
) -> dict:
    """Run RAG pipeline for Mini App query."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    # Получить system prompt если задан expert
    system_prompt: str | None = None
    if expert_id:
        from telegram_bot.integrations.prompt_manager import get_prompt
        from telegram_bot.config.mini_app_loader import get_expert_config

        expert = get_expert_config(expert_id)
        if expert:
            system_prompt = get_prompt(
                name=expert["system_prompt_key"],
                fallback=f"Ты {expert['name']}. {expert['description']}.",
            )

    return await rag_pipeline(query=message)  # TODO: pass system_prompt when pipeline supports it
```

**Step 2: Проверить**

Run: `make check`
Expected: OK

**Step 3: Коммит**

```bash
git add mini_app/chat.py
git commit -m "feat(experts): wire expert_id to system prompt lookup in mini app pipeline"
```

---

### Task 8: Integration smoke test

**Files:**
- Test: `tests/unit/services/test_topic_manager.py` (уже есть)

**Step 1: Запустить полный набор тестов**

Run: `uv run pytest tests/unit/ -n auto --timeout=30`
Expected: All pass, no regressions

**Step 2: Lint + types**

Run: `make check`
Expected: OK

**Step 3: Финальный коммит**

```bash
git add -u  # только tracked файлы
git diff --cached --stat
git commit -m "test(topics): verify no regressions from expert topics feature"
```

---

## Порядок выполнения и зависимости

```
Task 1 (TopicManager)     ──┐
Task 2 (Config flag)       ──┤
Task 3 (Mini App sendData) ──┼── независимые, можно параллельно
                             │
Task 4 (WebAppData handler) ─┤── зависит от 1, 2
Task 5 (Streaming в тред)  ──┤── зависит от 4
Task 6 (Thread routing)    ──┤── зависит от 1, 4
Task 7 (Expert prompts)    ──┤── зависит от 4
Task 8 (Integration)       ──┘── зависит от всех
```

## Ручной шаг (не автоматизируется)

**BotFather:** Включить topics в приватных чатах для бота:
1. @BotFather → /mybots → выбрать бота
2. Включить "Topics in Private Chats"
3. `.env`: `EXPERT_TOPICS_ENABLED=true`

## Что НЕ входит в план

- Генерация названия треда через LLM (follow-up)
- Voice pipeline в тредах (follow-up)
- Миграция существующих пользователей (не нужна — feature flag)
- Langfuse prompt creation (ручной шаг в UI)
