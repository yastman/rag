# Expert Topics in Private Chat — Design

**Дата:** 2026-03-09
**Статус:** Draft
**Задача:** Разделение общения по экспертам через forum topics в приватном чате бота

## Контекст

Бот Mira показал паттерн: Mini App → выбор эксперта/промпта → ответ в общий чат + создаётся тред с осмысленным названием. Пользователь может продолжить общение в треде.

Наш бот: 5 экспертов в Mini App (`mini_app.yaml`), но `expert_id` теряется в pipeline, system prompts определены но не применяются, чат stateless.

## Решение — Подход C: "Full Native"

Mini App = лобби для выбора эксперта. Весь чат — в нативных Telegram-тредах с `sendMessageDraft` стримингом.

### Флоу

```
1. Пользователь открывает Mini App → выбирает эксперта → кликает промпт
2. Mini App: Telegram.WebApp.sendData({expert_id, message}) → закрывается
3. Бот получает web_app_data в handler (bot.py:4144)
4. Бот создаёт ForumTopic: createForumTopic(chat_id=user_id, name="👷 Консультант")
5. Бот стримит ответ через sendMessageDraft(message_thread_id=topic_id)
6. Бот переименовывает тред по теме: editForumTopic(name="🏠 Двушка в Бургасе")
7. Дальнейшие сообщения в треде → тот же expert pipeline с историей
```

### Диаграмма

```
┌──────────────┐     web_app_data      ┌─────────────┐
│   Mini App   │ ──────────────────►   │   bot.py    │
│  (лобби)     │  {expert_id, msg}     │  handler    │
└──────────────┘                       └──────┬──────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
                   createForumTopic    sendMessageDraft     editForumTopic
                   ("👷 Консультант")  (stream в тред)     ("🏠 Тема...")
                          │                   │
                          ▼                   ▼
                   ┌─────────────┐    ┌──────────────┐
                   │ Redis store │    │ RAG pipeline  │
                   │ topic_map   │    │ + expert      │
                   │ user→expert │    │   system      │
                   │ →thread_id  │    │   prompt      │
                   └─────────────┘    └──────────────┘
```

## Компоненты

### 1. TopicManager (новый сервис)

Управляет связкой user_id ↔ expert_id ↔ message_thread_id.

```python
class TopicManager:
    """Управление forum topics для экспертов в приватных чатах."""

    def __init__(self, bot: Bot, redis: Redis):
        self._bot = bot
        self._redis = redis

    async def get_or_create_topic(
        self, chat_id: int, expert_id: str, expert_name: str, expert_emoji: str
    ) -> int:
        """Вернуть существующий topic_id или создать новый."""
        key = f"topic:{chat_id}:{expert_id}"
        topic_id = await self._redis.get(key)
        if topic_id:
            return int(topic_id)

        topic = await self._bot.create_forum_topic(
            chat_id=chat_id,
            name=f"{expert_emoji} {expert_name}",
        )
        await self._redis.set(key, topic.message_thread_id, ex=30 * 86400)  # 30 дней
        return topic.message_thread_id

    async def rename_topic(
        self, chat_id: int, topic_id: int, new_name: str
    ) -> None:
        """Переименовать тред по теме разговора."""
        await self._bot.edit_forum_topic(
            chat_id=chat_id,
            message_thread_id=topic_id,
            name=new_name[:128],
        )

    async def get_expert_for_topic(
        self, chat_id: int, topic_id: int
    ) -> str | None:
        """Обратный lookup: по topic_id найти expert_id."""
        # Scan Redis keys topic:{chat_id}:* или хранить reverse map
        ...
```

**Хранение в Redis:**
- `topic:{chat_id}:{expert_id}` → `message_thread_id` (TTL 30 дней)
- `topic_expert:{chat_id}:{message_thread_id}` → `expert_id` (reverse lookup)

### 2. Mini App изменения

**Frontend (`ExpertSheet.tsx`, `QuestionSheet.tsx`):**

Текущий флоу: клик → navigate(`/chat?message=...&expert_id=...`) → ChatPage (SSE чат внутри Mini App).

Новый флоу: клик → `Telegram.WebApp.sendData(JSON)` → Mini App закрывается.

```typescript
// ExpertSheet.tsx
const handlePrompt = (text: string) => {
  const payload = JSON.stringify({
    type: "expert_chat",
    expert_id: id,
    message: text,
  });
  window.Telegram.WebApp.sendData(payload);
  // Mini App закрывается автоматически после sendData
};
```

**ChatPage** — остаётся как fallback для inline-чата (если topics не включены).

### 3. WebAppData handler (bot.py)

Расширить существующий handler в `bot.py:4144`:

```python
async def handle_web_app_data(self, message: Message) -> None:
    data = json.loads(message.web_app_data.data)

    if data.get("type") == "expert_chat":
        expert_id = data["expert_id"]
        user_message = data["message"]
        expert_config = self._get_expert_config(expert_id)

        # 1. Создать/получить тред
        topic_id = await self.topic_manager.get_or_create_topic(
            chat_id=message.chat.id,
            expert_id=expert_id,
            expert_name=expert_config.name,
            expert_emoji=expert_config.emoji,
        )

        # 2. Цитировать вопрос в треде
        await self.bot.send_message(
            chat_id=message.chat.id,
            message_thread_id=topic_id,
            text=f"❝ {user_message} ❞",
        )

        # 3. Стримить ответ через sendMessageDraft
        draft_id = random.randint(1, 2**31)
        response = await self._generate_expert_response(
            message=user_message,
            expert_id=expert_id,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            topic_id=topic_id,
            draft_id=draft_id,
        )

        # 4. Финализировать ответ
        await self.bot.send_message(
            chat_id=message.chat.id,
            message_thread_id=topic_id,
            text=response,
        )

        # 5. Переименовать тред по теме (опционально, через LLM)
        topic_name = await self._generate_topic_name(user_message, response)
        if topic_name:
            await self.topic_manager.rename_topic(
                chat_id=message.chat.id,
                topic_id=topic_id,
                new_name=f"{expert_config.emoji} {topic_name}",
            )
```

### 4. Thread-aware message routing

Когда пользователь пишет в треде (не через Mini App), бот должен определить эксперта:

```python
# В handle_query или отдельный handler
async def handle_topic_message(self, message: Message) -> None:
    if not message.is_topic_message or not message.message_thread_id:
        return  # не тред — обычный pipeline

    expert_id = await self.topic_manager.get_expert_for_topic(
        chat_id=message.chat.id,
        topic_id=message.message_thread_id,
    )

    if expert_id:
        # Pipeline с expert system prompt
        await self._generate_expert_response(
            message=message.text,
            expert_id=expert_id,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            topic_id=message.message_thread_id,
            draft_id=random.randint(1, 2**31),
        )
```

### 5. Expert System Prompt Pipeline

Подключить `system_prompt_key` из `mini_app.yaml` к RAG pipeline:

```python
async def _generate_expert_response(self, *, expert_id, message, user_id, chat_id, topic_id, draft_id):
    expert = self._get_expert_config(expert_id)

    # Получить system prompt из Langfuse или fallback
    system_prompt = get_prompt(
        name=expert.system_prompt_key,  # "expert-consultant"
        fallback=f"Ты {expert.name}. {expert.description}.",
    )

    # RAG pipeline с expert persona
    result = await rag_pipeline(
        query=message,
        user_id=user_id,
        session_id=f"topic_{chat_id}_{topic_id}",
        system_prompt_override=system_prompt,
        # ... остальные параметры
    )

    # Стриминг через sendMessageDraft
    response = result["response"]
    accumulated = ""
    for i in range(0, len(response), 20):
        accumulated += response[i:i+20]
        await self.bot.send_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            text=accumulated,
            message_thread_id=topic_id,
        )
        await asyncio.sleep(0.2)

    return response
```

### 6. Conversation History per Topic

Thread ID как ключ для изоляции истории:

- **Redis checkpointer:** `thread_id = f"topic_{chat_id}_{message_thread_id}"`
- **Qdrant history:** `metadata.session_id = f"topic_{chat_id}_{topic_id}"`
- Каждый тред = отдельный контекст, не смешивается с другими экспертами

## Предусловия

### BotFather настройка
1. Открыть @BotFather → выбрать бота
2. Включить "Topics in Private Chats" / Threaded Mode
3. Настроить `allows_users_to_create_topics` (true/false — решить)
4. Проверить: `getMe` → `has_topics_enabled: true`

### Конфиг
```yaml
# .env
EXPERT_TOPICS_ENABLED=true  # feature flag для постепенного rollout
```

## Существующая инфраструктура (переиспользование)

| Компонент | Файл | Что переиспользуем |
|-----------|------|--------------------|
| `ForumBridge` | `services/forum_bridge.py` | Логика create/send/close topic (расширить для private chats) |
| `sendMessageDraft` | `services/generate_response.py` | Стриминг — уже работает, добавить `message_thread_id` |
| `WebAppData handler` | `bot.py:4144` | Уже обрабатывает Mini App данные |
| `prompt_manager` | `integrations/prompt_manager.py` | Langfuse prompt fetch по `system_prompt_key` |
| `mini_app.yaml` | `config/mini_app.yaml` | 5 экспертов с emoji, name, system_prompt_key |
| `Redis` | existing | Хранение topic_map |
| `Qdrant history` | `services/history_service.py` | Per-topic conversation history |

## Что НЕ меняем

- Общий чат (All) продолжает работать как раньше для обычных сообщений
- Menu keyboard, FSM dialogs, CRM callbacks — без изменений
- Voice pipeline — без изменений (пока)
- Mini App ChatPage — оставляем как fallback

## Edge Cases

| Кейс | Решение |
|------|---------|
| `has_topics_enabled` = false | Fallback на текущий флоу (чат в Mini App) |
| Тред удалён пользователем | `send_to_topic` поймает ошибку → создать новый |
| Пользователь пишет в общий чат (All) | Обычный pipeline без expert persona |
| Тот же эксперт, новая тема | Один тред на эксперта (reuse), или опция "Новый диалог" |
| Rate limit на createForumTopic | Redis кеш topic_id, создаём только при первом обращении |

## Метрики успеха

- Пользователи используют треды (% сообщений в тредах vs общий чат)
- Среднее кол-во сообщений в треде (engagement)
- Expert system prompt улучшает качество ответов (Langfuse scores)
- Latency стриминга через sendMessageDraft vs текущий SSE в Mini App

## Зависимости

- aiogram >= 3.25.0 ✅ (уже установлен)
- Bot API 9.5 ✅ (sendMessageDraft для всех ботов, март 2026)
- BotFather: включить topics в приватных чатах
- Langfuse: создать промпты `expert-consultant`, `expert-vnzh` и т.д.

## Источники

- [Telegram Bot API — createForumTopic](https://core.telegram.org/bots/api#createforumtopic)
- [Telegram Bot API — sendMessageDraft](https://core.telegram.org/bots/api#sendmessagedraft)
- [Bot API 9.5 — sendMessageDraft for all bots](https://news.aibase.com/news/25881)
- [aiogram createForumTopic docs](https://docs.aiogram.dev/en/dev-3.x/api/methods/create_forum_topic.html)
- [aiogram sendMessageDraft docs](https://docs.aiogram.dev/en/dev-3.x/api/methods/send_message_draft.html)
- [Bot API Changelog](https://core.telegram.org/bots/api-changelog)
