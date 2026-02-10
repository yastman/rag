---
paths: "telegram_bot/*.py, telegram_bot/middlewares/**, telegram_bot/graph/**"
---

# Telegram Bot

LangGraph-based RAG pipeline with aiogram Telegram interface.

## Purpose

Telegram interface for domain-configurable search (default: Bulgarian property) with LangGraph StateGraph pipeline, streaming-compatible responses, and rate limiting.

## Architecture

```
User Message → ThrottlingMiddleware → ErrorMiddleware
            → PropertyBot.handle_query()
            → make_initial_state() → build_graph() → graph.ainvoke(state)
            → [classify → cache_check → retrieve → grade → rerank → generate → cache_store → respond]
            → Markdown Response (with plain text fallback)
```

## Key Files

| File | Description |
|------|-------------|
| `telegram_bot/bot.py` | PropertyBot class (~290 LOC, LangGraph pipeline + score writing) |
| `telegram_bot/main.py` | Entry point |
| `telegram_bot/config.py` | BotConfig (pydantic-settings BaseSettings) |
| `telegram_bot/graph/graph.py` | `build_graph()` — assembles 9-node StateGraph |
| `telegram_bot/graph/state.py` | RAGState TypedDict (17 fields incl. `rewrite_effective`) + `make_initial_state()` |
| `telegram_bot/graph/edges.py` | 3 routing functions (`route_grade` checks `rewrite_effective`) |
| `telegram_bot/graph/config.py` | GraphConfig dataclass (service factories, `rewrite_model`/`rewrite_max_tokens`) |
| `telegram_bot/graph/nodes/` | 8 node modules (classify, cache, retrieve, grade, rerank, generate, rewrite, respond) |
| `telegram_bot/observability.py` | `get_client()`, `@observe`, `propagate_attributes`, PII masking |
| `telegram_bot/middlewares/throttling.py` | ThrottlingMiddleware |
| `telegram_bot/middlewares/error_handler.py` | ErrorHandlerMiddleware |

## LangGraph Pipeline (9 nodes)

```
START → classify → [CHITCHAT/OFF_TOPIC] → respond → END
                 → [other] → cache_check → [HIT] → respond → END
                                          → [MISS] → retrieve → grade
                                                       → [relevant] → rerank → generate → cache_store → respond → END
                                                       → [retries < 2 AND effective] → rewrite → retrieve (loop)
                                                       → [retries >= 2] → generate → cache_store → respond → END
```

### Nodes

| Node | File | Injected Deps |
|------|------|---------------|
| classify | `graph/nodes/classify.py` | — (regex-based, no external deps) |
| cache_check | `graph/nodes/cache.py` | cache, embeddings |
| retrieve | `graph/nodes/retrieve.py` | cache, sparse_embeddings, qdrant |
| grade | `graph/nodes/grade.py` | — (score threshold 0.3) |
| rerank | `graph/nodes/rerank.py` | reranker (ColBERT or None) |
| generate | `graph/nodes/generate.py` | — (uses GraphConfig.create_llm) |
| rewrite | `graph/nodes/rewrite.py` | llm (optional, uses `config.rewrite_model`/`rewrite_max_tokens`) |
| cache_store | `graph/nodes/cache.py` | cache |
| respond | `graph/nodes/respond.py` | message (aiogram Message, injected) |

### Edges (conditional routing)

| Function | From → To |
|----------|-----------|
| `route_by_query_type` | classify → respond (CHITCHAT/OFF_TOPIC) or cache_check |
| `route_cache` | cache_check → respond (hit) or retrieve (miss) |
| `route_grade` | grade → rerank (relevant), rewrite (retry < 2 AND `rewrite_effective`), generate (fallback) |

## Bot Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | cmd_start | Welcome message (domain from config) |
| `/help` | cmd_help | Usage instructions |
| `/clear` | cmd_clear | Clear conversation history |
| `/stats` | cmd_stats | Cache tier hit rates |
| `/metrics` | cmd_metrics | Pipeline p50/p95 timing |

## Configuration (BotConfig)

pydantic-settings `BaseSettings` with `.env` file support and `AliasChoices` for env vars:

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `telegram_token` | `TELEGRAM_BOT_TOKEN` | — | Bot token |
| `domain` | `BOT_DOMAIN` | `недвижимость` | Domain topic |
| `domain_language` | `BOT_LANGUAGE` | `ru` | Response language |
| `rerank_provider` | `RERANK_PROVIDER` | `voyage` | colbert / none / voyage |
| `admin_ids` | `ADMIN_IDS` | [] | Comma-separated Telegram IDs |

## Service Dependencies (initialized in PropertyBot.__init__)

```python
self._cache = CacheLayerManager(redis_url=config.redis_url)
self._embeddings = BGEM3Embeddings(base_url=config.bge_m3_url)
self._sparse = BGEM3SparseEmbeddings(base_url=config.bge_m3_url)
self._qdrant = QdrantService(url=config.qdrant_url, ...)
self._reranker = ColbertRerankerService(...)  # if rerank_provider == "colbert"
self._llm = self._graph_config.create_llm()   # langfuse.openai.AsyncOpenAI
```

## handle_query Flow

```python
state = make_initial_state(user_id, session_id, query)
with propagate_attributes(session_id=..., user_id=..., tags=["telegram", "rag"]):
    graph = build_graph(cache, embeddings, sparse, qdrant, reranker, llm, message)
    async with ChatActionSender.typing(...):
        result = await graph.ainvoke(state)
    lf = get_client()
    lf.update_current_trace(input=..., output=..., metadata=...)
    _write_langfuse_scores(lf, result)  # 12 scores
```

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
pytest tests/unit/test_bot.py -v
pytest tests/unit/test_middlewares.py -v
pytest tests/unit/graph/ -v                              # All graph unit tests (~124 tests)
pytest tests/integration/test_graph_paths.py -v          # 6 graph path integration tests (~5s, no Docker)
pytest tests/smoke/test_langgraph_pipeline.py -v         # Smoke tests
```

**Graph path tests** (`test_graph_paths.py`): Cover all 6 `route_grade` branches with mocked services. No Docker required.

## Troubleshooting

| Error | Fix |
|-------|-----|
| Bot not responding | Check `docker logs dev-bot` |
| `TELEGRAM_BOT_TOKEN` invalid | Get new token from @BotFather |
| Services unhealthy | Run preflight: `from telegram_bot.preflight import check_dependencies` |

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
