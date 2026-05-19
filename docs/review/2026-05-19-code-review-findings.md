# 2026-05-19 Code Review — Findings & Issue Drafts

This document is the deliverable of a line-by-line code review of `yastman/rag` performed on 2026-05-19. It is intended as a **launch pad for new GitHub Issues**: each section below is a self-contained issue body that can be published with one click. Cross-checked against the current 80+ open issues so nothing is a duplicate.

The accompanying PR also includes one concrete code fix (the highest-severity `asyncio.get_event_loop()` bug in production) — see `telegram_bot/integrations/embeddings.py` in the diff.

## Layout

1. **Production bugs** — concrete, reproducible defects (PROD-001 … PROD-008)
2. **SDK migration** — replace custom code with SDK-native solutions (SDK-001 … SDK-018)
3. **Recommended order** — pragmatic execution sequence

Each finding has:
- Severity, type, file:line range
- Reproduction or current pattern
- Suggested fix
- `not_duplicate_of` cross-checked against open issues

---

## Part 1 — Production bugs (PROD-001 … PROD-008)

### PROD-001 — `asyncio.get_event_loop()` in production breaks on Python 3.13

**Severity:** High · **Type:** bug · **Files:** `telegram_bot/integrations/embeddings.py:59,62,179,182`, `src/core/pipeline.py:119,130`, `src/ingestion/cocoindex_flow.py:118`, `src/ingestion/indexer.py:381`

5 production files use deprecated `asyncio.get_event_loop()`. The Dockerfiles target Python 3.13:

- Outside an active loop in 3.12+ → `DeprecationWarning`; in 3.15+ → `RuntimeError`.
- **Inside an active loop**, `loop.run_until_complete()` immediately raises `RuntimeError: This event loop is already running`. This affects the sync wrappers `BGEM3Embeddings.embed_documents/embed_query` and `BGEM3HybridEmbeddings.embed_documents/embed_query`, both of which subclass `langchain_core.embeddings.Embeddings` and may be called from any LangChain sync path.

**Fix.** Sync wrappers in `embeddings.py`: drop the methods (LangChain supports async-only embedders) — already partially applied in this PR. For `pipeline.py`, `cocoindex_flow.py`, `indexer.py` `run_in_executor` call sites, replace with `asyncio.get_running_loop()` or simpler `await asyncio.to_thread(fn, *args)`.

**Not a duplicate of #1515 (B1).** That issue covers only `tests/smoke/conftest.py:62`.

---

### PROD-002 — `datetime.utcnow()` deprecated in 3.12, removed in 3.15

**Severity:** Medium · **Type:** bug · **Files:** `scripts/e2e/runner.py:60` (primary); also `src/evaluation/ragas_evaluation.py:322,324,340`, `src/evaluation/run_ab_test.py:205`, `src/evaluation/metrics_logger.py:236`, `tests/baseline/collector.py:254`, `scripts/eval/run_experiment.py:153` (alignment)

`datetime.utcnow()` returns a **naive** datetime; comparing it to timezone-aware datetimes from Langfuse SDK ≥4 silently misbehaves. Will be removed in Python 3.15.

**Fix.** Replace with `datetime.now(UTC)` (`from datetime import UTC, datetime`) at all call sites; align other naive `datetime.now()` calls listed above to consistent UTC-aware timestamps.

**Not a duplicate of #1381** (Pydantic V1 warning).

---

### PROD-003 — `mini_app/api.py` CORS wide-open + missing initData verification + raw `print()` log endpoint

**Severity:** High (security) · **Type:** security · **Files:** `mini_app/api.py:21-25,43-91,95-103`

Three real issues in the mini-app FastAPI service:

1. `CORSMiddleware(allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])` — the API issues Telegram deep-links containing user PII; a wildcard origin allows any site to call `/api/start-expert` and `/api/phone` from the user's browser session.
2. `/api/start-expert` and `/api/phone` accept `user_id` / `query_id` straight from the request body without verifying the Telegram WebApp `initData` HMAC. Any caller can forge calls for arbitrary users.
3. `/api/log` uses `print(f"[REMOTE:{level}] {message} {data or ''}", flush=True)` with no whitelist on `level`, no size cap on `message`/`data`, and no rate limit — log injection + flood vector.

**Fix.** Restrict CORS to expected Telegram WebApp origins. Add an `initData` HMAC verifier (Telegram WebApp algorithm with the bot token as key) as a FastAPI dependency on PII-bearing endpoints. Replace `print()` with `logging.getLogger("mini_app.remote").log(...)` using the project formatter; truncate `message` to ≤4 KB and `data` to ≤16 KB; enforce a per-IP rate limit.

**Not a duplicate of #1239** (which only covers pub/sub reliability), nor #1236 (RAG API exception handler).

---

### PROD-004 — `BGEM3Client._get_client()` race window can leak `httpx.AsyncClient`

**Severity:** Medium · **Type:** bug / resource leak · **Files:** `telegram_bot/services/bge_m3_client.py:101-110`

```python
def _get_client(self) -> httpx.AsyncClient:
    if self._client is None or self._client.is_closed:
        self._client = httpx.AsyncClient(...)
    return self._client
```

The check-then-set is not atomic. Two coroutines that hit it simultaneously after a close (e.g. during reconnect) both observe `self._client.is_closed == True`, both create a new `AsyncClient`, and the first one is overwritten without `await ...aclose()`, leaking a TCP pool.

**Fix.** Wrap in an `asyncio.Lock` initialized in `__init__`, or atomically replace via `client = self._client; if client is None or client.is_closed: client = httpx.AsyncClient(...); old, self._client = self._client, client; if old and not old.is_closed: await old.aclose()`. The `Lock` variant is simpler.

**Not a duplicate of #1095** (retry decorators).

---

### PROD-005 — `re.compile()` inside hot-path loop in `query_preprocessor.py`

**Severity:** Low · **Type:** optimization · **Files:** `telegram_bot/services/query_preprocessor.py:191-193`

```python
for latin, cyrillic in self.TRANSLIT_MAP.items():
    pattern = re.compile(re.escape(latin), re.IGNORECASE)
    normalized = pattern.sub(cyrillic, normalized)
```

`TRANSLIT_MAP` is static, but the regex is recompiled on every query. With `len(TRANSLIT_MAP)` patterns × queries-per-second, this is wasted CPU.

**Fix.** Pre-compile a single combined regex at module level: `_TRANSLIT_RE = re.compile("|".join(re.escape(k) for k in sorted(TRANSLIT_MAP, key=len, reverse=True)), re.IGNORECASE)` and `_TRANSLIT_RE.sub(lambda m: TRANSLIT_MAP[m.group(0).lower()], text)`. Single pass instead of N passes.

**No overlap.**

---

### PROD-006 — `asyncio.create_task(...)` without storing reference (potential GC)

**Severity:** Medium · **Type:** concurrency bug · **Files:** `telegram_bot/bot.py:3653` (`# noqa: RUF006` suppresses Ruff but doesn't fix the issue)

```python
asyncio.create_task(_bg_save_history(), name=f"history-save-{user_id}")  # noqa: RUF006
```

[Python docs](https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task): *"Save a reference to the result of this function, to avoid a task disappearing mid-execution."* The task may be GC'd before `_bg_save_history()` finishes a long write to Postgres / Redis.

**Fix.** Add `self._history_save_tasks: set[asyncio.Task] = set()` to `PropertyBot.__init__`, then `task = asyncio.create_task(...); self._history_save_tasks.add(task); task.add_done_callback(self._history_save_tasks.discard)`. Same pattern already in use for `_BACKGROUND_TASKS` in `funnel.py`.

**Not a duplicate of #1541** (which actually proposes *removing* `_BACKGROUND_TASKS`, opposite direction).

---

### PROD-007 — `bge-m3-api` `/encode/*` batches die whole on a single failure

**Severity:** Medium · **Type:** bug · **Files:** `services/bge-m3-api/app.py` `/encode/dense`, `/encode/sparse`, `/encode/colbert`, `/encode/hybrid` handlers

The encode endpoints take `texts: list[str]` and run a single `model.encode(texts, ...)` call. If one input causes a tokenizer/CUDA error (e.g. unusual character, oversized input that slipped past `max_length` truncation), the entire batch raises HTTP 500 and the bot falls back to fallback responses.

**Fix.** Wrap inputs in a try/except per text only after tokenizer-level validation (length, encoding). For the rest, rely on FlagEmbedding's batch path. On `UnicodeError`/`ValueError`, return a sentinel zero-vector for the offending index and 200 OK for the rest, with a `partial_failures: [{"index": i, "error": "..."}]` field in the response.

**No overlap.**

---

### PROD-008 — Reranker variable in `src/api/main.py` is dead — only logs, never assigned

**Severity:** Low · **Type:** dead-code · **Files:** `src/api/main.py:64-67` (approx — the `if cfg.rerank_provider == "colbert": logger.info(...)` block)

`reranker = None` then an `if/elif` that only logs without ever assigning a reranker — confusing dead code. The `colbert` branch is silent because reranking is done server-side by Qdrant; the variable is misleading.

**Fix.** Remove `reranker` variable and the `if/elif`, keep one startup `logger.info("Reranking via server-side Qdrant ColBERT path")` only when `cfg.rerank_provider == "colbert"`.

**No overlap.**

---

## Part 2 — SDK migration targets (SDK-001 … SDK-018)

> Goal: replace custom code with SDK-native solutions. Each item names the exact SDK API (with package + version) and the migration path.

### SDK-001 — Replace manual OTEL setup in voice agent with Langfuse SDK initialization

**Severity:** Medium · **Type:** custom-vs-sdk · **Files:** `src/voice/agent.py:246-281`

`_setup_langfuse` builds `OTLPSpanExporter` + `TracerProvider` + `BatchSpanProcessor` by hand and base64-encodes credentials into the OTEL `Authorization` header. Langfuse 4.x ships first-class OTEL bootstrap; `telegram_bot/observability.py` already uses it.

**SDK alternative.** `from telegram_bot.observability import initialize_langfuse; initialize_langfuse(service_name="voice-agent")`. Drop the direct `opentelemetry-sdk` imports.

**Not a duplicate of #1349, #1521.**

---

### SDK-002 — Switch `ApartmentsService` to `RrfQuery` (matches `QdrantService`)

**Severity:** Low · **Type:** deprecated-sdk · **Files:** `telegram_bot/services/apartments_service.py:146-167`

Uses legacy `models.FusionQuery(fusion=models.Fusion.RRF)` while `telegram_bot/services/qdrant.py:477` already migrated to explicit `models.RrfQuery(rrf=models.Rrf(k=rrf_k))`. The two paths produce different fused scores when k differs from server default 60, and apartments path can never tune k.

**Fix.** Replace with `models.RrfQuery(rrf=models.Rrf(k=60))` and accept `rrf_k` kwarg, mirroring `QdrantService.hybrid_search_rrf`.

**No overlap.**

---

### SDK-003 — Push HyDE multi-query merging into a single Qdrant `Prefetch` + `RrfQuery`

**Severity:** Medium · **Type:** custom-vs-sdk · **Files:** `telegram_bot/services/qdrant.py:840-945`

`batch_search_rrf` issues N parallel `QueryRequest` objects, then dedupes and re-sorts in Python. Qdrant 1.18 supports server-side fusion under one outer `Prefetch` with `query=models.RrfQuery(...)`.

**Fix.** Build per-query inner `Prefetch`, wrap them under one outer `Prefetch` with `query=RrfQuery(...)`, call `query_points` once. Drop the Python dedupe/sort.

**No overlap.**

---

### SDK-004 — Replace per-endpoint Redis lazy global in `mini_app/api.py` with FastAPI `lifespan` + `Depends`

**Severity:** Medium · **Type:** sdk-migration · **Files:** `mini_app/api.py:18-40,49-91,105-110`

Module-level `_redis_client` global + `_get_redis()` lazy initializer; never `aclose()`d on shutdown. FastAPI's recommended pattern is `lifespan` + `Depends(get_redis)` (already used in `src/api/main.py:32-83`).

**Fix.** Add `@asynccontextmanager async def lifespan(app)` opening redis on `app.state`, expose via `def get_redis(request: Request) -> Redis: return request.app.state.redis`. Drop the global.

**No overlap.**

---

### SDK-005 — Replace `KommoClient` manual 401-then-refresh retry with `httpx.Auth`

**Severity:** Medium · **Type:** custom-vs-sdk · **Files:** `telegram_bot/services/kommo_client.py:55-77`

`_request` manually checks `status_code == 401` and rebuilds headers. `httpx.Auth.auth_flow` is designed for exactly this and integrates with `@kommo_retry`.

**Fix.** Subclass `httpx.Auth` with an `auth_flow` that yields once, on 401 calls `force_refresh()` and yields a re-signed request. Pass via `httpx.AsyncClient(auth=KommoOAuthAuth(token_store))`. `_request` collapses to a thin wrapper.

**Not a duplicate of #1095.**

---

### SDK-006 — Drop `tenacity` wrapper around OpenAI calls in `OpenAIContextualizer`; use `AsyncOpenAI(max_retries=...)`

**Severity:** Low · **Type:** custom-vs-sdk · **Files:** `src/contextualization/openai.py:55-62,99-107`

OpenAI SDK retries 408/409/429/5xx natively with backoff and `Retry-After`. Existing code wraps it in tenacity, duplicating logic.

**Fix.** Construct `AsyncOpenAI(api_key=..., max_retries=4)` once in `__init__`, drop `@retry` decorators on `contextualize_single`/`contextualize_sync`. Keep `@observe`.

**Not a duplicate of #1095, #1234.**

---

### SDK-007 — Replace manual `asyncio.sleep` poll loop in `RedisHealthMonitor` with APScheduler `IntervalTrigger`

**Severity:** Low · **Type:** custom-vs-sdk · **Files:** `telegram_bot/services/redis_monitor.py:80-99`

Bot already runs an `AsyncIOScheduler` in `NurturingScheduler`. Folding the health check into the same scheduler inherits coalesce / max_instances / misfire_grace_time semantics for free.

**Fix.** Inject `AsyncIOScheduler` into `RedisHealthMonitor` and `add_job(self._check_health, trigger='interval', seconds=300, coalesce=True, max_instances=1, id='redis-health-monitor')`. Drop `_loop` / `_task`.

**No overlap.**

---

### SDK-008 — Same migration for `SessionSummaryWorker._run_loop`

**Severity:** Low · **Type:** custom-vs-sdk · **Files:** `telegram_bot/services/session_summary_worker.py:74-99`

Polls every `poll_interval_sec` via `asyncio.wait_for(self._stop_event.wait(), ...)`. Consolidate into `NurturingScheduler.start()` as a third `add_job`.

**No overlap.**

---

### SDK-009 — Replace custom `PipelineMetrics` rolling-window p50/p95 with `prometheus_client` Histogram/Counter

**Severity:** Medium · **Type:** custom-vs-sdk · **Files:** `telegram_bot/services/metrics.py:20-180`

Hand-rolled in-memory aggregator with `deque` + `statistics.quantiles` + threading lock + singleton. `prometheus_client` already used by `services/bge-m3-api/app.py`. ~180 lines of singleton + lock code can disappear.

**Fix.** Define top-level `Histogram` / `Counter` instances; mount `make_asgi_app()` at `/metrics`; rewrite call sites `metrics.record('stage', ms)` → `STAGE_LATENCY.labels(stage='stage').observe(ms/1000)`.

**No overlap.**

---

### SDK-010 — Replace `logger.info('metric', extra={metric_name,...})` log-as-metric pattern with `prometheus_client` Counter

**Severity:** Low · **Type:** custom-vs-sdk · **Files:** `telegram_bot/agents/rag_pipeline.py:560,578,623,751-754`, `telegram_bot/services/qdrant.py:733-741`

Hot-path metrics (`colbert_rerank_attempted`, `topic_filter_fallback`, `retrieval_zero_docs`, `score_gap_confident`, `colbert_rerank_empty`, `colbert_fallback_to_rrf`) emitted as JSON log lines and parsed by Loki. Prometheus would remove the log-parsing pipeline.

**Fix.** `RETRIEVAL_EVENTS = Counter('rag_retrieval_events_total', '...', ['event'])` and `.labels(event='colbert_rerank_attempted').inc()`. Same `/metrics` endpoint as SDK-009.

**No overlap.**

---

### SDK-011 — Replace custom `HyDEGenerator` with LangChain `HypotheticalDocumentEmbedder`

**Severity:** Low · **Type:** custom-vs-sdk · **Files:** `telegram_bot/services/query_preprocessor.py:35-130`

Hand-rolled HyDE — hard-coded prompt, single OpenAI call, fallback to query. LangChain ships `HypotheticalDocumentEmbedder` with prompt-template versioning.

**Fix.** Replace with `HypotheticalDocumentEmbedder.from_llm(self._llm, self._hybrid, prompt=...)`. Move `HYDE_SYSTEM_PROMPT` to Langfuse Prompt Management.

**No overlap.**

---

### SDK-012 — Replace raw `aiohttp` + JSON-substring extraction with OpenAI `response_format=json_schema`

**Severity:** Medium · **Type:** custom-vs-sdk · **Files:** `src/evaluation/generate_test_queries.py:131-167`

Opens its own `aiohttp.ClientSession`, posts to LLM, then `content.find('{') ... rfind('}') + 1` substring-extracts JSON — brittle. OpenAI Structured Outputs guarantees parseable JSON shaped to a Pydantic model (already used in `scripts/generate_gold_set.py:162`).

**Fix.** Define `class GeneratedQueries(BaseModel): direct: str; semantic: str; paraphrased: str` and call `client.beta.chat.completions.parse(response_format=GeneratedQueries)`. Drop substring extraction.

**No overlap.**

---

### SDK-013 — Move `bge_m3_client` client-side batching to server side via single POST

**Severity:** Low · **Type:** refactor · **Files:** `telegram_bot/services/bge_m3_client.py:131-145,177-191,362-371,382-391,421-430`

`encode_dense`/`encode_sparse`/`encode_colbert` (sync + async) chunk inputs and POST one HTTP request per chunk. The BGE-M3 service already accepts `batch_size` and runs FlagEmbedding batching internally — extra round-trips for no GPU benefit. `encode_hybrid` (line 217) already does the right thing.

**Fix.** Drop the client-side `for i in range(0, len(texts), self.batch_size)`; send full list with `batch_size=self.batch_size` for the server.

**No overlap.**

---

### SDK-014 — Use `init_chat_model` instead of `ChatOpenAI` directly for `SummarizationNode`

**Severity:** Low · **Type:** sdk-migration · **Files:** `telegram_bot/graph/graph.py:280-292,144-167`

`_create_summarize_model` directly instantiates `langchain_openai.ChatOpenAI` with `SecretStr` api_key. `init_chat_model` is the canonical entry in LangChain 0.3+, with provider-prefixed strings (useful with LiteLLM proxy).

**Fix.** `from langchain.chat_models import init_chat_model; init_chat_model(config.llm_model, model_provider='openai', api_key=config.llm_api_key, base_url=config.llm_base_url)`.

**Not a duplicate of #1249.**

---

### SDK-015 — Replace `print()` remote-log endpoint in mini_app with structured logging

**Severity:** Low · **Type:** custom-vs-sdk · **Files:** `mini_app/api.py:95-103`

Already covered in PROD-003 from the security angle; this entry tracks the SDK side: use `logging.getLogger("mini_app.remote")` consistent with `telegram_bot/logging_config.py`.

---

### SDK-016 — Replace `asyncio.gather(return_exceptions=True)` in `ContextualizeProvider.contextualize_batch` with `asyncio.TaskGroup`

**Severity:** Low · **Type:** sdk-migration · **Files:** `src/contextualization/base.py:97-126`

Uses `asyncio.gather(..., return_exceptions=True)` and silently drops exceptions: `[r for r in results if isinstance(r, ContextualizedChunk)]`. Failures are LLM API failures and should be visible (Langfuse score), not dropped.

**Fix.** Switch to `asyncio.TaskGroup` (Python 3.11+); on `ExceptionGroup`, write a Langfuse score per failed chunk before re-raising or applying policy. Keep `Semaphore` as the per-task throttle.

**Not a duplicate of #1234.**

---

### SDK-017 — Use redis-py `Lock.extend(replace_ttl=True)` driven by APScheduler instead of manual heartbeat task

**Severity:** Low · **Type:** custom-vs-sdk · **Files:** `telegram_bot/bot.py:5118-5160`, `telegram_bot/integrations/polling_lock.py:60-90`

`_polling_lock_heartbeat` runs a parallel asyncio task that wakes every `ttl/3` seconds. Recommended pattern is `Lock.extend(additional_time, replace_ttl=True)` from an APScheduler `IntervalTrigger` — same scheduler used elsewhere — avoiding race with bot shutdown.

**Fix.** Register lock-extend as an APScheduler job; remove the standalone heartbeat task.

**No overlap.**

---

### SDK-018 — Replace dict-based `custom_fields_values` builder with Pydantic `KommoCustomField` models

**Severity:** Low · **Type:** refactor · **Files:** `telegram_bot/handlers/phone_collector.py:53-77`, plus consumers in `mini_app/phone.py`, `scripts/kommo_seed.py`

`_build_custom_fields` hand-builds `dict[str, list[dict]]` payloads — six identical `{'field_id': X, 'values': [{'value': Y}]}` shapes per call site. Pydantic 2 already powers `ContactCreate`/`LeadCreate`.

**Fix.** Define `class CustomFieldValue(BaseModel): field_id: int; values: list[CustomFieldEntry]` in `telegram_bot/services/kommo_models.py`; `_build_custom_fields` returns `[CustomFieldValue(...).model_dump(by_alias=True, exclude_none=True) for ...]`. Reuse from `mini_app/phone.py` and `scripts/kommo_seed.py`.

**No overlap.**

---

## Part 3 — Recommended execution order

| Step | Work | Why first |
|------|------|-----------|
| 1 | PROD-001 (`asyncio.get_event_loop()` in embeddings.py) | Already partially fixed in this PR — finish the rest |
| 2 | PROD-003 (mini_app CORS + initData + log endpoint) | Security: PII leak / forgery / log injection |
| 3 | PROD-004 (BGEM3Client race) | Resource leak, hits at scale |
| 4 | PROD-006 (`asyncio.create_task` GC) | Subtle, but real per Python docs |
| 5 | SDK-001, SDK-009, SDK-010 (observability consolidation) | Reduces ongoing maintenance the most |
| 6 | SDK-002, SDK-003 (Qdrant API alignment) | One-shot client.py rewrites with clear win |
| 7 | SDK-005, SDK-006 (HTTP/auth/retry consolidation) | Removes fragile retry layers |
| 8 | SDK-007, SDK-008, SDK-017 (APScheduler consolidation) | Single scheduler, simpler shutdown |
| 9 | PROD-007 (BGE batch failure modes) | After observability; needs metrics |
| 10 | PROD-002 (`datetime.utcnow`), PROD-005 (regex hot-path), PROD-008 (dead reranker), SDK-011 — SDK-018 (rest) | Low-risk cleanups, batch as a "tech-debt sweep" PR |

## Notes

- All findings cross-checked against open issues `#1070` … `#1593` (snapshot 2026-05-19 08:12 UTC).
- This file is intentionally a **publishing source** for issues, not a tracker — please convert each section into a GitHub Issue and close this document once converted.
- The PR opening this audit also applies the highest-severity fix as a code change so the PR itself is reviewable rather than docs-only.
