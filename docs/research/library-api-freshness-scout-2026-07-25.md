# Python library API freshness scout — 2026-07-25

## Scope and method

Source-verified comparison of active `rag-fresh` callsites with locked dependency versions and current first-party documentation retrieved through Context7. Code locations and call paths came from CodeGraph/CodeIndexer; versions came from `uv.lock`. The target remains one deployable Python process with in-process module calls. This report does not propose microservices or a second orchestration centre.

Terms:

- **Deprecated/removed**: first-party API marks the usage obsolete or unavailable.
- **Contract issue**: project wiring contradicts the documented API contract even when the called API itself remains current.
- **Cleanup**: no compatibility or runtime defect.

## Verdict

No active deprecated or removed API was found in Qdrant, aiogram, aiogram-dialog, LiteLLM, OpenAI, Redis, RedisVL, Docling, Docling Core, Pydantic, pydantic-settings, HTTPX, or Tenacity usage. The code is unusually current for the locked dependency set.

Three actionable integration issues remain:

1. RedisVL's declared minimum is older than the import layout used by the code.
2. LangGraph checkpointer/thread wiring is dead after the text agent became an imperative core facade; the apparent persistence contract is false.
3. Bot startup performs the same Telegram `getMe` request twice.

## Locked versions

| Component | Locked version |
|---|---:|
| qdrant-client | 1.18.0 |
| aiogram | 3.29.1 |
| aiogram-dialog | 2.6.0 |
| litellm | 1.91.0 |
| openai | 2.44.0 |
| redis | 7.4.1 |
| redisvl | 0.23.0 |
| docling | 2.110.0 |
| docling-core | 2.86.0 |
| langgraph | 1.2.7 |
| langchain-core | 1.4.8 |
| pydantic | 2.13.4 |
| pydantic-settings | 2.14.2 |
| httpx | 0.28.1 |
| tenacity | 9.1.4 |

## Actionable findings

### 1. RedisVL declared minimum is compatible

- **Severity:** no issue.
- **Callsites:** `pyproject.toml:12`, `telegram_bot/pyproject.toml:73`; imports and cache setup in `src/runtime/integrations/cache.py`.
- **Verified state:** official RedisVL tag `v0.18.2` exports `SemanticCache` from `redisvl.extensions.cache.llm` and `EmbeddingsCache` from `redisvl.extensions.cache.embeddings`. Its method and async-client ownership contracts cover the project's `acheck`/`astore`/`aget`/`aset` calls and injected async client.
- **Impact:** `redisvl>=0.18.2` matches the code; no floor change is needed. Compatibility below 0.18.2 was not investigated.
- **Action:** keep the existing minimum and locked 0.23.0. Do not add a compatibility branch.
- **Primary sources:** [RedisVL v0.18.2 tag](https://github.com/redis/redis-vl-python/tree/v0.18.2), [v0.18.2 SemanticCache export](https://raw.githubusercontent.com/redis/redis-vl-python/v0.18.2/redisvl/extensions/cache/llm/__init__.py), [v0.18.2 EmbeddingsCache export](https://raw.githubusercontent.com/redis/redis-vl-python/v0.18.2/redisvl/extensions/cache/embeddings/__init__.py), and [current RedisVL cache API](https://redis.io/docs/latest/develop/ai/redisvl/api/cache).

### 2. LangGraph persistence parameters are dead wiring

- **Severity:** medium contract/maintenance issue.
- **Callsites:** `telegram_bot/agents/agent.py:52-116,236-269`, `telegram_bot/integrations/memory.py:28-77,309-345`, `telegram_bot/lifecycle/lifecycle.py:207-249`, `telegram_bot/pipeline/supervisor.py:1058-1164`.
- **Current state:** `create_bot_agent(checkpointer=...)` explicitly discards `checkpointer`; `ImperativeBotAgent` is not a compiled LangGraph and ignores `thread_id`. `create_redis_checkpointer()` always raises; fallback `MemorySaver` is a project-local no-op saver whose methods return `None`.
- **Documented contract:** LangGraph checkpoint persistence requires compiling a graph with a checkpointer and invoking it with `configurable.thread_id`. `MemorySaver` is for in-memory development and does not persist across runs.
- **Impact:** code and tests imply conversation checkpointing, but the live imperative text-agent path has none.
- **Minimal monolith fix:** remove `checkpointer`, `thread_id`, no-op saver, fallback, and tests that assert pass-through. Keep real conversation state in the existing monolith-owned history path. Add `AsyncPostgresSaver` only if restart-safe graph persistence becomes an explicit product requirement and a real StateGraph consumes it.
- **Primary source:** [LangGraph checkpoints](https://reference.langchain.com/python/langgraph/checkpoints) and [StateGraph.compile](https://reference.langchain.com/python/langgraph/graph/state/StateGraph/compile) (Context7 `/websites/reference_langchain_python_langgraph`).

### 3. Telegram bot identity performs duplicate network calls

- **Severity:** low.
- **Callsite:** `telegram_bot/lifecycle/lifecycle.py:339-359`.
- **Current state:** startup awaits cached `bot.me()`, then immediately calls uncached `bot.get_me()` for the same `User` fields.
- **Documented contract:** `Bot.me()` is the cached alias for Telegram `getMe`; returned `User` already carries `has_topics_enabled`.
- **Impact:** one unnecessary Telegram API round-trip on every startup; split exception handling can leave `_bot_user_id` and topic capability derived from different calls.
- **Minimal fix:** call `me = await bot.bot.me()` once and populate both fields from that object.
- **Primary source:** [aiogram Bot API](https://docs.aiogram.dev/en/latest/api/bot.html) (Context7 `/websites/aiogram_dev_en`).

## Monitor, do not change now

### RedisVL SemanticCache private async-client injection

`src/runtime/integrations/cache.py` assigns private `_async_redis_client` and `_owns_redis_client` fields because RedisVL 0.23 `SemanticCache` accepts a synchronous `redis_client` or URL but no public `async_redis_client` constructor parameter. `EmbeddingsCache` does expose the async parameter. Current workaround works for 0.23.0, but private fields are upgrade-sensitive. Keep it isolated in the existing constructor helper; replace only when RedisVL publishes a public async-client parameter.

### LiteLLM/OpenAI token parameter

Current models and LiteLLM 1.91 accept the project's `max_tokens` calls. OpenAI marks `max_tokens` deprecated/incompatible for o-series reasoning models in favour of `max_completion_tokens`. No current callsite is broken because the active OpenAI fallback is `gpt-4o-mini`. Before adopting an o-series model, normalize this through the existing router rather than adding per-caller branches.

Primary sources: [LiteLLM Router](https://docs.litellm.ai/docs/routing) (Context7 `/berriai/litellm`) and [OpenAI Python SDK](https://github.com/openai/openai-python) (Context7 `/openai/openai-python`).

## Verified current APIs — no migration

### Qdrant 1.18.0

Current and correct: `query_points`, `query_points_groups`, `query_batch_points`, nested `Prefetch`, `RrfQuery`, `SearchParams`, `scroll(scroll_filter=...)`, `upsert`, `delete`, `count`, `update_vectors`, aliases, `field_schema`, named dense/sparse/ColBERT vectors, scalar/binary quantization, and async `close()`.

Known obsolete APIs have zero callsites: `search()`, `recreate_collection()`, `grpc.PointStruct`, and payload-index `field_type`.

Primary source: [Qdrant Python client](https://python-client.qdrant.tech/) and [hybrid queries](https://qdrant.tech/documentation/concepts/hybrid-queries/) (Context7 `/qdrant/qdrant-client`).

### aiogram 3.29.1 / aiogram-dialog 2.6.0

Current and correct: Router/Dispatcher registration, error handlers, `BaseMiddleware`, FSMContext, CallbackData filters, forum-topic methods, `send_message_draft`, `reply_parameters`, `DialogManager`, `StartMode.RESET_STACK`, `Window`, managed widgets, and `setup_dialogs`.

`telegram_bot/services/generation/telegram_formatting.py:58-60` contains an always-`None` `build_reply_parameters()` helper. This is dead indirection, not an API problem; delete it when touching delivery code.

Primary sources: [aiogram documentation](https://docs.aiogram.dev/en/latest/) and [aiogram-dialog documentation](https://aiogram-dialog.readthedocs.io/en/stable/).

### LiteLLM 1.91.0 / OpenAI 2.44.0

Current and correct: `Router`, `Router.acompletion`, fallbacks, async chat completions, streaming `choices[0].delta.content`, final-chunk usage with `stream_options.include_usage`, reasoning kwargs via `extra_body`, provider/model naming, timeout/retry parameters, and exception imports.

Primary sources: [LiteLLM documentation](https://docs.litellm.ai/) and [OpenAI Python SDK](https://github.com/openai/openai-python).

### Redis 7.4.1 / RedisVL 0.23.0

Current and correct: `redis.asyncio`, `from_url`, `aclose`, Retry/ExponentialBackoff, async `scan_iter`, Streams `xadd`, RedisVL `acheck`/`astore`/`aclear`/`adisconnect`, EmbeddingsCache `aget`/`aset`, and Tag filter expressions.

Primary sources: [redis-py asyncio examples](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html) and [RedisVL cache API](https://redis.io/docs/latest/develop/ai/redisvl/api/cache).

### Docling 2.110.0 / Docling Core 2.86.0

Current and correct: in-process `DocumentConverter`, `InputFormat.PDF`, `PdfFormatOption`, `PdfPipelineOptions`, `ConversionResult.document`, `HybridChunker`, `chunk(dl_doc=...)`, `contextualize`, HuggingFaceTokenizer, and current chunk metadata. Project does not use deprecated `serialize()` or `DocMeta.captions`.

Primary sources: [Docling documentation](https://docling-project.github.io/docling/) and [Docling chunking](https://docling-project.github.io/docling/concepts/chunking/) (Context7 `/docling-project/docling`, `/docling-project/docling-core`).

### Pydantic 2.13.4 / pydantic-settings 2.14.2

Current v2 throughout: `model_config`, `ConfigDict`, `SettingsConfigDict`, `field_validator`, `model_validator`, `model_dump`, `model_validate`, `TypeAdapter`, `model_copy`, `AliasChoices`, and `NoDecode`. No v1 `validator`, `root_validator`, `dict`, `json`, `parse_obj`, inner `Config`, or old BaseSettings import remains.

Primary sources: [Pydantic migration guide](https://docs.pydantic.dev/latest/migration/) and [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) (Context7 `/pydantic/pydantic`, `/pydantic/pydantic-settings`).

### HTTPX 0.28.1 / Tenacity 9.1.4

Current and correct: Client/AsyncClient constructors, Timeout/Limits, async auth flow, streaming requests, `close`/`aclose`, transport exceptions, retry decorators, exception predicates, exponential jitter, stop policies, and before-sleep logging. Project does not use removed HTTPX `proxies=`; it uses no explicit proxy parameter.

Primary sources: [HTTPX API](https://www.python-httpx.org/api/) (Context7 `/encode/httpx`) and [Tenacity API](https://tenacity.readthedocs.io/en/latest/api.html) (Context7 `/jd/tenacity`).

## Recommended order

1. Keep the RedisVL minimum unchanged; official 0.18.2 sources prove compatibility.
2. Delete dead checkpointer/thread plumbing from the imperative text-agent path. Do not replace it with infrastructure unless persistence has an explicit acceptance criterion.
3. Merge duplicate Telegram identity call.
4. Leave all other library callsites unchanged. Current APIs are not the project's main risk; correctness findings from the runtime/ingestion audit remain higher priority.
