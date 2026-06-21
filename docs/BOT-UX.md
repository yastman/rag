# BOT-UX.md — Menu → Handler → Layer Map

Reference map from each persistent menu action to its handler function to its architectural layer.

## Menu Actions

| Menu action | Button text | Callback / Route | Handler | Layer | Notes |
|---|---|---|---|---|---|
| **Ask question** | 💬 Задать вопрос | `"ask"` parsed from `parse_menu_button()` | `PropertyBot._handle_ask()` / `_bot_catalog._handle_ask()` | Adapter (telegram_bot) | Shows inline FAQ menu with 4 predefined questions (docs, costs, ВНЖ, installment); user selects or types free-form. Callback `ask:*` routes to `handle_ask_callback()` → `handle_menu_action_text()` → RAG pipeline. |
| **Find apartment** | 🏠 Подобрать квартиру | `"search"` parsed from `parse_menu_button()` | `PropertyBot._handle_search()` / `_bot_catalog._handle_search()` | Adapter (telegram_bot) | Launches aiogram-dialog funnel (FunnelSG.city state) for apartment search wizard. Fallback: `handle_menu_action_text()` if dialog_manager unavailable. |
| **Services** | 🔑 Услуги | `"services"` parsed from `parse_menu_button()` | `PropertyBot._handle_services()` / `_bot_catalog._handle_services()` | Adapter (telegram_bot) | Shows inline services menu. Callback `svc:*` routes to `handle_service_callback()` → service card display. |
| **Book viewing** | 📅 Запись на осмотр | `"viewing"` parsed from `parse_menu_button()` | `PropertyBot._handle_viewing()` / `_bot_catalog._handle_viewing()` | Adapter (telegram_bot) | Launches aiogram-dialog wizard (ViewingSG.date state) for viewing appointment booking. Fallback: text response if dialog_manager unavailable. |
| **Contact manager** | 👤 Связаться с менеджером | `"manager"` parsed from `parse_menu_button()` | `PropertyBot._handle_manager()` / `_bot_handoff._handle_manager()` | Adapter (telegram_bot) | HITL confirmation required. Routes to handoff qualification (forum topics) or phone collection. Creates Kommo CRM task for manager. |
| **My bookmarks** | 📌 Мои закладки | `"bookmarks"` parsed from `parse_menu_button()` | `PropertyBot._handle_bookmarks()` / `_bot_favorites._handle_bookmarks()` | Adapter (telegram_bot) | Lists user's favorited property cards from Redis. Requires FSMContext. Offers quick actions: view, delete, contact. |
| **Demo** | 🎯 Демонстрация | `"demo"` parsed from `parse_menu_button()` | `PropertyBot._handle_demo()` / `demo_handler.handle_demo_button()` | Adapter (telegram_bot) | Shows demo examples inline keyboard for quick exploration (no dialog). User selects → `handle_menu_action_text()` → RAG pipeline. |

## Flow Overview

```
User presses ReplyKeyboard button
    ↓
handle_menu_button(message, state, dialog_manager, i18n)
    ↓
parse_menu_button(message.text) → action_id ("ask", "search", etc.)
    ↓
Route via handlers dict:
    ├─ "search" → _handle_search(message, dialog_manager)
    ├─ "services" → _handle_services(message, i18n)
    ├─ "viewing" → _handle_viewing(message, state, dialog_manager)
    ├─ "bookmarks" → _handle_bookmarks(message, state)
    ├─ "ask" → _handle_ask(message, i18n)
    ├─ "manager" → _handle_manager(message, i18n, state, dialog_manager)
    └─ "demo" → _handle_demo(message)
    ↓
Handler acts:
    ├─ Dialog launchers: dialog_manager.start(SG.state) OR handle_menu_action_text()
    ├─ Inline menu: message.answer(text, reply_markup=keyboard)
    ├─ Callback handlers: parse_callback() → route to sub-handler (ask, service, etc.)
    └─ HITL workflows: qualification or phone collection
```

## Handler Organization

| Handler | Files | Purpose |
|---|---|---|
| `_handle_search` | `telegram_bot/_bot_catalog.py`, `telegram_bot/bot.py` | Apartment search funnel (dialog) |
| `_handle_services` | `telegram_bot/_bot_catalog.py`, `telegram_bot/bot.py` | Services inline menu |
| `_handle_viewing` | `telegram_bot/_bot_catalog.py`, `telegram_bot/bot.py` | Viewing appointment funnel (dialog) |
| `_handle_bookmarks` | `telegram_bot/_bot_favorites.py`, `telegram_bot/bot.py` | Bookmarks list |
| `_handle_ask` | `telegram_bot/_bot_catalog.py`, `telegram_bot/bot.py` | FAQ inline menu + query routing |
| `_handle_manager` | `telegram_bot/_bot_handoff.py`, `telegram_bot/bot.py` | Manager handoff qualification → Kommo CRM |
| `_handle_demo` | `telegram_bot/handlers/demo_handler.py`, `telegram_bot/bot.py` | Demo examples keyboard |

## Callback Handlers

Sub-handlers for inline keyboard callbacks from FAQ, services, and other inline menus:

| Callback prefix | Handler | Purpose |
|---|---|---|
| `ask:*` | `handle_ask_callback()` in `_bot_catalog.py` | FAQ question selected → route query to RAG pipeline |
| `svc:*` | `handle_service_callback()` in `_bot_catalog.py` | Service menu action (view service, back, menu) |
| `fav:*` | `handle_fav_add()` in `_bot_favorites.py` | Add/remove bookmark |
| `cta:*` | `handle_cta_callback()` in `_bot_catalog.py` | Call-to-action buttons on property cards (contact, inquire) |

## Architectural Layers

All menu handlers and their callbacks live in the **Adapter layer** (`telegram_bot/`):

| Layer | Components | Owns what | Never imports |
|---|---|---|---|
| **Adapter** (`telegram_bot/`) | Menu handlers, dialog flows, inline keyboards, callback routers, phone collection, handoff qualification | UI routing, dialog state, inline menus, user interaction orchestration | `src/runtime` (RAG core), `src/ingestion` |
| **Core** (`src/runtime/`, `src/core/`) | RAG pipeline, retrieval, generation, reranking, grounding | Query processing, knowledge search, LLM reasoning | `telegram_bot` (never import bot) |
| **Services** (`src/services/`, `telegram_bot/services/`) | Qdrant client, BGE-M3, Redis, Kommo, handoff state, content loader | Low-level integrations, API clients | High-level app logic |

Menu buttons never directly trigger RAG; they route through handlers that:
1. Show dialogs or inline menus, OR
2. Call `handle_menu_action_text(message, query_text)` which dispatches to the RAG pipeline via `handle_query()`.

---

## See Also

- [`telegram_bot/keyboards/client_keyboard.py`](../telegram_bot/keyboards/client_keyboard.py) — menu button definitions and parsing
- [`telegram_bot/bot.py`](../telegram_bot/bot.py) — `PropertyBot.handle_menu_button()` dispatcher
- [`telegram_bot/_bot_catalog.py`](../telegram_bot/_bot_catalog.py) — catalog-related handlers
- [`telegram_bot/_bot_favorites.py`](../telegram_bot/_bot_favorites.py) — bookmarks handler
- [`telegram_bot/_bot_handoff.py`](../telegram_bot/_bot_handoff.py) — manager handoff handler
- [`telegram_bot/handlers/demo_handler.py`](../telegram_bot/handlers/demo_handler.py) — demo handler
- [`docs/architecture/STRUCTURE.md`](architecture/STRUCTURE.md) — full architectural module map
