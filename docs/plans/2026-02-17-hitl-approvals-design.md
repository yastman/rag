# HITL Approval Flows — Design Document

**Issue:** #228 — `feat(bot): Human-in-the-Loop — approval flows for critical agent operations`
**Date:** 2026-02-17
**Status:** Research / Design

---

## 1. Контекст

### Проблема

Все операции бота выполняются автоматически — нет возможности запросить подтверждение пользователя перед необратимыми действиями.

### Цель

Определить, какие операции требуют подтверждения, и реализовать механизм паузы → подтверждения → продолжения через LangGraph `interrupt()` + Telegram inline keyboard.

### Правило HITL (из video notes)

> HITL нужен, если операция **необратима** или имеет **высокие последствия**.

---

## 2. LangGraph `interrupt()` — механизм

### 2.1 Как работает

```python
from langgraph.types import interrupt, Command

def approval_node(state: State):
    # 1. Пауза — граф останавливается, состояние сохраняется в checkpointer
    is_approved = interrupt({
        "question": "Подтвердить действие?",
        "details": state["action_details"],
    })
    # 2. Возобновление — resume value становится return value interrupt()
    if is_approved:
        return {"approved": True}
    return Command(goto="cancel")  # маршрутизация при отказе
```

### 2.2 Возобновление

```python
# Пользователь нажал "Подтвердить" → callback_query → resume graph
config = {"configurable": {"thread_id": thread_id}}
result = await graph.ainvoke(Command(resume=True), config)
```

### 2.3 Ключевые правила `interrupt()`

| Правило | Описание |
|---------|----------|
| **Checkpointer обязателен** | `interrupt()` работает ТОЛЬКО с persistence layer |
| **JSON-serializable payload** | Значение `interrupt(value)` должно быть сериализуемо |
| **Node restarts fully** | При resume нода перезапускается с начала, interrupt() возвращает resume value |
| **Idempotent side effects** | Код ДО interrupt() выполнится повторно — side effects должны быть идемпотентны |
| **Multiple interrupts** | Можно иметь несколько interrupt() в одной ноде (sequential) |

### 2.4 Отличие от старого API

| Старый | Новый | Рекомендация |
|--------|-------|-------------|
| `interrupt_before=["node"]` | `interrupt()` внутри ноды | ✅ Новый — гибче, conditional |
| `interrupt_after=["node"]` | `interrupt()` внутри ноды | ✅ Новый — rich payload |
| `NodeInterrupt` exception | `interrupt()` function | ✅ Новый — проще |

---

## 3. Текущая инфраструктура бота (готовность к HITL)

### 3.1 Checkpointer ✅ УЖЕ ЕСТЬ

```python
# telegram_bot/bot.py:1032-1045
self._checkpointer = create_redis_checkpointer(redis_url=...)
await self._checkpointer.asetup()
# Fallback: create_fallback_checkpointer() → MemorySaver()
```

```python
# telegram_bot/graph/graph.py:201-207
if checkpointer is not None:
    ...
return workflow.compile(checkpointer=checkpointer)
```

**Вывод:** Redis checkpointer уже подключен — `interrupt()` будет работать из коробки.

### 3.2 Inline Keyboard + CallbackQuery ✅ УЖЕ ЕСТЬ

```python
# telegram_bot/feedback.py — паттерн для feedback кнопок
InlineKeyboardButton(text="👍", callback_data="fb:1:{trace_id}")
InlineKeyboardButton(text="👎", callback_data="fb:0:{trace_id}")

# telegram_bot/bot.py:387
self.dp.callback_query(F.data.startswith("fb:"))(self.handle_feedback)
```

**Вывод:** Тот же паттерн используется для approval кнопок.

### 3.3 Thread ID ✅ УЖЕ ЕСТЬ

Каждый пользователь имеет `thread_id` (= `user_id`) для checkpointer. Interrupt state будет персиститься в Redis per-user.

---

## 4. Архитектура HITL для Telegram бота

### 4.1 Поток данных

```
User Query → [classify → ... → generate] → approval_node
                                                │
                                          interrupt()
                                                │
                                     ┌──────────▼──────────┐
                                     │  Telegram Message:   │
                                     │  "Создать запись?"   │
                                     │  [✅ Подтвердить]    │
                                     │  [❌ Отменить]       │
                                     └──────────┬──────────┘
                                                │
                                     User clicks button
                                                │
                                     CallbackQuery handler
                                                │
                                     graph.ainvoke(Command(resume=True/False))
                                                │
                                     ┌──────────▼──────────┐
                                     │  execute_tool_node   │
                                     │  (или cancel_node)   │
                                     └─────────────────────┘
```

### 4.2 Компоненты

```
telegram_bot/
├── approval.py              # NEW: build_approval_keyboard(), parse_approval_callback()
├── bot.py                   # MODIFY: handle_approval() callback handler
└── graph/
    └── nodes/
        └── approval.py      # NEW: approval_node с interrupt()
```

### 4.3 Approval Keyboard (по аналогии с feedback.py)

```python
# telegram_bot/approval.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_APPROVAL_PREFIX = "approve:"

def build_approval_keyboard(
    action_id: str,
    action_description: str,
) -> InlineKeyboardMarkup:
    """Inline keyboard: Подтвердить / Отменить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"{_APPROVAL_PREFIX}yes:{action_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"{_APPROVAL_PREFIX}no:{action_id}",
                ),
            ]
        ]
    )

def parse_approval_callback(data: str) -> tuple[bool, str] | None:
    """Parse 'approve:yes:action_123' → (True, 'action_123')."""
    if not data.startswith(_APPROVAL_PREFIX):
        return None
    parts = data.removeprefix(_APPROVAL_PREFIX).split(":", 1)
    if len(parts) != 2:
        return None
    return (parts[0] == "yes", parts[1])
```

### 4.4 Approval Node (LangGraph)

```python
# telegram_bot/graph/nodes/approval.py
from langgraph.types import interrupt, Command
from langfuse.decorators import observe

@observe(name="node-approval")
async def approval_node(state: dict) -> dict | Command:
    """Pause graph and request human approval via Telegram inline keyboard."""
    action = state.get("pending_action", {})

    # interrupt() — graph pauses here, payload sent to Telegram
    decision = interrupt({
        "type": "approval_request",
        "action": action.get("name", "unknown"),
        "description": action.get("description", ""),
        "details": action.get("details", {}),
    })

    if decision.get("approved"):
        return {"approval_status": "approved"}
    else:
        return {
            "approval_status": "rejected",
            "response": f"Действие отменено пользователем.",
        }
```

### 4.5 Bot Callback Handler

```python
# telegram_bot/bot.py — additions
async def handle_approval(self, callback: CallbackQuery):
    """Handle approval/rejection from inline keyboard."""
    parsed = parse_approval_callback(callback.data)
    if not parsed:
        await callback.answer("Неизвестная кнопка")
        return

    approved, action_id = parsed
    user_id = callback.from_user.id
    thread_id = str(user_id)

    # Resume the interrupted graph
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await self._current_graph.ainvoke(
            Command(resume={"approved": approved, "action_id": action_id}),
            config,
        )
        # Send result to user
        response = result.get("response", "Действие выполнено.")
        await callback.message.edit_text(
            f"{'✅' if approved else '❌'} {response}"
        )
    except Exception:
        logger.exception("Failed to resume approval graph")
        await callback.message.edit_text("Ошибка при обработке решения.")

    await callback.answer()
```

---

## 5. Какие операции требуют HITL

### 5.1 Текущие операции (не требуют HITL)

| Операция | Тип | HITL? | Причина |
|----------|-----|-------|---------|
| RAG search | Read-only | ❌ | Поиск безопасен, необратимости нет |
| Cache lookup | Read-only | ❌ | Чтение кеша безопасно |
| Query rewrite | Internal | ❌ | Внутренняя оптимизация запроса |
| Generate response | Read-only | ❌ | Генерация текста, можно переспросить |

### 5.2 Будущие операции (потребуют HITL)

| Операция | Тип | HITL? | Когда появится |
|----------|-----|-------|---------------|
| Создать запись/встречу | Write (external API) | ✅ | После #240 supervisor + tools |
| Отправить email/уведомление | Write (external) | ✅ | После MCP tools (#232) |
| Изменить настройки пользователя | Write (DB) | ⚠️ Опционально | После user personalization |
| Удалить данные | Delete (DB) | ✅ | Если будет такой tool |
| Оплата / финансовая операция | Write (payment API) | ✅ | Если будет интеграция |

### 5.3 Правило категоризации

```
IF операция = read-only → NO HITL
IF операция = write AND reversible → OPTIONAL HITL (config)
IF операция = write AND irreversible → REQUIRED HITL
IF операция = delete → REQUIRED HITL
IF операция = financial → REQUIRED HITL
```

---

## 6. Timeout и Auto-Cancel

### 6.1 Механизм

LangGraph `interrupt()` ждёт **бесконечно** — нет встроенного timeout. Нужен внешний механизм.

### 6.2 Варианты

| Вариант | Реализация | Плюсы | Минусы |
|---------|-----------|-------|--------|
| **A. Redis TTL** | Ключ `approval:{action_id}` с TTL=300s | Простой, надёжный | Нужен polling/expiry listener |
| **B. asyncio.wait_for** | Не применимо — interrupt() не async wait | — | ❌ Не работает с interrupt |
| **C. Background task** | `asyncio.create_task` + sleep(300) + cancel | Точный timeout | Не переживёт restart |
| **D. Scheduled cleanup** | Периодическая задача проверяет interrupted threads | Reliable | Latency до 1 мин |

### 6.3 Рекомендация: Redis TTL + Cleanup Task

```python
# При interrupt:
await redis.set(f"approval:{action_id}", json.dumps(payload), ex=300)

# Periodic cleanup (каждые 60s):
async def cleanup_expired_approvals():
    # Find interrupted threads older than 5 min
    # Resume with Command(resume={"approved": False, "reason": "timeout"})
    ...

# При callback:
if not await redis.exists(f"approval:{action_id}"):
    await callback.answer("Время подтверждения истекло (5 мин)")
    return
```

---

## 7. Langfuse Observability

### 7.1 Scores для HITL

| Score | Type | Values | Описание |
|-------|------|--------|----------|
| `hitl_requested` | CATEGORICAL | `true` | Был ли запрошен HITL |
| `hitl_decision` | CATEGORICAL | `approved`, `rejected`, `timeout` | Решение пользователя |
| `hitl_latency_ms` | NUMERIC | 0-300000 | Время от запроса до решения |
| `hitl_action` | CATEGORICAL | action name | Какое действие требовало подтверждения |

### 7.2 Trace structure

```
trace: handle_query
  ├── node-classify
  ├── node-cache-check
  ├── node-retrieve
  ├── node-generate
  ├── node-approval          ← interrupt() here
  │   ├── span: approval_request_sent
  │   └── span: approval_decision_received  (after resume)
  ├── node-execute-tool      ← only if approved
  └── node-respond
```

---

## 8. Интеграция с Supervisor (#240)

### 8.1 Supervisor + HITL

В архитектуре multi-agent supervisor (#240), HITL встраивается в tool execution:

```
User Query → Supervisor → [select tool] → tool_node
                                              │
                                    if tool.requires_approval:
                                              │
                                        approval_node
                                              │
                                       interrupt()
                                              │
                                    [user approves/rejects]
                                              │
                                    tool execution / cancel
```

### 8.2 Tool Metadata

```python
@mcp.tool(metadata={"requires_approval": True})
async def create_appointment(date: str, description: str) -> str:
    """Create an appointment — requires human approval."""
    ...
```

Supervisor проверяет `tool.metadata["requires_approval"]` и маршрутизирует через `approval_node`.

---

## 9. Реализация — поэтапная

### Phase 1: Infrastructure (не блокирует — всё уже есть)

- [x] Redis checkpointer подключен
- [x] Inline keyboard pattern (feedback.py)
- [x] Thread ID per user

### Phase 2: Approval Module

1. Создать `telegram_bot/approval.py` (keyboard + parser)
2. Создать `telegram_bot/graph/nodes/approval.py` (interrupt node)
3. Добавить `handle_approval()` callback handler в bot.py
4. Тесты: `tests/unit/test_approval.py`, `tests/unit/graph/test_approval_node.py`

### Phase 3: Integration (после #240 supervisor)

1. Добавить `approval_node` в граф (conditional — только для write operations)
2. Tool metadata `requires_approval`
3. Timeout cleanup task

### Phase 4: Observability

1. Langfuse scores: `hitl_requested`, `hitl_decision`, `hitl_latency_ms`
2. Spans: `approval_request_sent`, `approval_decision_received`

---

## 10. Альтернативы (отклонённые)

| Альтернатива | Почему отклонена |
|-------------|------------------|
| **Отдельный approval service** | Over-engineering, LangGraph interrupt() решает задачу |
| **interrupt_before/after** (static) | Deprecated pattern, нет conditional logic |
| **Polling-based** (бот спрашивает текстом) | UX хуже чем inline keyboard, нет structured response |
| **WebSocket-based UI** | Telegram bot — inline keyboard достаточно |
| **CIBA (Auth0)** | Избыточно для Telegram бота, подходит для enterprise |

---

## 11. Риски и Mitigation

| Риск | Severity | Mitigation |
|------|----------|-----------|
| Interrupt state lost (Redis restart) | HIGH | Redis persistence (AOF), MemorySaver fallback |
| User clicks after timeout | MEDIUM | Check Redis TTL before resume, graceful error |
| Multiple concurrent interrupts per user | MEDIUM | Queue — один interrupt за раз per thread_id |
| Node idempotency (code before interrupt reruns) | HIGH | Все side effects после interrupt(), не до |
| Graph version mismatch after deploy | LOW | Version в state, reject stale interrupts |

---

## 12. Key Research Sources

| Источник | Тип |
|----------|-----|
| [LangGraph interrupt() docs](https://docs.langchain.com/oss/python/langgraph/interrupts) | Official docs |
| [LangGraph HITL concepts](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/) | Conceptual guide |
| [interrupt() announcement blog](https://blog.langchain.dev/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt/) | Blog post |
| [Wait for user input how-to](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/) | How-to guide |
| [HITL + FastAPI production](https://generativeai.pub/when-llms-need-humans-managing-langgraph-interrupts-through-fastapi-97d0912fb6af) | Production patterns |
| [HITL + Elasticsearch](https://www.elastic.co/search-labs/kr/blog/human-in-the-loop-hitllanggraph-elasticsearch) | Real-world example |
| [Plan-and-Execute with approval (2026)](https://www.marktechpost.com/2026/02/16/how-to-build-human-in-the-loop-plan-and-execute-ai-agents-with-explicit-user-approval-using-langgraph-and-streamlit/) | Latest tutorial |

---

## 13. Резюме

**Ключевые решения:**

1. **LangGraph `interrupt()`** — основной механизм паузы/возобновления (не static breakpoints)
2. **Redis checkpointer** — уже подключен, interrupt state персистится
3. **Telegram inline keyboard** — approve/reject кнопки (аналогично feedback.py)
4. **Timeout 5 мин** — Redis TTL + cleanup task для auto-cancel
5. **Поэтапная реализация** — approval module → integration с supervisor (#240) → observability
6. **Правило:** HITL только для write/delete/financial — read-only операции без подтверждения

**Зависимости:**
- Phase 2 можно начать сейчас (модуль + тесты)
- Phase 3 блокируется #240 (supervisor architecture)
- Phase 4 можно параллельно с Phase 3
