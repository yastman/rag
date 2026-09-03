# Redis demo behavior record — polling lock and fail-open caches — 2026-09-03

Scope: definition record for #3199 (parent epic #3197). It makes Redis responsibilities
explicit for the five-minute demo: exactly one authoritative responsibility (single-poller
ownership) plus non-authoritative caches that fail open. Evidence comes from the code paths
cited below, the characterization tests added under `tests/characterization/`
(`test_redis_demo_behavior.py`, part of the `make test-core` gate), and the live Redis
healthy/degraded probes in `tests/integration/test_redis_demo_probes.py` (run against the
local dev Redis on 2026-09-03; probe artifacts use the unique `i3199-` prefix and are
cleaned up). Following [`candidate-freeze-2026-09-03.md`](candidate-freeze-2026-09-03.md),
this record does not self-reference its own commit SHA.

## Ownership split

| Concern | Owner | Redis role |
| --- | --- | --- |
| Knowledge corpus (documents, chunks, vectors) | **Qdrant** | none |
| Apartment data (listings, filters, catalog) | **Qdrant** | none |
| Polling ownership (who runs the bot) | **Redis lease** | authoritative |
| Q&A / retrieval / rerank / extraction caches | in-product behavior | non-authoritative, fail open |
| Manager-handoff session state | product feature | optional, capability-gated |

Redis never stores demo content. Losing Redis never loses knowledge or apartment data; it
degrades the run to uncached behavior, and single-instance enforcement is re-established at
the next startup (preflight treats `redis` as a CRITICAL dependency, so the demo does not
start half-leased).

## Authoritative responsibility: single-poller ownership

Canonical key: `telegram-bot:polling` (`POLLING_LOCK_KEY`,
`src/runtime/integrations/polling_lock.py`). `RedisPollingLock` wraps
`redis.lock(key, timeout=90, blocking=False, thread_local=False)`; the owner token is
`{hostname}:{pid}` (`telegram_bot/lifecycle/lifecycle.py::setup_polling_lock`).

Deterministic outcomes:

- **Acquire (healthy Redis, free key):** the acquirer wins and is the only poller. The
  heartbeat task refreshes the lease every `ttl_sec // 3` seconds (30 s at the default 90 s
  TTL) via `extend(additional_time=ttl, replace_ttl=True)`.
- **Contention (key held):** the second acquirer gets `PollingLockBusy` whose message embeds
  `key`, `owner`, `pttl_ms` (or `ttl_sec`), and the remediation hint "stop the other bot
  instance first" — operator-visible without extra tooling. The loser never polls; the
  winner's lease is untouched (the loser drops its backend lock reference without releasing
  the winner's token).
- **Startup without Redis:** `setup_polling_lock` returns without acquiring and preflight
  has already failed the CRITICAL `redis` check — the bot does not run unleased.
- **Loss of ownership mid-run:** if the heartbeat cannot refresh
  (`POLLING_LOCK_MAX_REFRESH_FAILURES = 2` consecutive failures, heartbeat at ttl/3), the
  helper stops polling via `dp.stop_polling()` before the lease can silently expire into a
  second live bot. A lost or expired lease therefore ends in "this instance stopped", never
  in two bots answering the same update.

## Non-authoritative responsibilities: caches fail open

All caches are read-through/write-behind accelerators. The fail-open rule: an index/read
failure, timeout, or miss degrades to the uncached product path; a write failure is a logged
no-op. A cache failure can never fabricate a result (values are only ever previously stored
real responses) and never suppress a valid result (miss/failure → recompute).

| Cache | Key scheme | TTL | Failure behavior |
| --- | --- | --- | --- |
| Semantic answer (`CacheLayerManager`, RedisVL `SemanticCache`) | index `sem:v8:bge1024`, filter tags per query type/language/scope/role | per query type, 1–24 h | check error/timeout → `None` (recompute); store error → logged no-op |
| Dense embeddings (RedisVL `EmbeddingsCache`) | `embeddings:v5` | 7 d | get error → `None`; set error → logged no-op |
| Sparse embeddings | `sparse:v5:{sha256(model:norm_query)[:16]}` | 7 d | read error → `None`; write error → logged no-op |
| Search results | `search:v5:{hash(embedding, filters, retrieval_config)}` | 2 h | read error → `None`; write error → logged no-op |
| Rerank results | `rerank:v5:{hash(query, top_k, doc fingerprints)}` | 2 h | read error → `None`; write error → logged no-op |
| Apartment extraction | `extraction:v1:{sha256(norm_query)[:16]}` | 24 h | read error → `None` → regex-first extraction still returns the deterministic numeric filters; write error → logged no-op |

Operator-visible degraded status: `CacheLayerManager.initialize` logs
`Redis connection failed: …` (credentials redacted) and leaves `redis`/`semantic_cache`/
`embed_cache` as `None`, so every later read is a deterministic miss; per-read and per-store
errors are logged at ERROR/WARNING. At startup the preflight gate runs the deep Redis check
(PING/INFO) plus a synthetic write/read/TTL/delete cycle per cache key prefix
(`telegram_bot/preflight/remediation.py::_verify_cache_synthetic`) and surfaces failures as
CRITICAL `redis_cache` checks in the startup report — a degraded cache is announced before
the demo starts, and the demo itself continues uncached if it degrades mid-run.

## Handoff keys are conditional on the handoff capability

`handoff:{client_id}` (hash) and `topic_map:{topic_id}` (reverse lookup, default 72 h TTL)
exist only while the capability is on: `HANDOFF_ENABLED` defaults to false and config
validation rejects `handoff_enabled=true` without `managers_group_id`;
`setup_handoff_services` constructs `HandoffState` only when the cache layer is connected;
every handler guards on `bot._handoff_state is None`. A demo run without the handoff
capability writes no handoff keys.

## Deterministic outcome matrix (acceptance)

| Case | Outcome |
| --- | --- |
| Healthy Redis | exactly one poller holds `telegram-bot:polling`; caches hit/miss deterministically; hits only ever return previously stored real responses |
| Cache-index failure at startup | cache layer stays disabled (`None` backends); every read is a miss; product answers/retrieval proceed uncached; degraded status is logged and preflight reports CRITICAL |
| Cache read failure mid-run | that read degrades to the uncached path (recompute); no exception escapes to the user; nothing is fabricated or suppressed |
| Cache miss | uncached product behavior (recompute, then store for next time) |
| Lock contention | second instance raises `PollingLockBusy` with key/owner/pttl diagnostics and does not poll |
| Loss of polling ownership | heartbeat stops polling after 2 consecutive refresh failures — the instance stops safely instead of risking two bots |

## Probe evidence (2026-09-03, local dev Redis `localhost:6379`)

`tests/integration/test_redis_demo_probes.py` (marked `requires_services`; skips when Redis
is absent) exercises the live paths with `i3199-`-prefixed artifacts only:

- Healthy: PING; `RedisPollingLock` acquire on `i3199-polling` succeeds; a second owner's
  acquire raises `PollingLockBusy` naming the winner; release lets the next owner win.
- Healthy cache round trip: exact-tier miss → `None`, store → identical hit, cleanup.
- Degraded: `CacheLayerManager.initialize` against a closed port leaves `redis=None` and
  reads return `None` (fail open); a read against a dropped connection returns `None`.
  All probe keys are deleted in teardown.

## Verification

| Check | Result |
| --- | --- |
| `pytest tests/characterization/test_redis_demo_behavior.py tests/unit/runtime/test_polling_lock.py tests/unit/integrations/test_polling_lock.py tests/unit/integrations/test_cache_layers.py` | focused lock/cache tests pass |
| Live probes `tests/integration/test_redis_demo_probes.py` | healthy + degraded probes pass against local dev Redis (`i3199-` keys cleaned up) |
| `make test-core` | 243 passed (227 baseline + 16 new characterization tests) |
