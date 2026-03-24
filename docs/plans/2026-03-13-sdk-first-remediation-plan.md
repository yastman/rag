# SDK-First Remediation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce unnecessary custom integration code by adopting official SDK/native APIs where they already cover the use case, while preserving the custom adapters that are still justified.

**Architecture:** Keep SDK boundaries explicit per subsystem. Replace repo-local logic only where the vendor SDK already exposes the same behavior (`Langfuse` prompt fetching, `Docling` conversion/chunking). Do not force third-party or low-trust community wrappers into production paths when the repo's first-party adapter is safer (`Kommo`, local BGE-M3 service). Build on the audit in `docs/plans/2026-03-02-sdk-migration-audit.md`, but turn it into an execution-ready sequence.

**Tech Stack:** Python 3.12, Langfuse Python SDK, Docling Python API, Qdrant Python SDK, LiveKit Agents, aiogram, Redis, asyncpg, httpx

---

## Scope

**In scope**
- Remove SDK duplication in `Langfuse` prompt access.
- Consolidate duplicate Kommo token-store implementations into one canonical adapter.
- Run a bounded Docling native-SDK migration spike for unified ingestion.
- Add a typed internal client for voice-to-RAG calls instead of ad-hoc `httpx` usage in the tool body.
- Update SDK guidance/docs after code changes land.

**Out of scope**
- Replacing direct `qdrant-client` usage with `langchain-qdrant`.
- Replacing the self-hosted BGE-M3 REST boundary with a third-party wrapper.
- Replacing `LiveKit Agents` or `aiogram` architecture.
- Introducing unofficial Kommo SDKs into production without a separate approval decision.

## Research Verdicts To Preserve

- `Langfuse` official SDK already supports `get_prompt(..., cache_ttl_seconds=..., fallback=...)` and prompt lookup via `client.prompts.get(...)`.
- `Docling` official Python package already exposes `DocumentConverter` and `HybridChunker`; the repo also already depends on `docling` and uses it outside unified ingestion.
- `Qdrant` direct SDK usage is already the correct path for named vectors, hybrid search, and server-side rerank flows.
- `LiveKit Agents` explicitly supports external backend calls from `@function_tool`; the problem in voice is not missing SDK support, but the lack of a shared typed client boundary.
- Kommo official docs document REST + OAuth2, but no official Python SDK was verified. Community packages exist, but they are third-party and lower-trust than the current in-repo adapter.

### Task 1: Simplify Langfuse Prompt Management To SDK-Native Behavior

**Files:**
- Modify: `telegram_bot/integrations/prompt_manager.py`
- Test: `tests/unit/test_prompt_manager.py`
- Reference: `docs/engineering/sdk-registry.md`

**Step 1: Write the failing tests**

Add/extend tests to assert:
- `get_prompt()` passes `cache_ttl_seconds` through to the SDK.
- fallback text is returned when the SDK raises a not-found error.
- prompt compilation still applies `variables`.
- no direct use of `client.api.prompts.get(...)` is required for the happy path.

Example test shape:

```python
def test_get_prompt_uses_sdk_fallback(mock_langfuse_client):
    mock_langfuse_client.get_prompt.side_effect = Exception("Prompt not found")
    result = prompt_manager.get_prompt("missing", fallback="hello {{name}}", variables={"name": "A"})
    assert result == "hello A"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_prompt_manager.py -q`
Expected: FAIL because current implementation still depends on manual probe/cache helpers.

**Step 3: Write minimal implementation**

Refactor `prompt_manager.py` to:
- remove `_missing_prompts_until`, `_known_prompts_until`, and `_probe_prompt_available()`;
- call `client.get_prompt(name, label=..., cache_ttl_seconds=..., fallback=...)`;
- keep local fallback-variable substitution only for the no-client case or for SDK exceptions that still need graceful degradation;
- keep public API unchanged.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_prompt_manager.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/integrations/prompt_manager.py tests/unit/test_prompt_manager.py docs/engineering/sdk-registry.md
git commit -m "refactor: use langfuse sdk prompt cache and fallback"
```

### Task 2: Consolidate Kommo OAuth State Into One Canonical Token Store

**Files:**
- Modify: `telegram_bot/services/kommo_client.py`
- Modify: `telegram_bot/services/kommo_tokens.py`
- Modify: `telegram_bot/services/kommo_token_store.py`
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/services/test_kommo_tokens.py`
- Test: `tests/unit/services/test_kommo_token_store.py`
- Test: `tests/unit/services/test_kommo_client.py`

**Step 1: Write the failing tests**

Add/extend tests to assert:
- bot initialization and `KommoClient` use the same token-store implementation;
- only one Redis key format is used;
- refresh flow still works for stored refresh tokens;
- seed-from-env mode still works when only an access token is present.

Example test shape:

```python
async def test_bot_and_client_share_same_kommo_token_store(redis_client):
    store = KommoTokenStore(...)
    await store.seed_env_token("token")
    assert await store.get_valid_token() == "token"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/services/test_kommo_tokens.py tests/unit/services/test_kommo_token_store.py tests/unit/services/test_kommo_client.py -q`
Expected: FAIL once assertions require a single canonical implementation.

**Step 3: Write minimal implementation**

Choose one canonical module:
- keep one `KommoTokenStore` implementation;
- make the other module a compatibility shim or delete it after import-site cleanup;
- align Redis keying strategy;
- update `telegram_bot/bot.py` and `telegram_bot/services/kommo_client.py` to import the same class/protocol;
- preserve current OAuth2 behavior and fail-safe startup.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/services/test_kommo_tokens.py tests/unit/services/test_kommo_token_store.py tests/unit/services/test_kommo_client.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/kommo_client.py telegram_bot/services/kommo_tokens.py telegram_bot/services/kommo_token_store.py telegram_bot/bot.py tests/unit/services/test_kommo_tokens.py tests/unit/services/test_kommo_token_store.py tests/unit/services/test_kommo_client.py
git commit -m "refactor: unify kommo oauth token store"
```

### Task 3: Run A Feature-Flagged Docling Native-SDK Migration Spike For Unified Ingestion

**Files:**
- Modify: `src/ingestion/unified/config.py`
- Modify: `src/ingestion/unified/targets/qdrant_hybrid_target.py`
- Modify: `src/ingestion/docling_client.py`
- Create: `src/ingestion/docling_native.py`
- Test: `tests/unit/ingestion/test_docling_client.py`
- Test: `tests/unit/ingestion/test_docling_native.py`
- Test: `tests/integration/test_gdrive_ingestion.py`

**Step 1: Write the failing tests**

Add a contract-focused test suite that asserts the native path returns the same normalized chunk shape as the current HTTP client:
- `text`
- `seq_no`
- `headings`
- `page_range`
- `metadata`

Example test shape:

```python
def test_native_docling_chunk_contract(sample_docx):
    chunks = chunk_with_native_docling(sample_docx)
    assert chunks
    assert {"text", "seq_no", "headings", "page_range", "metadata"} <= chunks[0].model_dump().keys()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_docling_native.py -q`
Expected: FAIL because the native adapter does not exist yet.

**Step 3: Write minimal implementation**

Implement a bounded migration:
- add a native adapter using `DocumentConverter` + `HybridChunker`;
- keep the current HTTP `DoclingClient` as fallback behind config/feature flag;
- wire unified ingestion to choose native vs HTTP path explicitly;
- preserve deterministic metadata mapping and chunk identity;
- do not remove the HTTP path until integration results are acceptable.

**Step 4: Run tests to verify behavior**

Run: `uv run pytest tests/unit/ingestion/test_docling_client.py tests/unit/ingestion/test_docling_native.py -q`
Expected: PASS

Run: `uv run pytest tests/integration/test_gdrive_ingestion.py -q`
Expected: PASS when the required local services/test fixtures are available

**Step 5: Commit**

```bash
git add src/ingestion/unified/config.py src/ingestion/unified/targets/qdrant_hybrid_target.py src/ingestion/docling_client.py src/ingestion/docling_native.py tests/unit/ingestion/test_docling_client.py tests/unit/ingestion/test_docling_native.py tests/integration/test_gdrive_ingestion.py
git commit -m "feat: add native docling path for unified ingestion"
```

### Task 4: Add A Typed Voice RAG API Client

**Files:**
- Create: `src/voice/rag_api_client.py`
- Modify: `src/voice/agent.py`
- Test: `tests/unit/voice/test_rag_api_client.py`
- Test: `tests/unit/voice/test_agent.py`

**Step 1: Write the failing tests**

Add tests to assert:
- `search_knowledge_base()` delegates to a typed client instead of inline `httpx`;
- HTTP errors return the current user-facing fallback;
- the request payload still includes `query`, `user_id`, `session_id`, `channel`, and optional `langfuse_trace_id`.

Example test shape:

```python
async def test_voice_agent_uses_rag_api_client(mock_rag_client):
    result = await agent.search_knowledge_base(context, "price in Sofia")
    assert result == "ok"
    mock_rag_client.query.assert_awaited_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/voice/test_rag_api_client.py tests/unit/voice/test_agent.py -q`
Expected: FAIL because the typed client boundary does not exist yet.

**Step 3: Write minimal implementation**

Create `src/voice/rag_api_client.py` that:
- owns the shared `httpx.AsyncClient`;
- exposes one typed `query()` method returning parsed response data;
- centralizes timeout/error handling and request schema.

Update `src/voice/agent.py` so the tool calls that client instead of issuing inline HTTP requests.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/voice/test_rag_api_client.py tests/unit/voice/test_agent.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/voice/rag_api_client.py src/voice/agent.py tests/unit/voice/test_rag_api_client.py tests/unit/voice/test_agent.py
git commit -m "refactor: add typed rag api client for voice agent"
```

### Task 5: Refresh SDK Guidance And Audit Docs

**Files:**
- Modify: `docs/engineering/sdk-registry.md`
- Modify: `docs/plans/2026-03-02-sdk-migration-audit.md`
- Modify: `README.md`

**Step 1: Write the failing test/check**

There is no unit test here. Use a docs consistency check instead:
- ensure the SDK registry reflects the canonical Kommo, Langfuse, and Docling decisions;
- ensure README/plan text does not describe removed legacy paths as primary.

**Step 2: Run the check**

Run: `rg -n "kommo_token_store|docling-serve|client.api.prompts.get|Prompt availability probe" docs/engineering/sdk-registry.md README.md docs/plans/2026-03-02-sdk-migration-audit.md telegram_bot src`
Expected: reveals stale references before docs updates.

**Step 3: Write minimal implementation**

Update docs to reflect:
- Kommo stays first-party/internal, but only one adapter is supported;
- Langfuse prompt access is SDK-native;
- Docling has a feature-flagged native ingestion path and the old HTTP path is compatibility only if still present.

**Step 4: Run the check again**

Run: `rg -n "kommo_token_store|client.api.prompts.get|Prompt availability probe" docs/engineering/sdk-registry.md README.md docs/plans/2026-03-02-sdk-migration-audit.md telegram_bot src`
Expected: no stale references, or only intentional compatibility mentions

**Step 5: Commit**

```bash
git add docs/engineering/sdk-registry.md docs/plans/2026-03-02-sdk-migration-audit.md README.md
git commit -m "docs: refresh sdk-first guidance after integration cleanup"
```

### Task 6: Full Validation

**Files:**
- N/A

**Step 1: Run repo checks**

Run: `make check`
Expected: PASS

**Step 2: Run unit suite**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
Expected: PASS

**Step 3: Run ingestion-specific checks if Task 3 changed code**

Run: `uv run pytest tests/unit/ingestion/test_docling_client.py tests/unit/ingestion/test_docling_native.py -n auto --dist=worksteal -q`
Expected: PASS

**Step 4: Run voice-specific checks if Task 4 changed code**

Run: `uv run pytest tests/unit/voice/test_rag_api_client.py tests/unit/voice/test_agent.py -n auto --dist=worksteal -q`
Expected: PASS

**Step 5: Commit validation state**

```bash
git status --short
```

## References

- Kommo OAuth docs: `https://developers.kommo.com/docs/oauth-20`
- Third-party Kommo package found during audit: `https://pypi.org/project/kommo-python/`
- Langfuse Python SDK prompt docs: `https://context7.com/langfuse/langfuse-python/llms.txt`
- Qdrant Python SDK docs: `https://context7.com/qdrant/qdrant-client/llms.txt`
- Docling repository/docs: `https://github.com/docling-project/docling`
- Docling chunking docs: `https://docling-project.github.io/docling/concepts/chunking/`
- LiveKit Agents docs: `https://context7.com/livekit/agents/llms.txt`

## Implementation Notes

- Preserve Telegram transport/domain boundaries from `telegram_bot/AGENTS.override.md`.
- Preserve ingestion determinism/resumability from `src/ingestion/unified/AGENTS.override.md`.
- If Task 3 cannot match native Docling output closely enough, keep the HTTP path and document the measured reason instead of forcing the migration.
- Do not adopt `kommo-python`, `amochka`, or other third-party Kommo clients without a separate approval step and live-account verification.
