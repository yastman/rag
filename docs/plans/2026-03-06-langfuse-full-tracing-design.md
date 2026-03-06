# Langfuse Full Tracing Coverage — Design

**Date:** 2026-03-06
**Goal:** Полное покрытие Langfuse трейсами всех runtime flows бота: меню, диалоги, callbacks, commands, apartment pipeline, LLM gaps, graph edges.

---

## 1. Текущее состояние

### Покрыто хорошо (не трогаем)
- Graph nodes (11/11) — `@observe` + curated spans
- RAG pipeline (6 steps) — полное покрытие
- Kommo client (15/16 методов) — 94%
- CRM agent tools (12/12) — 100%
- History service (4/4) — 100%
- Cache operations (12 методов) — 100%
- Scoring — 30+ метрик на trace
- Voice graph — все nodes + OTEL на LiveKit

### Проблемы из реальных трейсов (lf traces list)
1. **21 orphan traces из 50** — `apartments-filtered-search`, `OpenAI-generation`, `bge-m3-hybrid-colbert-embed` без session/user/tags. Причина: demo handler, funnel dialog, apartment extraction вызывают `@observe`-сервисы без `propagate_attributes`.
2. **8 litellm-acompletion дубликатов** — LiteLLM proxy автотрейсит `success_callback: langfuse`, дублируя наши `generate-answer` генерации.
3. **Промпты в Langfuse пусты** (dev инстанс) — все 8 prompt names (`generate`, `hyde`, `query-analysis`, `client_agent`, `manager_agent`, `advisor-daily-plan`, `advisor-deal-tips`, `generate_{style}`) используют hardcoded fallback.

### Пробелы по слоям

| Слой | Покрыто | Непокрыто |
|------|---------|-----------|
| Handlers & Commands | 3/31 | 28 handlers/callbacks/commands |
| Dialogs | 0/11 файлов | Все dialog handlers |
| handlers/ | 0/4 файла | phone_collector, handoff, demo, crm_callbacks |
| Services (LLM) | 0/4 метода | session_summary, ai_advisor, nurturing, apartment_llm_extractor |
| Middleware | 0/3 | throttling, error_handler, i18n |
| Graph edges | 0/5 | route_start, route_by_query_type, route_after_guard, route_cache, route_grade |
| Apartment pipeline | 3/11 | extraction pipeline, regex parser, scroll, funnel filters |

---

## 2. Архитектура решения

**Подход C: Middleware root trace + selective @observe**

```
User Message/Callback
  |
  v
LangfuseMiddleware (NEW) -----> propagate_attributes(session_id, user_id, tags)
  |                               Creates root trace for EVERY update
  v
ThrottlingMiddleware             (existing, throttled events get trace with tag "throttled")
  |
  v
ErrorMiddleware (MODIFIED) ----> lf.update_current_span(level="ERROR") on exception
  |
  v
I18nMiddleware                   (existing, no changes)
  |
  v
Handler (@observe) -----------> Child span: menu-search, cmd-clear, cb-results-more, etc.
  |
  v
Service (@observe) -----------> Child span: apartment-extraction-pipeline, advisor-llm-call, etc.
```

**Принципы:**
- Middleware создает root trace — гарантирует session_id/user_id ВСЕГДА есть
- `@observe` добавляется ТОЛЬКО на handlers с бизнес-логикой (не на cmd_help, FAQ getter)
- Orphan traces исчезают — все сервисные вызовы наследуют контекст от middleware
- LiteLLM dedup — убрать `success_callback: langfuse` из LiteLLM config

---

## 3. Детальный scope

### 3.1 LangfuseMiddleware (новый файл)

**Файл:** `telegram_bot/middlewares/langfuse_middleware.py`

```python
class LangfuseMiddleware(BaseMiddleware):
    """Root trace on every Telegram update with session_id, user_id, tags."""

    async def __call__(self, handler, event, data):
        user_id = extract_user_id(event)
        session_id = make_session_id(event)
        action_type = classify_action(event)  # "message", "callback", "command"

        with propagate_attributes(
            session_id=session_id,
            user_id=str(user_id),
            tags=["telegram", action_type],
        ):
            lf = get_client()
            if lf:
                lf.update_current_trace(
                    name=f"telegram-{action_type}",
                    metadata={"action_type": action_type},
                )
            return await handler(event, data)
```

**Регистрация:** `dp.message.outer_middleware(LangfuseMiddleware())` + `dp.callback_query.outer_middleware(LangfuseMiddleware())` — ПЕРЕД throttling.

**Порядок middleware (outer → inner):**
1. `LangfuseMiddleware` (NEW) — root trace
2. `ErrorHandlerMiddleware` (MODIFIED) — error spans
3. `I18nMiddleware` — locale injection
4. `ThrottlingMiddleware` — rate limiting

### 3.2 ErrorHandlerMiddleware — добавить Langfuse error reporting

**Файл:** `telegram_bot/middlewares/error_handler.py`

```python
# В catch блоке добавить:
lf = get_client()
if lf:
    lf.update_current_span(
        level="ERROR",
        status_message=f"{type(exc).__name__}: {str(exc)[:200]}",
    )
```

### 3.3 Menu Handlers (@observe)

**Файл:** `telegram_bot/bot.py`

| Метод | Span name | Что логировать в span |
|-------|-----------|----------------------|
| `handle_menu_button()` | `menu-router` | action_id |
| `_handle_search()` | `menu-search` | has_dialog_manager |
| `_handle_services()` | `menu-services` | — |
| `_handle_viewing()` | `menu-viewing` | has_dialog_manager |
| `_handle_bookmarks()` | `menu-bookmarks` | items_count |
| `_handle_promotions()` | `menu-promotions` | promos_count |
| `_handle_ask()` | `menu-ask` | — |
| `_handle_manager()` | `menu-manager` | handoff_type (forum/phone/fallback) |

### 3.4 Callback Handlers (@observe)

**Файл:** `telegram_bot/bot.py`

| Метод | Span name | Что логировать |
|-------|-----------|---------------|
| `handle_service_callback()` | `cb-service` | action, param |
| `handle_cta_callback()` | `cb-cta` | action (get_offer/manager) |
| `handle_favorite_callback()` | `cb-favorite` | action (add/remove/viewing) |
| `handle_results_callback()` | `cb-results` | action (more/refine/viewing), page_num |
| `handle_card_callback()` | `cb-card` | action (viewing/ask), property_id |
| `handle_ask_callback()` | `cb-ask` | query_text |
| `handle_feedback()` | `cb-feedback` | value (like/dislike) — уже пишет score, добавить span |
| `handle_feedback_reason()` | `cb-feedback-reason` | reason_code |
| `handle_clearcache_callback()` | `cb-clearcache` | tier, deleted_count |

### 3.5 Command Handlers (@observe)

**Файл:** `telegram_bot/bot.py`

| Command | Span name | Что логировать | Приоритет |
|---------|-----------|---------------|-----------|
| `cmd_start()` | `cmd-start` | role (client/manager) | LOW |
| `cmd_clear()` | `cmd-clear` | cleared_tiers | LOW |
| `cmd_call()` | `cmd-call` | phone, call_id, room_name | MEDIUM |
| `cmd_clearcache()` | `cmd-clearcache` | — | LOW |
| `cmd_stats()` | — | Не трейсим (readonly) | — |
| `cmd_help()` | — | Не трейсим (static) | — |
| `cmd_metrics()` | — | Не трейсим (readonly) | — |

### 3.6 Dialog Handlers (@observe, 7 критических)

| Файл | Handler | Span name | Что логировать |
|------|---------|-----------|---------------|
| `funnel.py` | `on_summary_search()` | `dialog-funnel-search` | filters, results_count, has_more |
| `funnel.py` | `get_results_data()` | `dialog-funnel-results` | page, total_count |
| `viewing.py` | `on_confirm()` | `dialog-viewing-confirm` | objects_count, has_kommo, lead_id |
| `crm_leads.py` | `on_lead_confirm()` | `dialog-crm-create-lead` | name, budget, pipeline_id |
| `crm_contacts.py` | `on_contact_confirm()` | `dialog-crm-create-contact` | phone (masked) |
| `crm_tasks.py` | `on_task_confirm()` | `dialog-crm-create-task` | task_type, lead_id |
| `crm_notes.py` | `on_note_confirm()` | `dialog-crm-create-note` | entity_type, entity_id |

### 3.7 Handlers/ (@observe, 5 handlers)

| Файл | Handler | Span name | Что логировать |
|------|---------|-----------|---------------|
| `phone_collector.py` | `_process_valid_phone()` | `phone-lead-capture` | service_key, has_kommo, lead_created |
| `demo_handler.py` | `_run_demo_search()` | `demo-search` | query, extraction_method (llm/regex), results_count |
| `demo_handler.py` | `transcribe_voice()` | `demo-transcribe` | audio_size, stt_duration_ms |
| `crm_callbacks.py` | `on_task_complete()` | `crm-quick-complete` | task_id |
| `crm_callbacks.py` | `on_note_text_received()` | `crm-quick-note` | entity_type, entity_id |

### 3.8 Services — LLM без трейсов (4 @observe)

| Файл | Метод | Span name | Что логировать |
|------|------|-----------|---------------|
| `session_summary.py` | `generate_summary()` | `session-summary-generate` | turns_count, model, response_format_used |
| `ai_advisor_service.py` | `_call_llm()` | `advisor-llm-call` | prompt_name, model, max_tokens |
| `nurturing_service.py` | `_generate_nurturing_message()` | `nurturing-llm-generate` | lead_id, template_fallback |
| `apartment_llm_extractor.py` | `extract()` | `apartment-llm-extract` | model, retries, extracted_fields |

### 3.9 Apartment Pipeline (@observe, 3 метода)

| Файл | Метод | Span name | Что логировать |
|------|------|-----------|---------------|
| `apartment_extraction_pipeline.py` | `extract()` | `apartment-extraction-pipeline` | method (llm/regex/cache), confidence, conflicts |
| `apartment_filter_extractor.py` | `parse()` | `apartment-filter-parse` | rooms, price_range, confidence, missing_fields, semantic_remainder |
| `apartments_service.py` | `scroll_with_filters()` | `apartments-scroll` | filter_count, limit, returned_count, has_more |

### 3.10 Graph Edge Functions (@observe, 5 edges)

**Файл:** `telegram_bot/graph/edges.py`

| Edge | Span name | Что логировать |
|------|-----------|---------------|
| `route_start()` | `edge-route-start` | decision (transcribe/classify) |
| `route_by_query_type()` | `edge-route-query-type` | query_type, decision |
| `route_after_guard()` | `edge-route-guard` | guard_blocked, decision |
| `route_cache()` | `edge-route-cache` | cache_hit, embedding_error, decision |
| `route_grade()` | `edge-route-grade` | confidence, skip_rerank, rewrite_count, decision |

### 3.11 LiteLLM Dedup

**Файл:** `docker/litellm/config.yaml`

```yaml
# УДАЛИТЬ:
litellm_settings:
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]
```

Наши `@observe` + Langfuse OpenAI SDK wrapper уже трейсят все LLM вызовы. LiteLLM callback создает дублирующие orphan `litellm-acompletion` traces.

### 3.12 Langfuse Prompts — восстановление

Загрузить 8 промптов в dev Langfuse через API или UI, чтобы `get_prompt()` возвращал remote версии вместо fallback. Это позволит A/B тестирование промптов.

| Prompt name | Source | Variables |
|-------------|--------|-----------|
| `generate` | `_GENERATE_FALLBACK` | `{{domain}}` |
| `generate_short` | contract template | `{{domain}}` |
| `generate_balanced` | contract template | `{{domain}}` |
| `generate_detailed` | contract template | `{{domain}}` |
| `query-analysis` | `SYSTEM_PROMPT` | — |
| `hyde` | `HYDE_SYSTEM_PROMPT` | — |
| `client_agent` | `CLIENT_SYSTEM_PROMPT` | `{{language}}`, `{{role_context}}` |
| `manager_agent` | `MANAGER_SYSTEM_PROMPT` | `{{language}}`, `{{role_context}}` |
| `advisor-daily-plan` | `_FALLBACK_DAILY_PLAN` | — |
| `advisor-deal-tips` | `_FALLBACK_DEAL_TIPS` | — |

---

## 4. Что НЕ трейсим (осознанное решение)

| Компонент | Причина |
|-----------|---------|
| `cmd_help()`, `cmd_stats()`, `cmd_metrics()` | Static/readonly, шум в трейсах |
| `build_funnel_filters()` | Чистая функция, данные видны в parent span |
| `_build_apartment_filter()` | Чистая функция, данные видны в parent span |
| Keyboard builders | UI-only, нет бизнес-логики |
| `i18n.py` middleware | Locale detection, низкая ценность |
| `content_loader.py` | YAML read, lru_cached |
| `favorites_service.py` | Простой CRUD, трейсится через parent |
| `user_service.py` | Простой CRUD |

---

## 5. Ожидаемый результат

### До
- 21/50 orphan traces (42%)
- 8 LiteLLM дубликатов
- Menu/dialog/callback handlers invisible
- 4 LLM вызова без трейсов

### После
- 0 orphan traces (middleware гарантирует root trace)
- 0 LiteLLM дубликатов
- ~40 новых span names покрывающих все user flows
- 100% LLM вызовов с трейсами
- Edge routing decisions видны в Langfuse
- Промпты управляемы через Langfuse UI

### Trace tree (пример menu → funnel → search)

```
telegram-message (middleware root)
└── menu-router (handle_menu_button)
    └── menu-search (_handle_search)
        └── dialog-funnel-search (on_summary_search)
            ├── apartment-extraction-pipeline
            │   ├── apartment-filter-parse (regex)
            │   └── apartment-llm-extract (fallback)
            ├── apartments-scroll (scroll_with_filters)
            │   └── apartments-filtered-search (existing)
            └── phone-lead-capture (_process_valid_phone)
                ├── kommo-upsert-contact (existing)
                ├── kommo-create-lead (existing)
                └── kommo-create-task (existing)
```

---

## 6. Риски и митигация

| Риск | Митигация |
|------|----------|
| Middleware создает trace для throttled requests | Тег `throttled` в tags, фильтрация в Langfuse UI |
| @observe overhead на hot path | capture_input=False, capture_output=False на heavy handlers |
| Двойной trace (middleware + handle_query @observe) | handle_query уже имеет @observe — middleware root станет parent, handle_query станет child. Проверить что не дублируется. |
| Langfuse down → latency | Graceful degradation уже реализован (get_client() → None → no-op) |

---

## 7. Объём работы

| Категория | Файлов | @observe добавить | Новые файлы |
|-----------|--------|------------------|-------------|
| Middleware | 2 | 0 (middleware pattern) | 1 (`langfuse_middleware.py`) |
| Handlers bot.py | 1 | ~17 | 0 |
| Commands bot.py | 1 | ~4 | 0 |
| Dialogs | 5 | ~7 | 0 |
| handlers/ | 3 | ~5 | 0 |
| Services | 4 | ~4 | 0 |
| Apartment | 3 | ~3 | 0 |
| Graph edges | 1 | ~5 | 0 |
| LiteLLM config | 1 | 0 | 0 |
| Prompts | 0 | 0 | 1 (seed script) |
| **Total** | **~21** | **~45** | **2** |

Оценка: **большая задача** → plan + tmux-swarm (Sonnet workers).
