# Semantic Cache Degraded Response Hardening Design

Date: 2026-03-25
Branch: `dev`
Scope: `telegram_bot/` semantic cache write/read policy, degraded-response handling, RedisVL metadata filters, rollout and observability

## Purpose

This design defines the target hardening for the application's semantic cache so degraded, fallback, and error-like responses do not enter or survive inside the normal semantic reuse path.

The immediate trigger is a cache poisoning risk for queries such as `виды внж в болгарии`, where a degraded answer can be reused across semantically similar prompts. This is materially worse than poisoning an exact cache because the blast radius extends to paraphrases and related formulations.

The target state is:

- semantic cache stores only successful, reusable answers
- degraded or fallback answers never enter the primary semantic cache
- already-poisoned entries can be blocked on read and removed operationally
- cacheability logic is decided once and reused across all write paths
- telemetry makes poisoning visible before users report it

## External Baseline

As of March 2026, the external guidance still aligns with this direction:

- Google Apigee continues to document caching error responses as an anti-pattern and recommends excluding them from normal response caching except for tightly controlled, temporary cases.
- Google Cloud CDN continues to model negative caching as a separate policy with separate TTL controls by status code.
- RedisVL continues to document semantic cache as a lookup/store system with TTL, tags, filters, and targeted entry deletion.
- OpenAI prompt caching remains an exact-prefix input cache and does not replace application-level output cacheability policy.

References:

- https://cloud.google.com/apigee/docs/api-platform/antipatterns/caching-error
- https://docs.cloud.google.com/cdn/docs/using-negative-caching
- https://docs.redisvl.com/en/latest/user_guide/03_llmcache.html
- https://developers.openai.com/api/docs/guides/prompt-caching

## Problem Statement

Current protection is asymmetric.

- The direct client path in `telegram_bot/pipelines/client.py` already applies several write-side guards, including grounding checks and `safe_fallback_used`.
- The graph path in `telegram_bot/agents/rag_pipeline.py` and `telegram_bot/graph/nodes/cache.py` still stores broadly when response and embedding exist.
- The cache layer in `telegram_bot/integrations/cache.py` supports tag filters, but the schema does not yet encode full degraded-state eligibility.

This leaves three concrete failure modes:

1. A degraded answer is written through one path even if another path would have blocked it.
2. An old poisoned entry remains readable because read-side filtering is weaker than write-side policy.
3. Incident recovery relies on TTL rather than explicit invalidation or versioning.

## Design Goals

Primary goals:

- Define one semantic-cache eligibility policy for all write paths.
- Define one canonical application-level store entrypoint for `cache_scope="rag"`.
- Distinguish `successful but reusable` from `successful transport-level delivery`.
- Add read-side metadata enforcement so bad historical entries are not reused.
- Preserve the existing service boundaries: generation emits signals, cache policy decides reuse, cache integration enforces storage and lookup constraints.
- Keep rollout operationally safe with targeted purge and semantic schema version bump support.

Non-goals:

- Replacing RedisVL or Redis.
- Redesigning the retrieval pipeline.
- Introducing a full negative-cache subsystem in the first patch.
- Mixing transport-layer Telegram logic into cache policy.

## Current Architecture Findings

Observed repo facts:

- Exact cache namespaces are versioned by `CACHE_VERSION = "v5"`.
- Semantic cache already has its own schema boundary via `SEMANTIC_CACHE_VERSION = "v6"`.
- Primary RAG semantic writes currently happen from multiple application paths, including:
  - `telegram_bot/pipelines/client.py`
  - `telegram_bot/agents/rag_pipeline.py`
  - `telegram_bot/graph/nodes/cache.py`
  - `telegram_bot/bot.py`
- Semantic cache currently uses RedisVL tag filters for:
  - `query_type`
  - `language`
  - `user_id`
  - `cache_scope`
  - `agent_role`
  - `grounding_mode`
  - `semantic_cache_safe_reuse`
- Existing tests currently assume broad store behavior on graph cache-store paths, so the behavioral contract will need to change deliberately.
- `telegram_bot/agents/history_tool.py` also writes semantic cache entries, but in `cache_scope="history"`. That path is not the primary subject of this hardening and should remain explicitly out of scope unless we choose to extend the same contract to history summaries later.

These findings make a semantic-schema bump an accepted repo-native mechanism, not an exceptional migration.

## Architectural Principles

1. The semantic cache is a reuse store for valid answers, not a persistence sink for any emitted text.
2. Application-level degraded responses are operationally equivalent to cache-excluded error responses.
3. Write-side guard prevents new poison; read-side guard protects against old poison.
4. Cacheability must be decided in one policy function, not re-derived ad hoc in multiple call sites.
5. Metadata fields must be useful for lookup filtering, targeted purge, and observability.
6. For `cache_scope="rag"`, application code should have one canonical semantic-store entrypoint above the cache adapter.

## Target Cacheability Contract

Every semantic cache candidate should be normalized into a cacheability contract with these minimum fields:

- `response_state`
  - `ok`
  - `degraded`
  - `fallback`
  - `safe_fallback`
  - `error`
- `cache_eligible`
- `provider_model`
- `degraded_reason`
- `grounding_mode`
- `semantic_cache_safe_reuse`
- `created_at`
- `schema_version`

Recommended meanings:

- `response_state` describes the application-level quality of the answer, not the transport outcome.
- `cache_eligible` is the final policy verdict for semantic reuse.
- `provider_model` preserves the actual provider/model string or `"fallback"`.
- `degraded_reason` is a short operational code such as `llm_failure`, `timeout`, `provider_fallback`, `safe_fallback`, `empty_response`, or `partial_recovery`.
- `schema_version` allows future read isolation and controlled invalidation.

## Response Classification Rules

The generation layer remains responsible for emitting raw degradation signals, not for deciding cache writes.

`response_state`, `degraded_reason`, and `cache_eligible` must be derived from one normalization/decision helper. No other layer should invent `response_state` independently.

The normalization helper should map the existing raw signals into `response_state` using rules such as:

- `safe_fallback_used=True` -> `response_state="safe_fallback"`
- `fallback_used=True` -> `response_state="fallback"`
- `llm_provider_model=="fallback"` -> `response_state="fallback"`
- `llm_timeout=True` with fallback content -> `response_state="degraded"` or `fallback`, depending on emitted result
- empty or truncated unusable output -> `response_state="error"` or `degraded`
- normal grounded or ordinary answer -> `response_state="ok"`

`degraded_reason` should be set even when the pipeline continues successfully from the user perspective.

`cache_eligible` must be derived from the same decision object that computes `response_state`. It must not be set independently in call sites or stored as a second hand-maintained truth.

## Unified Cache Policy

Add a single policy module, preferably `telegram_bot/services/cache_policy.py`, with a decision builder and one canonical RAG store helper:

- `build_cacheability_decision(...) -> SemanticCacheDecision`
- `maybe_store_semantic_response(...) -> bool`

Recommended `SemanticCacheDecision` contents:

- `response_state`
- `degraded_reason`
- `cache_eligible`
- `metadata`
- `store_reason`

This module should own the full write-side decision for the primary RAG path.

For `cache_scope="rag"`, business code should not call `cache.store_semantic(...)` directly. Instead:

- `maybe_store_semantic_response(...)` is the only application-level entrypoint allowed to decide whether a RAG answer is stored
- `CacheLayerManager.store_semantic(...)` remains the low-level adapter sink once a store is already authorized

This removes the current duplication between `client.py`, `rag_pipeline.py`, `graph/nodes/cache.py`, and `bot.py`.

Semantic cache store is allowed only when all of the following are true:

- response text is non-empty
- request was not already served from semantic cache
- query type is allowlisted for semantic caching
- request is not contextual/follow-up if the current path already treats contextual queries as non-cacheable
- retrieval and grounding quality gates pass
- required documents are present for that query class
- `fallback_used == false`
- `safe_fallback_used == false`
- `llm_provider_model != "fallback"`
- `response_state == "ok"`
- `cache_eligible == true`

This policy replaces fragmented local checks in write call sites.

## Read-Side Enforcement

The cache integration layer should filter semantic hits so entries are reused only when they remain policy-valid.

Minimum read-side requirements:

- `cache_eligible == true`
- `response_state == "ok"`
- current `schema_version` matches the active semantic cache contract

Additional existing strict-grounding behavior remains valid:

- when strict grounding requires safe reuse, `semantic_cache_safe_reuse == "true"` stays part of the filter

Read-side enforcement matters because:

- write policy protects the future
- read policy protects the present from already-bad historical entries

## RedisVL Schema Changes

Extend semantic cache `filterable_fields` to include:

- `response_state`
- `cache_eligible`
- `schema_version`

`degraded_reason` may remain metadata-only unless operational querying in Redis search is required.

Because RedisVL `filterable_fields` participate in index initialization/schema shape, expanding these lookup tags should be treated as a schema boundary. In this repo, that means a semantic cache version bump rather than a mixed old/new namespace.

Recommended tag strategy:

- use filterable tags only for fields needed during lookup or broad operational isolation
- keep explanatory fields in metadata when they are not part of lookup policy

## Component Changes

### `telegram_bot/services/generate_response.py`

Responsibilities:

- emit stable raw degradation signals
- avoid deciding semantic cache policy directly

### `telegram_bot/services/cache_policy.py`

Responsibilities:

- normalize raw generation signals into `response_state` and `degraded_reason`
- derive `cache_eligible` from the same decision object
- build semantic cache metadata
- provide the single canonical `maybe_store_semantic_response(...)` entrypoint for `cache_scope="rag"`

### `telegram_bot/pipelines/client.py`

Responsibilities:

- stop owning bespoke semantic-cache policy logic
- call shared `maybe_store_semantic_response(...)`
- stop calling `cache.store_semantic(...)` directly for RAG answers

### `telegram_bot/agents/rag_pipeline.py`

Responsibilities:

- adopt the same shared cacheability policy as the direct client path
- stop broad unconditional semantic-store behavior
- stop calling `cache.store_semantic(...)` directly for RAG answers

### `telegram_bot/graph/nodes/cache.py`

Responsibilities:

- either consume a precomputed `SemanticCacheDecision` from graph state or call the same shared helper before storing
- preserve current graph-node contract shape while tightening store eligibility
- stop serving as an independent source of semantic-cache policy

### `telegram_bot/bot.py`

Responsibilities:

- remove ad hoc RAG-side semantic store logic
- delegate to the shared RAG semantic-store helper instead of maintaining its own allowlist and grounding checks

### `telegram_bot/integrations/cache.py`

Responsibilities:

- add new semantic cache filterable fields
- enforce read-side metadata filtering
- preserve current versioned namespace pattern
- expose or document targeted clear/drop workflows when needed for incident response

## Rollout Strategy

Use a three-step rollout:

1. Implement the new policy and metadata contract.
2. Bump the semantic cache namespace as part of the same change.
3. Clean up old poisoned or obsolete entries opportunistically.

The semantic cache version bump is mandatory for this work, not optional. Reasons:

- new `filterable_fields` change the effective lookup schema
- the new read contract depends on metadata older entries do not have
- the repo already uses versioned semantic namespaces for this kind of boundary

Expected effect of the bump:

- old entries without the new metadata become unreadable by design because they live in the old namespace
- this is a desired isolation outcome, not an accidental cache miss regression

Operational cleanup options:

### Option A: Targeted purge

Use when there is a small known set of poisoned prompts or entry IDs and we want to remove them immediately from the old namespace or reclaim space after the version bump.

Benefits:

- minimal cache disruption
- useful for immediate incident response

Limitations:

- relies on accurate identification of all poisoned entries
- easy to miss semantically related stale entries

### Option B: Semantic schema/version bump

Increment `SEMANTIC_CACHE_VERSION` in this change set and treat it as part of the migration, not as a fallback contingency.

Benefits:

- strongest isolation boundary
- simple operational rollback path
- already aligns with repo conventions

Limitations:

- cold-start hit-rate reset for the semantic tier

Recommendation:

- always use semantic version bump in this work
- optionally use targeted purge for known-bad entries or old-namespace cleanup

## Negative Cache Position

Negative caching should not be implemented by writing degraded responses into the primary semantic cache.

If the system later needs incident-time request suppression, do it as a separate namespace with:

- short TTL
- separate metrics
- explicit read path
- explicit semantics different from normal answer reuse

This is a later enhancement, not a dependency for the first hardening patch.

## Observability

Add cache-policy-aware telemetry:

- `semantic_hit`
- `semantic_miss`
- `semantic_store_ok`
- `semantic_store_blocked_noncacheable`
- `semantic_store_blocked_degraded`
- `semantic_read_blocked_metadata`
- `semantic_poison_purge_count`

Recommended dimensions:

- `query_type`
- `grounding_mode`
- `response_state`
- `degraded_reason`
- `provider_model`
- `cache_scope`

Alerting worth adding later:

- sudden spike in `semantic_store_blocked_degraded`
- sudden drop in `semantic_hit` after rollout beyond expected cold-start window
- elevated share of `response_state != ok` for strict-grounding topics

## Validation Plan

Required validation areas:

### Unit tests

- cache policy helper accepts clean `ok` responses
- cache policy helper rejects fallback, safe fallback, degraded, timeout, and empty-response cases
- client path passes metadata and blocks non-cacheable writes
- graph path blocks writes for degraded results
- cache integration applies new read-side filters
- poisoned historical entry is not returned when metadata marks it non-eligible

### Integration tests

- `miss -> generate ok -> store -> hit`
- `miss -> generate degraded -> no store`
- strict-grounding path still requires safe reuse where applicable

### Repo checks

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- targeted cache/search suites under `tests/unit/`
- affected integration tests for graph paths and cache behavior

## Risks And Tradeoffs

Expected tradeoffs:

- semantic hit rate may dip initially because degraded answers will no longer be reused
- some current tests will need contract updates because they assert broad store behavior
- introducing new RedisVL tags may require a semantic schema bump

These tradeoffs are acceptable because the current behavior optimizes hit rate at the expense of correctness and incident recovery.

## Implementation Sequence

1. Add cache policy helper and response-state normalization.
2. Replace direct RAG semantic-store call sites with the shared canonical helper.
3. Extend RedisVL semantic schema and read filters.
4. Bump `SEMANTIC_CACHE_VERSION`.
5. Add tests for store-block and read-block behavior.
6. Purge known poisoned entries or old namespace keys as operational cleanup.
7. Run validation and monitor semantic metrics after rollout.

## Acceptance Criteria

The design is satisfied when:

- degraded or fallback answers are never written to the primary semantic cache
- semantic reads return only `response_state="ok"` and `cache_eligible=true` entries
- client and graph paths share one cacheability policy
- known poisoned entries are no longer reusable
- semantic cache contract changes are versioned safely
- tests cover both prevention of new poison and blocking of old poison
