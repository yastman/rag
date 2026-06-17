# Code Reuse and Abstraction Audit (#2714)

Audit of repeated logic and weak reuse across the codebase. Scope: request/response patterns, partial-failure handling, retry policy, tracing helpers, sentinel reconstruction, sync/async wrappers, validation, config parsing, Telegram handler boilerplate, and ingestion client boilerplate.

---

## Findings Table

| Repeated pattern | Locations | Current differences | Shared abstraction candidate | Risk | Action |
|---|---|---|---|---|---|
| **Langfuse span update in every BGE-M3 client method** | `src/services/bge_m3_client.py` — 15 `lf.update_current_span()` calls, one pair per encode method (input + output) | Each call has different key names for input/output counts (`vectors_count`, `weights_count`, `colbert_count`, etc.) | `_update_bge_span(lf, input_meta, output_meta)` helper inside the module — already partially done in `services/bge-m3-api/app.py` as `_update_current_bge_span()`, but the client side is inline | Low — pure helper extraction, no behavior change | **Refactor**: extract `_update_bge_client_span()` in `bge_m3_client.py`; keep field-name differences as caller-supplied dicts |
| **Partial-failure validation + sentinel reconstruction in every `/encode/*` endpoint** | `services/bge-m3-api/app.py` — `encode_dense`, `encode_sparse`, `encode_colbert`, `encode_hybrid` each repeat: `_validate_texts` → build `partial_failures` → `valid_texts` slice → encode → timing → reconstruct full-cardinality result with sentinel fill | Sentinel value differs per type (`[0.0]*1024`, `{"indices":[],"values":[]}`, `[[0.0]*1024]`); output field names differ | `_encode_with_partial_failure(model, texts, encode_fn, sentinel_fn)` factory extracting the validate → slice → encode → reconstruct loop | Medium — logic is identical structurally; sentinel type needs generic parameter | **High-value refactor**: extract a generic `_run_encode_with_partials()` helper; the four endpoints become thin wrappers |
| **`@observe` + Prometheus counter + batch-size histogram boilerplate at every endpoint** | `services/bge-m3-api/app.py` — every `encode_*` endpoint repeats: `encode_requests_total.labels(encode_type=X).inc()`, `encode_batch_size.observe(len(request.texts))`, `_update_current_bge_span(input=...)` | `encode_type` string differs; rerank uses different input shape | Decorator or context manager that accepts `encode_type` and runs the three boilerplate calls | Low | **Refactor**: small `_observe_encode_request(encode_type, texts_count, ...)` call at the top of each handler |
| **Sync vs async HTTP client duplication (`BGEM3Client` / `BGEM3SyncClient`)** | `src/services/bge_m3_client.py` — `BGEM3SyncClient.encode_dense/sparse/colbert/hybrid` duplicate request construction, response parsing, and empty-list guard from `BGEM3Client` | Sync uses `httpx.Client`; async uses `httpx.AsyncClient` + reconnect lock + `@observe` + Langfuse spans (sync lacks observability) | Shared `_build_encode_payload(texts, batch_size, max_length)` and `_parse_dense_response(data)` etc. helper functions consumed by both | Low | **Refactor**: extract 3–4 `_build_*` / `_parse_*` pure helpers; both clients call them |
| **`try: int(os.getenv(...)) except ValueError: fallback`** | `src/adapters/embeddings/local_bge_m3.py` (3×: `batch_size`, `max_length`, `max_concurrency`) | All three use the same try/except/fallback pattern; only env var name and default differ | `_env_int(name, default)` helper (already exists implicitly; also scattered in `src/runtime/graph/config.py`, `src/config/settings.py`, etc. with bare `int(os.getenv(...))` no-guard calls) | Low | **Minor refactor**: add `_env_int()` in `local_bge_m3.py`; larger unification with `settings.py` is lower priority |
| **Router factory + inner closure wrappers for bot injection** | `telegram_bot/handlers/command_handlers.py` — `create_commands_router()` wraps every handler in an `async def _cmd_*` closure to inject `bot_instance`; `phone_collector.py` and `demo_handler.py` use simpler factories without bot injection | `command_handlers.py` needs bot injection so each closure is a one-liner wrapper; others do not | The closure pattern is already the correct design for aiogram + dependency injection; the boilerplate is intrinsic. Only improvement: use `functools.partial` instead of inner `async def` wrappers | Low | **Leave alone** — the pattern is idiomatic for aiogram; replacing with `functools.partial` saves a few lines but is not materially better |
| **Empty-guard early return before HTTP call** | `src/services/bge_m3_client.py` — `BGEM3Client.encode_dense/sparse/hybrid/colbert` each start with `if not texts: return <empty result>` (also in `BGEM3SyncClient`); `src/adapters/embeddings/bge_m3.py` repeats `if not texts: return []` | Return type differs per method (`DenseResult`, `SparseResult`, etc.) | Already a minimal one-liner; abstraction would be over-engineered | None | **Leave alone** — boilerplate is one line per method, adding a helper would be more complex than the code |
| **`_trace_context_headers()` wrapping `_langfuse_trace_context_headers()`** | `src/services/bge_m3_client.py` — two functions, outer adds nothing beyond calling inner | `_trace_context_headers` exists for future multi-system extension but currently is a passthrough | Inline `_langfuse_trace_context_headers()` at call sites or remove the outer wrapper | Low | **Minor cleanup**: remove `_trace_context_headers()`, call `_langfuse_trace_context_headers()` directly — saves one indirection |
| **`ServiceBgeM3Provider` as an empty subclass of `BgeM3EmbeddingProvider`** | `src/adapters/embeddings/service_bge_m3.py` — the class body is just `pass`; adds no behavior | Kept for import compat for legacy consumers | Already a `__all__` re-export; the class can be replaced by a module-level alias `ServiceBgeM3Provider = BgeM3EmbeddingProvider` | Low | **Minor cleanup**: replace class with type alias once legacy callers are confirmed (grep shows only internal uses via factory) |
| **Ingestion client timeout + URL patterns** | `src/ingestion/docling_client.py` — `DoclingConfig.timeout=300.0`, `base_url`; `src/ingestion/unified/config.py` — similar patterns; `BGEM3SyncClient.__init__` also has `timeout: float = 300.0` | Each config is domain-specific and not logically shared | Different domains; shared base would create false coupling | None | **Leave alone** — not duplicated logic, just similar-looking defaults |

---

## Ranked Refactor Candidates

| Rank | Candidate | Payoff | Risk | Owner area |
|---|---|---|---|---|
| 1 | Partial-failure + sentinel reconstruction helper in `app.py` | High — ~100 lines removed, bug surface halved | Medium | `services/bge-m3-api/` |
| 2 | Sync/async HTTP payload builder and response parser helpers in `bge_m3_client.py` | Medium — removes payload duplication between two clients | Low | `src/services/` |
| 3 | Langfuse span update helper in `bge_m3_client.py` | Medium — 15 call sites collapsed to structured calls | Low | `src/services/` |
| 4 | Prometheus + observe boilerplate per endpoint in `app.py` | Low-medium — reduces per-endpoint noise | Low | `services/bge-m3-api/` |
| 5 | `_env_int()` helper in `local_bge_m3.py` | Low — 3 call sites, no risk | Low | `src/adapters/embeddings/` |
| 6 | Remove `_trace_context_headers()` outer wrapper | Low — cosmetic simplification | Low | `src/services/` |
| 7 | `ServiceBgeM3Provider` → type alias | Low — simplification with compat maintained | Low | `src/adapters/embeddings/` |

---

## Low-value duplications — explicitly left alone

| Pattern | Reason |
|---|---|
| Empty-guard `if not texts: return` per encode method | One line per method; abstracting it would require a sentinel factory more complex than the code itself |
| Telegram command handler closure wrappers | Intrinsic to aiogram dispatcher injection; `functools.partial` saves lines but doesn't improve clarity |
| Timeout/URL defaults in ingestion configs | Similar values in different domains; coupling them would be false abstraction |
| `int(os.getenv(...))` bare calls in `settings.py` / `config.py` | Settings modules already use Pydantic or structured dataclasses; adding a standalone `_env_int` across all would require a shared utils module not worth the dependency graph change at this stage |
