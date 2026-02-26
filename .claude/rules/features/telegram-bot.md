---
paths: "telegram_bot/*.py, telegram_bot/middlewares/**, telegram_bot/graph/**, telegram_bot/agents/**, telegram_bot/services/generate_response.py, telegram_bot/pipelines/**, telegram_bot/services/types.py, telegram_bot/keyboards/**, telegram_bot/handlers/**"
---

# Telegram Bot

Hybrid RAG pipeline (async functions for text, LangGraph for voice) with aiogram Telegram interface.

## Architecture

```
Text (client fast-path — default for client role):
  User Message → ThrottlingMiddleware → ErrorMiddleware
             → PropertyBot.handle_query() → _handle_client_direct_pipeline()
             → run_client_pipeline() (pipelines/client.py)
             → classify → detect_agent_intent → cache → rag_pipeline(skip_rewrite?) → generate_response
             → Langfuse: @observe spans (pipeline_mode="client_direct")

Text (sdk_agent — manager role, fallback for client on fast-path error):
  User Message → ThrottlingMiddleware → ErrorMiddleware
             → PropertyBot.handle_query() → _handle_query_supervisor()
             → create_bot_agent(model, tools, context_schema=BotContext)
             → Agent LLM → tool_choice:
               → rag_search → rag_pipeline() (6-step async)
               → history_search → build_history_graph() (4-node LangGraph)
               → 8 CRM tools (Kommo API) | direct response
             → Langfuse: CallbackHandler + @observe spans (pipeline_mode="sdk_agent")

Menu:   ReplyKeyboard button → handle_menu_button() → dispatch:
             🏠 Подбор апартаментов → _handle_search → handle_query("Подбери апартаменты")
             🔑 Услуги → _handle_services → inline services menu (svc:/cta: callbacks)
             📅 Запись на осмотр → _handle_viewing → phone_collector FSM
             📌 Мои закладки → _handle_bookmarks → FavoritesService (fav: callbacks)
             🎁 Акции → _handle_promotions → get_promotions() from services.yaml (#628)
             👤 Связь с менеджером → _handle_manager → handle_query("Соедини с менеджером")
        Inline callbacks: svc:*/cta:* → service cards | fav:* → favorites CRUD | results:* → pagination/viewing

Voice: Voice Message → PropertyBot.handle_voice()
                    → download .ogg → make_initial_state(voice_audio=bytes)
                    → build_graph().ainvoke() (11-node LangGraph: transcribe→guard→classify→...→respond)
```

## Key Files

| File | Description |
|------|-------------|
| `telegram_bot/bot.py` | PropertyBot class (agent orchestrator + voice handler) |
| `telegram_bot/scoring.py` | `score()`, `write_langfuse_scores()`, `write_history_scores()`, `write_crm_scores()` (#310, #451, #452) |
| `telegram_bot/main.py` | Entry point |
| `telegram_bot/config.py` | BotConfig (pydantic-settings BaseSettings) |
| `telegram_bot/agents/rag_pipeline.py` | 6-step async RAG pipeline: `_cache_check → _hybrid_retrieve → _grade_documents → _rerank → _rewrite_query → _cache_store` (#442) |
| `telegram_bot/agents/agent.py` | `create_bot_agent()` — `langchain.agents.create_agent` SDK, `ChatOpenAI` client, `get_prompt` (#413) |
| `telegram_bot/agents/context.py` | `BotContext` dataclass — DI via `context_schema` into tools |
| `telegram_bot/agents/rag_tool.py` | `rag_search` @tool — wraps `rag_pipeline()` (async functions) |
| `telegram_bot/agents/history_tool.py` | `history_search` @tool — wraps 4-node history sub-graph |
| `telegram_bot/agents/crm_tools.py` | 8 CRM @tools for Kommo API (get/create/update deals, contacts, notes, tasks) |
| `telegram_bot/agents/hitl.py` | `hitl_guard()` — LangGraph `interrupt()` for HITL confirmation on CRM write ops (#443) |
| `telegram_bot/agents/manager_tools.py` | `build_tools_for_role()` — role-gating (client vs manager), `sync_pending_lead_scores` tool |
| `telegram_bot/agents/utility_tools.py` | `mortgage_calculator`, `daily_summary`, `handoff` @tools (#445) |
| `telegram_bot/agents/history_graph/` | History sub-graph: guard → retrieve → grade → rewrite → summarize (5 nodes, LangGraph) |
| `telegram_bot/graph/graph.py` | `build_graph()` — 11-node StateGraph (**voice path only**) |
| `telegram_bot/graph/state.py` | RAGState TypedDict (25 fields incl. voice_audio, stt_text, input_type) + `make_initial_state()` |
| `telegram_bot/graph/config.py` | GraphConfig dataclass (service factories, pipeline tuning params) |
| `telegram_bot/pipelines/client.py` | `run_client_pipeline()` — deterministic client fast-path: classify → intent gate → cache → RAG → generate → post-process (#567) |
| `telegram_bot/services/types.py` | `PipelineResult` dataclass (frozen, slots) — pipeline return type with needs_agent fallback signal |
| `telegram_bot/services/generate_response.py` | `generate_response()` — shared LLM generation service (streaming, style, fallback) |
| `telegram_bot/graph/nodes/` | 9 node modules — used by voice LangGraph and shared by rag_pipeline.py |
| `telegram_bot/observability.py` | `get_client()`, `@observe`, `propagate_attributes`, `create_callback_handler`, PII masking |
| `telegram_bot/integrations/prompt_manager.py` | `get_prompt()` — Langfuse Prompt Management with fallback templates + TTL probe cache |
| `telegram_bot/integrations/event_stream.py` | EventStream for graph→bot communication |
| `telegram_bot/services/user_service.py` | `UserService` — user CRUD (asyncpg), locale detection |
| `telegram_bot/services/session_summary.py` | `SessionSummary` — structured CRM note generation from dialog (LLM, Pydantic) |
| `telegram_bot/services/response_style_detector.py` | `ResponseStyleDetector` — zero-latency regex style/difficulty classifier (#129) |
| `telegram_bot/middlewares/throttling.py` | ThrottlingMiddleware |
| `telegram_bot/middlewares/error_handler.py` | ErrorHandlerMiddleware |
| `telegram_bot/middlewares/i18n.py` | I18nMiddleware — locale detection, injects `i18n`, `locale`, `property_bot`, `apartments_service` (#660) |
| `telegram_bot/dialogs/` | aiogram-dialog menus: `crm_submenu`, `faq`, `funnel`, `manager_menu`, `settings` |
| `telegram_bot/handlers/phone_collector.py` | Phone number collection FSM handler + Kommo CRM lead creation (#628) |
| `telegram_bot/keyboards/client_keyboard.py` | Client ReplyKeyboard — `build_client_keyboard(i18n=)`, `get_menu_button_texts(i18n_hub=)`, `parse_menu_button(text, i18n_hub=)` with .ftl keys (#660) |
| `telegram_bot/keyboards/property_card.py` | Property listing card with bookmark + results footer |
| `telegram_bot/keyboards/services_keyboard.py` | Services inline menu — `build_services_menu(i18n=)`, `build_service_card_buttons(key, i18n=)` with .ftl keys, yaml fallback (#677) |
| `telegram_bot/services/apartments_service.py` | ApartmentsService — hybrid search + `scroll_with_filters()` + funnel `search()` (#632, #660, #628) |
| `telegram_bot/services/apartment_filter_extractor.py` | Regex filter parser: rooms, price, complex, view, floor, area (#632) |
| `telegram_bot/services/favorites_service.py` | User apartment favorites (asyncpg, add/remove/list/count) |
| `telegram_bot/agents/apartment_tools.py` | `apartment_search` @tool — agent escalation for complex queries (#632) |

## Text RAG Pipeline (6 async steps, #442)

`rag_pipeline()` in `agents/rag_pipeline.py` — called by `rag_search` @tool and `run_client_pipeline()`:

```
rag_pipeline(query, ctx, skip_rewrite=False) →
  1. _cache_check(query, embeddings, cache) → cache_hit? return early
  2. _hybrid_retrieve(query_embedding, sparse, qdrant) → RRF fusion
  3. _grade_documents(documents, threshold=0.005) → grade_confidence
  4. _rerank(documents, reranker) → if confidence < skip_rerank_threshold
  5. _rewrite_query(query, llm) → loop back to step 2 (skipped if skip_rewrite=True)
  6. _cache_store(query, response, cache) → store for future hits
```

Each step is `@observe()`-decorated for Langfuse tracing. Returns dict with `documents`, `response`, `latency_stages`, pipeline metadata.

**`skip_rewrite`** (#567): When `True`, bypasses the rewrite loop entirely. Used by client pipeline for FAQ queries where rewrite adds latency without improving retrieval.

## Voice LangGraph Pipeline (11 nodes)

```
START → [voice_audio?] → transcribe → guard → classify → ...
      → [text]         → guard → classify → ...

guard → [injection_detected] → respond (blocked message) → END
      → [clean] → classify → ...

START → classify → [CHITCHAT/OFF_TOPIC] → respond → END
                 → [other] → cache_check → [HIT] → respond → END
                                          → [MISS] → retrieve → grade
                                                       → [relevant + confidence >= 0.018] → generate → cache_store → respond → END (skip rerank)
                                                       → [relevant + confidence < 0.018] → rerank → generate → cache_store → respond → END
                                                       → [count < max_rewrite_attempts AND effective] → rewrite → retrieve (loop)
                                                       → [count >= max_rewrite_attempts] → generate → cache_store → respond → END
```

### Nodes

| Node | File | Injected Deps |
|------|------|---------------|
| guard | `graph/nodes/guard.py` | — (regex patterns, EN+RU, configurable via GUARD_MODE: hard/soft/log) |
| transcribe | `graph/nodes/transcribe.py` | llm (AsyncOpenAI, Whisper API via LiteLLM), message (optional preview) |
| classify | `graph/nodes/classify.py` | — (regex-based, no external deps) |
| cache_check | `graph/nodes/cache.py` | cache, embeddings |
| retrieve | `graph/nodes/retrieve.py` | cache, sparse_embeddings, qdrant (parallel dense+sparse on re-embed) |
| grade | `graph/nodes/grade.py` | — (RRF threshold 0.005, returns `grade_confidence`) |
| rerank | `graph/nodes/rerank.py` | reranker (ColBERT or None) |
| generate | `graph/nodes/generate.py` | Thin adapter → delegates to `services/generate_response.py` (voice/LangGraph compat) |
| rewrite | `graph/nodes/rewrite.py` | llm (optional, uses `config.rewrite_model`/`rewrite_max_tokens`) |
| cache_store | `graph/nodes/cache.py` | cache |
| respond | `graph/nodes/respond.py` | message (aiogram Message, injected) |

### Edges (conditional routing)

| Function | From → To |
|----------|-----------|
| `route_start` | START → transcribe (voice_audio present) or guard (text) |
| `route_guard` | guard → respond (injection_detected) or classify (clean) |
| `route_by_query_type` | classify → respond (CHITCHAT/OFF_TOPIC) or cache_check |
| `route_cache` | cache_check → respond (hit) or retrieve (miss) |
| `route_grade` | grade → generate (relevant + confidence >= `skip_rerank_threshold`), rerank (relevant + low confidence), rewrite (count < `max_rewrite_attempts` AND `rewrite_effective`), generate (fallback) |

## Bot Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | cmd_start | Welcome via i18n key `welcome-text` (fallback: `services.yaml`) + localized ReplyKeyboard (#660) |
| `/help` | cmd_help | Usage instructions |
| `/clear` | cmd_clear | Clear conversation history |
| `/clearcache` | cmd_clearcache | Inline keyboard to clear individual Redis cache tiers (#566) |
| `/stats` | cmd_stats | Cache tier hit rates |
| `/metrics` | cmd_metrics | Pipeline p50/p95 timing |
| (menu button) | handle_menu_button | Routes 6 ReplyKeyboard buttons to dedicated handlers (#628) |
| (callback `svc:`) | handle_service_callback | Service cards, back/menu navigation (#628) |
| (callback `cta:`) | handle_cta_callback | CTA actions: get_offer → phone FSM, manager (#628) |
| (callback `fav:`) | handle_favorite_callback | Favorites: add/remove/viewing/viewing_all (#628) |
| (callback `results:`) | handle_results_callback | Results: more/refine/viewing (#628) |
| (callback) | handle_feedback | Like/dislike feedback (#229) |
| (callback `cc:`) | handle_clearcache_callback | Clear selected cache tier (#566) |

## Client Menu Flow (#628)

ReplyKeyboard (persistent 3x2 grid) → `handle_menu_button()` dispatches to dedicated handlers.
Visible labels are localized from `.ftl` keys (`kb-search`, `kb-services`, `kb-viewing`, `kb-bookmarks`, `kb-promotions`, `kb-manager`), while routing stays action-ID based.
Service titles/cards also localized via `.ftl` keys (`svc-passive-income-title`, `svc-*-card`, `svc-get-offer`, `svc-contact-manager`, `svc-back-to-services`) with `services.yaml` fallback (#677):

| Button | Handler | Action |
|--------|---------|--------|
| 🏠 Подбор апартаментов | `_handle_search` | `handle_menu_action_text(msg, "Подбери апартаменты")` |
| 🔑 Услуги | `_handle_services` | Shows inline services menu (`build_services_menu(i18n=)`) |
| 📅 Запись на осмотр | `_handle_viewing` | `start_phone_collection(msg, state, source="viewing_main_menu")` |
| 📌 Мои закладки | `_handle_bookmarks` | FavoritesService list → property cards or empty message |
| 🎁 Акции | `_handle_promotions` | `get_promotions()` from `services.yaml` (#628) |
| 👤 Связь с менеджером | `_handle_manager` | `handle_menu_action_text(msg, "Соедини с менеджером")` |

**`handle_menu_action_text(message, query_text)`**: DRY helper — patches message text via `model_copy(update={"text": query_text})` and delegates to `handle_query`.

### Callback Routing (inline keyboards)

| Prefix | Handler | Actions |
|--------|---------|---------|
| `svc:` | `handle_service_callback` | `svc:back` (delete msg), `svc:menu` (edit to menu), `svc:{key}` (show service card) |
| `cta:` | `handle_cta_callback` | `cta:get_offer` (phone FSM), `cta:manager` (manager message) |
| `fav:` | `handle_favorite_callback` | `fav:add:{id}`, `fav:remove:{id}`, `fav:viewing:{id}`, `fav:viewing_all` |
| `results:` | `handle_results_callback` | `results:more`, `results:refine`, `results:viewing` (phone FSM) |

Service keys from `config/services.yaml`: `passive_income`, `online_deals`, `vnzh`, `installment`, `infotour`.
Promotions section: `config/services.yaml` → `promotions:` list with `emoji`, `title`, `text` per item (#628).

### Funnel → Hybrid Search (#628)

`get_results_data()` in `dialogs/funnel.py` calls `ApartmentsService.search()` with BGE-M3 embeddings:
1. Resolves `apartments_service` + `hybrid_embeddings` from `middleware_data` (fallback: `property_bot._apartments_service`)
2. Builds query text from dialog_data (city + property_type)
3. `embeddings.aembed_hybrid(query_text)` → dense + sparse vectors
4. `_build_funnel_filters(dialog_data)` → Qdrant payload filters (rooms, price_eur, city, floor, view_tags)
5. `svc.search(dense_vector, sparse_vector, filters, top_k=5)` → results
6. Formats via `format_property_card()` or returns fallback text

### PhoneCollector → Kommo CRM (#628)

`on_phone_received()` accepts `kommo_client` via middleware DI (not FSM state):
1. Validates phone → clears FSM state
2. If `kommo_client is not None`: `upsert_contact` → `create_lead` → `link_contact_to_lead` → `create_task`
3. Graceful degradation: `try/except` with `logger.exception`, user always gets confirmation

### Handler Registration Order (`_register_handlers`)

```
1. phone_router (FSM) — included via dp.include_router()
2. /start, /help, /clear, /clearcache, /stats, /metrics — command handlers
3. `F.text.in_(get_menu_button_texts(self._i18n_hub))` → `handle_menu_button` (before catch-all)
4. StateFilter(None) + F.text — handle_query (catch-all, only when no FSM state active)
5. svc:/cta:/fav:/results: — callback_query handlers
6. feedback/clearcache — other callback handlers
```

**StateFilter(None)**: Critical guard on `handle_query` — prevents catch-all from intercepting text during phone_collector FSM (`waiting_phone` state).

### SDK-backed Constraints (aiogram 3)

- **Filter resolution is first-match:** aiogram stops searching handlers after the first filter set that passes. Therefore, menu handler registration must remain above catch-all `StateFilter(None), F.text` handlers.
- **Middleware data is DI context:** middleware/filter-added context keys are mapped to handler keyword parameters by name. This is why handler signatures can safely accept injected args like `i18n`, `locale`, `kommo_client`, `state`.

## Configuration (BotConfig)

pydantic-settings `BaseSettings` with `.env` file support and `AliasChoices` for env vars:

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `telegram_token` | `TELEGRAM_BOT_TOKEN` | — | Bot token |
| `domain` | `BOT_DOMAIN` | `недвижимость` | Domain topic |
| `domain_language` | `BOT_LANGUAGE` | `ru` | Response language |
| `rerank_provider` | `RERANK_PROVIDER` | `voyage` | colbert / none / voyage |
| `admin_ids` | `ADMIN_IDS` | [] | Comma-separated Telegram IDs |
| `supervisor_model` | `SUPERVISOR_MODEL` | `gpt-4o-mini` | Model for agent routing decisions (#413: create_agent SDK) |
| `client_direct_pipeline_enabled` | `CLIENT_DIRECT_PIPELINE_ENABLED` | `false` | Client fast-path: bypass create_agent, call rag_pipeline → generate_response directly |
| `kommo_enabled` | `KOMMO_ENABLED` | `false` | Enable Kommo CRM tools in agent |
| `streaming_enabled` | `STREAMING_ENABLED` | `true` | Stream LLM output to Telegram via edit_text |
| `show_transcription` | `SHOW_TRANSCRIPTION` | `true` | Show transcribed text before RAG response |
| `voice_language` | `VOICE_LANGUAGE` | `ru` | Whisper language hint (ISO code) |
| `stt_model` | `STT_MODEL` | `whisper` | LiteLLM model name for STT |

### GraphConfig (pipeline tuning)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `skip_rerank_threshold` | `SKIP_RERANK_THRESHOLD` | `0.018` | Skip rerank when grade confidence >= threshold (RRF scale; must be > 1/61≈0.016 to ensure ColBERT runs) |
| `max_rewrite_attempts` | `MAX_REWRITE_ATTEMPTS` | `1` | Max query rewrites before fallback |
| `generate_max_tokens` | `GENERATE_MAX_TOKENS` | `4096` | Token cap for LLM generation |
| `rewrite_max_tokens` | `REWRITE_MAX_TOKENS` | `64` | Token budget for rewrite LLM call |
| `rewrite_model` | `REWRITE_MODEL` | `gpt-4o-mini` | Model for rewrites |
| `bge_m3_timeout` | `BGE_M3_TIMEOUT` | `120.0` | BGE-M3 API timeout (seconds) |
| `guard_mode` | `GUARD_MODE` | `hard` | Content filter mode: hard (block), soft (flag+continue), log (log only) |
| `content_filter_enabled` | `CONTENT_FILTER_ENABLED` | `true` | Enable/disable guard_node entirely |
| `show_sources` | `SHOW_SOURCES` | `false` | Source attribution footer + inline citations in responses (#225) |

## Service Dependencies (initialized in PropertyBot.__init__)

```python
self._cache = CacheLayerManager(redis_url=config.redis_url)
self._hybrid = BGEM3HybridEmbeddings(base_url=config.bge_m3_url)
self._embeddings = self._hybrid  # primary embeddings provider
self._sparse = BGEM3SparseEmbeddings(base_url=config.bge_m3_url)
self._qdrant = QdrantService(url=config.qdrant_url, ...)
self._reranker = ColbertRerankerService(...)  # if rerank_provider == "colbert"
self._llm = self._graph_config.create_llm()   # langfuse.openai.AsyncOpenAI
```

## handle_voice Flow

Downloads `.ogg` → bytes → injects `voice_audio` + `voice_duration_s` + `input_type="voice"` into `make_initial_state()`, then calls `graph.ainvoke(state)`. `transcribe_node` runs first via `route_start`.

**Error handling:** Empty transcription → "Голосовое не содержит речи." | API error → "Не удалось распознать. Попробуйте текстом."

**Langfuse scores:** `input_type` (CATEGORICAL), `stt_duration_ms` (NUMERIC), `voice_duration_s` (NUMERIC)

## handle_query Flow (dual-path routing)

Role-based routing in `PropertyBot.handle_query()`:

1. **Client fast-path** (`_handle_client_direct_pipeline` → `run_client_pipeline()`): Deterministic pipeline in `pipelines/client.py`:
   - classify → `detect_agent_intent()` (mortgage/handoff/daily_summary → `needs_agent=True`) → cache check → `rag_pipeline()` → `generate_response()` → post-process
   - No `create_agent` SDK, no tool-routing LLM call. Feature flag: `CLIENT_DIRECT_PIPELINE_ENABLED`.
   - Returns `PipelineResult` (frozen dataclass from `services/types.py`). If `needs_agent=True`, falls through to agent path.
   - Cache rules: contextual queries skipped, confidence/source guards before store.
   - Fail-safe: on exception, falls back to sdk_agent path.
2. **Manager / fallback** (`_handle_query_supervisor`): Full `create_agent` SDK with tool choice, CRM tools, history search.

**Observability:** `pipeline_mode` metadata on Langfuse span — `"client_direct"` vs `"sdk_agent"`.

### sdk_agent path (manager role)

Builds tools list (`rag_search` + optional `history_search` + optional 8 CRM tools), calls `create_bot_agent(model, tools, checkpointer)`, constructs `BotContext` for DI, invokes agent with `CallbackHandler` for Langfuse tracing.

**Tools (all @tool decorated, deps via BotContext):**
- `rag_search` — wraps `rag_pipeline()` (6-step async functions), @observe("tool-rag-search")
- `history_search` — wraps `build_history_graph().ainvoke()` (5-node sub-graph incl. guard), @observe("tool-history-search")
- 8 CRM tools — `crm_get_deal`, `crm_create_lead`, `crm_update_lead`, `crm_upsert_contact`, `crm_add_note`, `crm_create_task`, `crm_link_contact_to_deal`, `crm_get_contacts`
- Manager tools — `sync_pending_lead_scores`, role-gated via `build_tools_for_role(role=ctx.role, ...)`
- Utility tools — `mortgage_calculator`, `daily_summary`, `handoff` (#445)

**HITL (CRM write ops):** CRM write tools call `hitl_guard(tool_name, preview, args)` → `interrupt()` pauses graph → bot sends inline keyboard → user approves/cancels → `Command(resume={"action": "approve"|"cancel"})`.

**Runtime context:** Tools receive `BotContext` via `config["configurable"]["bot_context"]` (context_schema DI). Role (`ctx.role`) gates manager tools.

**Score writing:** RAG pipeline scores (14 metrics) are written inside `rag_search` tool via `write_langfuse_scores()` from `telegram_bot/scoring.py`.

## Client Pipeline (`pipelines/client.py`, #567)

Deterministic fast-path for client queries — no agent loop, 0-1 LLM calls.

```
run_client_pipeline(user_text, user_id, session_id, message, cache, ...) → PipelineResult
  1. Classify: query_type from classify_query() → CHITCHAT/OFF_TOPIC → canned response
  2. Agent intent gate: detect_agent_intent(user_text) → "mortgage"|"handoff"|"daily_summary"|""
     → if intent: return PipelineResult(needs_agent=True, agent_intent=intent)
  3. Cache check: semantic cache for CACHEABLE types → hit: return early
  4. RAG pipeline: rag_pipeline(skip_rewrite=True for FAQ)
  5. Generate: generate_response(message=message) with streaming (#571: message forwarded for chunked edits)
  6. Post-process: double-send guard (response_sent), cache store (confidence/source/contextual guards), history save, Langfuse scores
```

**Embedding passthrough (#571):** Pre-agent computes dense+sparse+ColBERT in one `aembed_hybrid_with_colbert()` call. All three are stashed in `rag_result_store` (on both HIT and MISS) and passed to `rag_pipeline()` via `pre_computed_sparse`/`pre_computed_colbert` params, eliminating redundant BGE-M3 calls.

**`detect_agent_intent()`**: Regex/keyword detector for intents not covered by `classify_query()`:
- "ипотек", "кредит", "рассрочка" → `"mortgage"`
- "менеджер", "позвонить", "связаться" → `"handoff"`
- "сводка", "отчёт", "итог дня" → `"daily_summary"`

**`PipelineResult`** (`services/types.py`): Frozen dataclass with `answer`, `sources`, `query_type`, `cache_hit`, `needs_agent`, `agent_intent`, `latency_ms`, `llm_call_count`, `scores`, `pipeline_mode`, `sent_message`, `response_sent`.

**Cache store guards:**
- `query_type in _PIPELINE_STORE_TYPES` (FAQ, GENERAL, ENTITY — not STRUCTURED)
- Contextual follow-ups ("подробнее", "первый", "это", "ещё") → skip cache store
- `grade_confidence >= config.relevance_threshold_rrf` (RRF scale, default 0.005; fallback `_CONFIDENCE_THRESHOLD=0.005`)
- Empty documents → skip
- **Note:** `grade_confidence` is a RRF score (max ~0.016). The threshold must be on the same RRF scale, not cosine similarity [0-1].

## generate_response Service

**File:** `telegram_bot/services/generate_response.py` — shared LLM generation extracted from `generate_node`.

Called by both client direct pipeline (via bot.py) and voice LangGraph (via `generate_node` adapter in `graph/nodes/generate.py`).

```
generate_response(query, documents, message?, config?, ...) →
  1. Style detection (ResponseStyleDetector, ~0ms)
  2. System prompt (Langfuse Prompt Manager + style/citation/history injection)
  3. Build OpenAI-format messages (system + history + context + query)
  4. Streaming path: placeholder → stream chunks (300ms throttle) → finalize Markdown
     Non-streaming path: single completion call
  5. Fallback: document summary if LLM unavailable
  → Returns dict: response, response_sent, sent_message, latency_stages, style metrics
```

**Dependency injection:** All core functions passed as kwargs (format_context, build_system_prompt, generate_streaming, etc.) for testability. `generate_node` passes its own local implementations.

**Span:** `@observe(name="service-generate-response")` with curated input/output metadata.

## Streaming Delivery

When `STREAMING_ENABLED=true` (default), `generate_response` streams LLM output directly to Telegram: sends placeholder, edits with chunks (throttled 300ms), finalizes with Markdown parse_mode. Sets `response_sent=True` → `respond_node` skips duplicate send.

**Fallback:** If streaming fails, falls back to non-streaming LLM call. **Disable:** `STREAMING_ENABLED=false`.

## Middlewares

- **ThrottlingMiddleware:** `cachetools.TTLCache(maxsize=10_000, ttl=1.5s)`, admins bypass.
- **ErrorHandlerMiddleware:** Catches all exceptions, logs with `exc_info=True`, returns user-friendly message.
- **I18nMiddleware:** Loads user locale from DB (via `UserService`), injects `i18n` (FluentTranslator), `locale`, `property_bot`, `apartments_service` into handler data. i18n keys in `locales/{ru,uk,en}/messages.ftl`.

## Testing

```bash
pytest tests/unit/test_bot_handlers.py -v                # Bot handlers + client direct pipeline routing
pytest tests/unit/test_bot_menu_handlers.py -v           # Client menu: 47 tests for buttons, callbacks, FSM guard (#628)
pytest tests/unit/pipelines/test_client_pipeline.py -v   # Client pipeline: classify, intent, cache, RAG, generate
pytest tests/unit/test_middlewares.py -v
pytest tests/unit/graph/ -v                              # All graph tests (incl. test_transcribe_node.py)
pytest tests/unit/agents/ -v                             # Agent tests (factory, context, tools, CRM, history, streaming, skip_rewrite)
pytest tests/unit/services/test_generate_response.py -v  # Shared generation service
pytest tests/unit/dialogs/test_menu_routing.py -v        # Menu routing dialog tests
pytest tests/unit/keyboards/ -v                          # Keyboard builder tests
pytest tests/unit/handlers/test_phone_collector.py -v    # Phone collector FSM + CRM lead tests
pytest tests/unit/handlers/test_phone_crm_integration.py -v  # CRM integration tests (#628)
pytest tests/unit/dialogs/test_funnel.py -v              # Funnel dialog + hybrid search tests (#628)
pytest tests/unit/dialogs/test_funnel_results.py -v      # Funnel filter building + results getter (#628)
pytest tests/unit/services/test_content_loader_promotions.py -v  # Promotions config tests (#628)
pytest tests/unit/services/test_favorites_service.py -v  # Favorites service tests
pytest tests/integration/test_graph_paths.py -v          # Graph path tests incl. voice flow (~5s, no Docker)
pytest tests/smoke/test_langgraph_pipeline.py -v         # Smoke tests
```

**Graph path tests** (`test_graph_paths.py`): Cover all 6 `route_grade` branches with mocked services. No Docker required.

**phone_router singleton**: `phone_collector.py` has module-level `Router(name="phone_collector")`. Tests creating multiple PropertyBot instances need autouse fixture resetting `phone_router._parent_router = None`.

## Troubleshooting

| Error | Fix |
|-------|-----|
| Bot not responding | Check `docker logs dev-bot` |
| `TELEGRAM_BOT_TOKEN` invalid | Get new token from @BotFather |
| Services unhealthy | Run preflight: `from telegram_bot.preflight import check_dependencies` |

## CRM Integration (#384, #390, #402, #413)

### Agent CRM Tools (8 @tool, Kommo API v4)

| Tool | Span Name | Description |
|------|-----------|-------------|
| `crm_get_deal` | `crm-get-deal` | GET lead by ID |
| `crm_get_contacts` | `crm-get-contacts` | Search contacts by name/phone |
| `crm_create_lead` | `crm-create-lead` | POST new lead (name, budget, pipeline) |
| `crm_update_lead` | `crm-update-lead` | PATCH lead (name, budget, status) |
| `crm_upsert_contact` | `crm-upsert-contact` | Find by phone or create contact |
| `crm_add_note` | `crm-add-note` | POST note to lead/contact |
| `crm_create_task` | `crm-create-task` | POST follow-up task |
| `crm_link_contact_to_deal` | `crm-link-contact-to-deal` | Link contact to lead |

All tools check `ctx.kommo_client is not None` before proceeding. Enabled via `config.kommo_enabled`.

##***REMOVED*** Infrastructure (#413)

- **Client:** `telegram_bot/services/kommo_client.py` — `KommoClient` (async httpx, OAuth2 auto-refresh on 401)
- **Token store:** `telegram_bot/services/kommo_token_store.py` — `KommoTokenStore` (Redis hash, 5-min refresh buffer)
- **Models:** `telegram_bot/services/kommo_models.py` — Pydantic v2 (Lead, Contact, Note, Task, Pipeline, *Create, *Update)

### Lead Scoring

- **Store:** `telegram_bot/services/lead_scoring_store.py` — `LeadScoringStore` (asyncpg upsert, pending sync queue)
- **Models:** `telegram_bot/services/lead_scoring_models.py` — `LeadScoreRecord`, `LeadScoreSyncPayload`
- **DB tables:** `lead_scores` (with `sync_status`), `lead_score_sync_audit`
- **Lifecycle:** `HotLeadNotifier` wired in bot startup (#402)

### Nurturing & Funnel Analytics

- **Nurturing:** `telegram_bot/services/nurturing_service.py` — `NurturingService`
- **Scheduler:** `telegram_bot/services/nurturing_scheduler.py` — `NurturingScheduler` (APScheduler v3)
- **Funnel:** `telegram_bot/services/funnel_analytics_store.py` + `funnel_analytics_service.py`
- **DB tables:** `nurturing_jobs`, `funnel_metrics_daily`, `scheduler_leases` (distributed lock)

### CRM Config

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| — | `KOMMO_LEAD_SCORE_FIELD_ID` | — | Kommo custom field for lead score |
| — | `KOMMO_LEAD_BAND_FIELD_ID` | — | Kommo custom field for lead band |
| — | `NURTURING_ENABLED` | `false` | Enable nurturing scheduler |
| — | `NURTURING_INTERVAL_MINUTES` | — | Batch interval |
| — | `FUNNEL_ROLLUP_CRON` | — | Daily funnel metrics rollup |

### Langfuse Scores (CRM — `write_crm_scores()` #455)

| Score | Type | Purpose |
|-------|------|---------|
| `crm_tool_used` | BOOLEAN | Whether any CRM tool was called |
| `crm_tools_count` | NUMERIC | Number of CRM tool calls |
| `crm_tools_success` | NUMERIC | Successful CRM operations |
| `crm_tools_error` | NUMERIC | Failed CRM operations |
