---
paths: "telegram_bot/*.py, telegram_bot/middlewares/**, telegram_bot/graph/**, telegram_bot/agents/**"
---

# Telegram Bot

Async RAG pipeline + LangGraph voice path with aiogram Telegram interface.

## Purpose

Telegram interface for domain-configurable search (default: Bulgarian property) with async RAG pipeline (#442), LangGraph voice path, streaming-compatible responses, and rate limiting.

## Architecture

```
Text:  User Message → ThrottlingMiddleware → ErrorMiddleware
                   → PropertyBot.handle_query()
                   → _handle_query_supervisor()
                   → create_bot_agent(model, tools, context_schema=BotContext)
                   → Agent LLM → tool_choice (rag_search | history_search | 8 CRM tools | direct)
                   → tool executes (deps via BotContext DI) → respond
                   → Langfuse: CallbackHandler + @observe spans

Voice: Voice Message → PropertyBot.handle_voice()
                    → download .ogg → make_initial_state(voice_audio=bytes)
                    → [transcribe → classify → ... same pipeline]
                    → Markdown Response
```

## Key Files

| File | Description |
|------|-------------|
| `telegram_bot/bot.py` | PropertyBot class (agent orchestrator + voice handler) |
| `telegram_bot/scoring.py` | `write_langfuse_scores()` + `write_crm_scores()` (#440) |
| `telegram_bot/main.py` | Entry point |
| `telegram_bot/config.py` | BotConfig (pydantic-settings BaseSettings) |
| `telegram_bot/agents/rag_pipeline.py` | `rag_pipeline()` — 6-step async pipeline: cache → retrieve → grade → rerank → rewrite → cache_store (#442) |
| `telegram_bot/graph/graph.py` | `build_graph()` — 11-node StateGraph (voice path, legacy) |
| `telegram_bot/graph/state.py` | RAGState TypedDict (25 fields incl. voice_audio, stt_text, input_type) + `make_initial_state()` |
| `telegram_bot/graph/edges.py` | 4 routing functions (`route_start` voice→transcribe/classify, `route_grade` checks `grade_confidence`) |
| `telegram_bot/graph/config.py` | GraphConfig dataclass (service factories, `show_transcription`, `voice_language`, `stt_model`, `streaming_enabled`) |
| `telegram_bot/graph/nodes/` | 9 node modules (transcribe, classify, cache, retrieve, grade, rerank, generate, rewrite, respond) |
| `telegram_bot/agents/agent.py` | `create_bot_agent()` — wraps `langchain.agents.create_agent` SDK (#413) |
| `telegram_bot/agents/context.py` | `BotContext` dataclass (13 fields) — DI via `context_schema` into tools |
| `telegram_bot/agents/rag_tool.py` | `rag_search` @tool — wraps `rag_pipeline()` (#442), returns formatted context |
| `telegram_bot/agents/history_tool.py` | `history_search` @tool — wraps 5-node history sub-graph (with guard #432) |
| `telegram_bot/agents/crm_tools.py` | 8 CRM @tools for Kommo API (get/create/update deals, contacts, notes, tasks) |
| `telegram_bot/agents/history_graph/` | History sub-graph: guard → retrieve → grade → rewrite → summarize (5 nodes #432) |
| `telegram_bot/observability.py` | `get_client()`, `@observe`, `propagate_attributes`, `create_callback_handler`, PII masking |
| `telegram_bot/middlewares/throttling.py` | ThrottlingMiddleware |
| `telegram_bot/middlewares/error_handler.py` | ErrorHandlerMiddleware |

## LangGraph Pipeline (11 nodes)

```
START → [voice_audio?] → transcribe → guard → classify → ...
      → [text]         → guard → classify → ...

guard → [injection_detected] → respond (blocked message) → END
      → [clean] → classify → ...

START → classify → [CHITCHAT/OFF_TOPIC] → respond → END
                 → [other] → cache_check → [HIT] → respond → END
                                          → [MISS] → retrieve → grade
                                                       → [relevant + confidence >= 0.012] → generate → cache_store → respond → END (skip rerank)
                                                       → [relevant + confidence < 0.012] → rerank → generate → cache_store → respond → END
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
| generate | `graph/nodes/generate.py` | message (aiogram Message, for streaming; uses GraphConfig.create_llm) |
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
| `/start` | cmd_start | Welcome message (domain from config) |
| `/help` | cmd_help | Usage instructions |
| `/clear` | cmd_clear | Clear conversation history |
| `/stats` | cmd_stats | Cache tier hit rates |
| `/metrics` | cmd_metrics | Pipeline p50/p95 timing |
| (callback) | handle_feedback | Like/dislike feedback (#229) |

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
| `kommo_enabled` | `KOMMO_ENABLED` | `false` | Enable Kommo CRM tools in agent |
| `streaming_enabled` | `STREAMING_ENABLED` | `true` | Stream LLM output to Telegram via edit_text |
| `show_transcription` | `SHOW_TRANSCRIPTION` | `true` | Show transcribed text before RAG response |
| `voice_language` | `VOICE_LANGUAGE` | `ru` | Whisper language hint (ISO code) |
| `stt_model` | `STT_MODEL` | `whisper` | LiteLLM model name for STT |

### GraphConfig (pipeline tuning)

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `skip_rerank_threshold` | `SKIP_RERANK_THRESHOLD` | `0.012` | Skip rerank when grade confidence >= threshold (RRF scale) |
| `max_rewrite_attempts` | `MAX_REWRITE_ATTEMPTS` | `1` | Max query rewrites before fallback |
| `generate_max_tokens` | `GENERATE_MAX_TOKENS` | `2048` | Token cap for LLM generation |
| `rewrite_max_tokens` | `REWRITE_MAX_TOKENS` | `64` | Token budget for rewrite LLM call |
| `rewrite_model` | `REWRITE_MODEL` | `gpt-4o-mini` | Model for rewrites |
| `bge_m3_timeout` | `BGE_M3_TIMEOUT` | `120.0` | BGE-M3 API timeout (seconds) |
| `guard_mode` | `GUARD_MODE` | `hard` | Content filter mode: hard (block), soft (flag+continue), log (log only) |
| `content_filter_enabled` | `CONTENT_FILTER_ENABLED` | `true` | Enable/disable guard_node entirely |

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

```python
# Download .ogg → bytes → inject into state
voice = message.voice
file = await bot.get_file(voice.file_id)
buf = io.BytesIO()
await bot.download_file(file.file_path, destination=buf)

state = make_initial_state(user_id, session_id, query="")
state["voice_audio"] = buf.getvalue()
state["voice_duration_s"] = float(voice.duration)
state["input_type"] = "voice"

# Same graph.ainvoke(state) — transcribe_node runs first via route_start
```

**Error handling:** Empty transcription → "Голосовое не содержит речи." | API error → "Не удалось распознать. Попробуйте текстом."

**Langfuse scores:** `input_type` (CATEGORICAL), `stt_duration_ms` (NUMERIC), `voice_duration_s` (NUMERIC)

## handle_query Flow (create_agent SDK since #413)

```python
# handle_query always delegates to _handle_query_supervisor
# 1. Build tools list
tools = [rag_search]  # @tool from agents/rag_tool.py
if history_service: tools.append(history_search)  # @tool from agents/history_tool.py
if kommo_enabled: tools.extend(get_crm_tools())   # 8 @tools from agents/crm_tools.py

# 2. Create agent via SDK
agent = create_bot_agent(model=config.supervisor_model, tools=tools, checkpointer=...)

# 3. Build BotContext for DI (injected into tools via context_schema)
ctx = BotContext(telegram_user_id=..., session_id=..., kommo_client=..., embeddings=..., ...)

# 4. Invoke with CallbackHandler for Langfuse
langfuse_handler = create_callback_handler()
result = await agent.ainvoke(
    {"messages": [HumanMessage(content=query)]},
    config={"configurable": {"bot_context": ctx}, "callbacks": [langfuse_handler]},
)
```

**Tools (all @tool decorated, deps via BotContext):**
- `rag_search` — wraps `build_graph().ainvoke()` (11-node RAG pipeline), @observe("tool-rag-search")
- `history_search` — wraps `build_history_graph().ainvoke()` (4-node sub-graph), @observe("tool-history-search")
- 8 CRM tools — `crm_get_deal`, `crm_create_lead`, `crm_update_lead`, `crm_upsert_contact`, `crm_add_note`, `crm_create_task`, `crm_link_contact_to_deal`, `crm_get_contacts`

**Runtime context:** Tools receive `BotContext` via `config["configurable"]["bot_context"]` (context_schema DI).

**Score writing:** RAG pipeline scores (14 metrics) are written inside `rag_search` tool via `write_langfuse_scores()` from `telegram_bot/scoring.py`.

## Streaming Delivery

When `STREAMING_ENABLED=true` (default), `generate_node` streams LLM output directly to Telegram:

1. Sends placeholder message (`⏳ Генерирую ответ...`)
2. Edits message with accumulated chunks (throttled 300ms via `edit_text`)
3. Finalizes with Markdown parse_mode (plain text fallback)
4. Sets `response_sent=True` → `respond_node` skips duplicate send

**Fallback:** If streaming fails at any point, falls back to non-streaming LLM call. `respond_node` handles delivery normally.

**Disable:** `STREAMING_ENABLED=false` in env or `GraphConfig(streaming_enabled=False)`.

**Graph wiring:** `_make_generate_node(message)` injects aiogram Message into generate_node (same pattern as `_make_respond_node`).

## Middlewares

### ThrottlingMiddleware

Rate limiting: `cachetools.TTLCache(maxsize=10_000, ttl=1.5s)`, admins bypass.

### ErrorHandlerMiddleware

Catches all exceptions, logs with `exc_info=True`, returns user-friendly message.

## Dependencies

- Container: `dev-bot` / `vps-bot`, 512MB RAM
- Requires: redis, qdrant, litellm, bge-m3

## Testing

```bash
pytest tests/unit/test_bot_handlers.py -v
pytest tests/unit/test_middlewares.py -v
pytest tests/unit/graph/ -v                              # All graph tests (incl. test_transcribe_node.py)
pytest tests/unit/agents/ -v                             # Agent tests (factory, context, tools, CRM, history, streaming)
pytest tests/integration/test_graph_paths.py -v          # Graph path tests incl. voice flow (~5s, no Docker)
pytest tests/smoke/test_langgraph_pipeline.py -v         # Smoke tests
```

**Graph path tests** (`test_graph_paths.py`): Cover all 6 `route_grade` branches with mocked services. No Docker required.

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

### Kommo Infrastructure (#413)

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

### Langfuse Scores (CRM)

| Score | Type | Purpose |
|-------|------|---------|
| `nurturing_batch_size` | NUMERIC | Total leads in nurturing batch |
| `nurturing_sent_count` | NUMERIC | Successfully sent nurturing messages |
| `funnel_conversion_rate` | NUMERIC | Stage conversion rate |
| `funnel_dropoff_rate` | NUMERIC | Stage dropoff rate |

## Development Guide

### Adding new command

1. Add handler method to `PropertyBot`:
```python
async def cmd_newcmd(self, message: Message):
    await message.answer("Response")
```

2. Register in `_register_handlers()`:
```python
self.dp.message(Command("newcmd"))(self.cmd_newcmd)
```

### Adding new graph node

1. Create module in `telegram_bot/graph/nodes/`
2. Define async function with `state: dict[str, Any]` signature
3. Return partial state update dict
4. Add to `build_graph()` in `graph/graph.py` with `functools.partial` for deps
5. Add edges in `graph/graph.py`
6. Write tests in `tests/unit/graph/`
