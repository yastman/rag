# Voice SDK Transition Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate voice runtime from mixed custom lifecycle patterns to SDK-first lifecycle (LiveKit AgentServer + process/session resource boundaries) without user-facing behavior regressions.

**Architecture:** Keep current product flow from issue #153 (Telegram `/call` -> LiveKit dispatch/SIP -> Voice Agent -> RAG API), but move resource ownership to SDK lifecycle primitives (`setup_fnc`, `JobContext` shutdown hooks, process userdata) and remove fragile module-global state. Preserve existing STT fallback and timeout behavior.

**Tech Stack:** livekit-agents ~1.3 (Python), LiveKit SIP, httpx + tenacity, asyncpg, FastAPI RAG API, Langfuse OTEL

---

## Completed Work (from #153 code review)

The following hardening was applied directly to `src/voice/agent.py` during the #153 code review session. These changes are prerequisites for the remaining tasks.

### Done: STT FallbackAdapter

**Files changed:** `src/voice/agent.py:226-230`

Replaced single `elevenlabs.STT()` with SDK `stt.FallbackAdapter`:
```python
primary_stt = elevenlabs.STT(model_id="scribe_v2_realtime")
fallback_stt = openai.STT(model="whisper-1")
session = AgentSession(stt=lk_stt.FallbackAdapter([primary_stt, fallback_stt]), ...)
```

### Done: Configurable RAG API Timeout + Tenacity Retry

**Files changed:** `src/voice/agent.py:27-28, 127-147`

- `RAG_API_TIMEOUT` env var (default 60s) replaces hardcoded timeout
- `@retry(stop=stop_after_attempt(2), wait=wait_exponential(...))` on `_call_rag_api`
- Retries only on `httpx.TimeoutException` and `httpx.ConnectError`

### Done: Granular Error Handling in search_knowledge_base

**Files changed:** `src/voice/agent.py:149-171`

Three distinct fallback paths:
- `httpx.TimeoutException` -> "поиск занимает слишком долго"
- `httpx.HTTPStatusError` -> "сервис временно недоступен"
- Generic `Exception` -> "не могу найти информацию"

All fallbacks are appended to transcript before return.

### Done: Shutdown Callback with Singleton Reset

**Files changed:** `src/voice/agent.py:209-223`

- `ctx.add_shutdown_callback(_on_shutdown)` for lifecycle cleanup
- `_transcript_store = None` reset after `store.close()` to prevent stale singleton

### Done: LiveKit Mock in conftest.py

**Files changed:** `tests/conftest.py`

- `_setup_mock_optional_voice_deps()` mocks all `livekit.*` submodules
- Pattern matches existing `_setup_mock_optional_telegram_deps()` for aiogram
- Enables voice unit tests to run without `[voice]` optional deps installed

### Done: Error Handling Unit Tests

**Files changed:** `tests/unit/voice/test_voice_agent.py`

7 tests total (3 original + 4 new):
- `test_search_tool_timeout_returns_fallback`
- `test_search_tool_http_error_returns_fallback`
- `test_search_tool_generic_error_returns_fallback`
- `test_search_tool_appends_transcript_entries_with_store`

**Verification:** 21/21 tests pass (`voice/ + api/ + test_cmd_call`), ruff clean.

---

## Remaining Tasks

### Task 1: Move Runtime Initialization to LiveKit SDK Lifecycle

**Status:** NOT STARTED

**Files:**
- Modify: `src/voice/agent.py`
- Test: `tests/unit/voice/test_voice_agent.py`

**Step 1: Write failing test for SDK-managed prewarm usage**

Add a unit test that asserts VAD is read from `ctx.proc.userdata` when prewarmed, instead of always calling `silero.VAD.load()` inside each entrypoint run.

**Step 2: Implement `setup_fnc` prewarm**

In `src/voice/agent.py`:
1. Add `def prewarm(proc: JobProcess) -> None`.
2. Store preloaded VAD in `proc.userdata["vad"]`.
3. Set `server.setup_fnc = prewarm`.
4. In `entrypoint`, read VAD from `ctx.proc.userdata` with safe fallback.

**Step 3: Run focused tests**

Run:
```bash
uv run pytest tests/unit/voice/test_voice_agent.py -q
```
Expected: PASS and no behavior regressions in existing tool tests.

**Step 4: Commit**

```bash
git add src/voice/agent.py tests/unit/voice/test_voice_agent.py
git commit -m "refactor(voice): use LiveKit setup_fnc/process userdata for runtime prewarm"
```

---

### Task 2: Remove Module-Global TranscriptStore Lifecycle

**Status:** NOT STARTED (partially mitigated by singleton reset in "Done" section)

**Files:**
- Modify: `src/voice/agent.py`
- Modify: `src/voice/transcript_store.py` (only if needed for explicit state checks)
- Test: `tests/unit/voice/test_voice_agent.py`

**Step 1: Write failing test for close-path safety**

Add tests for two paths:
1. `store` exists but `call_id` empty -> pool still closes.
2. Next call after shutdown initializes a fresh store cleanly.

**Step 2: Replace global singleton flow**

In `src/voice/agent.py`:
1. Remove `_transcript_store` module global and `_get_transcript_store()` lazy helper.
2. Create store per job entrypoint (`initialize()` once per job).
3. In shutdown callback, always close store if initialized (independent of `call_id`).

**Step 3: Preserve best-effort semantics**

Ensure all transcript operations remain wrapped in exception-safe logging (no exception escapes call flow).

**Step 4: Run focused tests**

Run:
```bash
uv run pytest tests/unit/voice/test_voice_agent.py -q
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/voice/agent.py src/voice/transcript_store.py tests/unit/voice/test_voice_agent.py
git commit -m "refactor(voice): remove module-global transcript store and enforce job-scoped lifecycle"
```

---

### Task 3: Introduce SDK-Style RAG Client Boundary

**Status:** NOT STARTED

**Files:**
- Create: `src/voice/rag_client.py`
- Modify: `src/voice/agent.py`
- Test: `tests/unit/voice/test_voice_agent.py`

**Step 1: Write failing test for client abstraction**

Add test asserting `VoiceBot.search_knowledge_base()` delegates to a client interface (not raw inline `httpx` usage), preserving current fallback texts.

**Step 2: Implement typed client wrapper**

In `src/voice/rag_client.py`:
1. Add `RagApiClient` with `query()` method.
2. Centralize timeout, retries, and error mapping there.
3. Keep request/response shape aligned with `src/api/schemas.py`.

In `src/voice/agent.py`:
1. Inject `RagApiClient` into `VoiceBot`.
2. Remove `_call_rag_api` method and direct HTTP payload construction from tool method.

**Step 3: Run unit tests**

Run:
```bash
uv run pytest tests/unit/voice/test_voice_agent.py -q
```
Expected: PASS with unchanged functional behavior.

**Step 4: Commit**

```bash
git add src/voice/rag_client.py src/voice/agent.py tests/unit/voice/test_voice_agent.py
git commit -m "refactor(voice): extract SDK-style RAG client boundary"
```

---

### Task 4: Distributed Trace Propagation (Voice -> RAG API)

**Status:** NOT STARTED

**Files:**
- Modify: `src/voice/agent.py`
- Modify: `src/api/main.py`
- Modify: `src/api/schemas.py` (if schema tightening needed)
- Test: `tests/unit/api/test_rag_api.py`

**Step 1: Write failing test for trace pass-through**

Add test that voice-origin request can pass `langfuse_trace_id` and API path keeps it in `propagate_attributes(trace_id=...)`.

**Step 2: Implement propagation path**

1. Extract/construct trace id in voice entrypoint context.
2. Pass `langfuse_trace_id` in tool request payload.
3. Keep API behavior backward-compatible when trace id missing.

**Step 3: Run tests**

Run:
```bash
uv run pytest tests/unit/api/test_rag_api.py tests/unit/voice/test_voice_agent.py -q
```
Expected: PASS.

**Step 4: Commit**

```bash
git add src/voice/agent.py src/api/main.py src/api/schemas.py tests/unit/api/test_rag_api.py tests/unit/voice/test_voice_agent.py
git commit -m "feat(observability): propagate voice trace id into RAG API path"
```

---

### Task 5: SDK Migration Runbook + Rollout

**Status:** NOT STARTED

**Files:**
- Create: `docs/VOICE-SDK-RUNBOOK.md`
- Modify: `README.md` (link runbook)

**Step 1: Document operational flow**

Include:
1. Required env vars.
2. Startup order (`--profile voice`).
3. Health checks for `rag-api`, `livekit-server`, `voice-agent`.
4. Recovery actions for SIP failures and RAG timeouts.

**Step 2: Add rollout checklist**

Checklist:
1. Shadow verification in staging.
2. 10-call smoke batch with transcript + trace validation.
3. Production canary (small % of outbound calls).

**Step 3: Commit docs**

```bash
git add docs/VOICE-SDK-RUNBOOK.md README.md
git commit -m "docs(voice): add SDK migration runbook and rollout checklist"
```

---

## Verification Gate (Before Merge)

Run:
```bash
uv run ruff check src/voice src/api tests/unit/voice tests/unit/api
uv run pytest tests/unit/voice tests/unit/api tests/unit/test_cmd_call.py -q
uv run pytest tests/integration/test_voice_pipeline.py -m integration -q
```

Expected:
1. Lint checks pass.
2. Unit tests pass.
3. Integration voice pipeline passes when Docker voice profile is up.

---

## Acceptance Criteria

1. No module-global mutable runtime state in voice agent path (`_transcript_store`, global breaker state, etc.).
2. LiveKit SDK lifecycle primitives are used for runtime initialization (`setup_fnc` + `ctx.proc.userdata`).
3. Transcript store lifecycle is safe across all shutdown paths (including missing `call_id`).
4. Voice -> RAG trace propagation works via `langfuse_trace_id` pass-through.
5. Existing user-facing behavior from issue #153 remains unchanged.
