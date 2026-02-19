# Langfuse Trace & Score Integrity Audit — #476

**Date:** 2026-02-19
**Branch:** `audit/langfuse-traces-476`
**Auditor:** Claude Sonnet 4.6 (automated static analysis)
**Scope:** `telegram_bot/observability.py`, `telegram_bot/bot.py`, `telegram_bot/scoring.py`, `telegram_bot/agents/rag_tool.py`, `telegram_bot/agents/history_tool.py`, `telegram_bot/agents/crm_tools.py`

---

## 1. Enablement & Config

### Mechanism

```python
LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_SECRET_KEY"))
```

Evaluated once at module import. No runtime toggle — requires restart to change.

### Graceful No-Op (LANGFUSE_ENABLED=False)

| Symbol | Disabled Stub | Behavior |
|--------|---------------|----------|
| `observe` | `_noop_observe` | Returns function unchanged (zero overhead) |
| `get_client()` | `_noop_get_client()` | Returns `_NullLangfuseClient` — all methods are no-ops |
| `propagate_attributes` | `_noop_propagate` | `@contextmanager` that yields immediately |
| `get_langfuse_client()` | returns `None` | Callers check `if lf_client is not None:` |
| `create_callback_handler()` | returns `None` | Bot wraps in `if langfuse_handler:` |

**Verdict:** No-op path is complete and safe. Disabling Langfuse has zero user-visible impact.

### Startup Logging

```
INFO telegram_bot.observability — Langfuse observability ENABLED
INFO telegram_bot.observability — Langfuse observability DISABLED (LANGFUSE_SECRET_KEY not set)
```

**Verdict:** Startup mode is logged at INFO level. ✓

### Minor Finding

`_NullLangfuseClient.get_current_trace_id()` returns `""` (empty string). Callers use `lf.get_current_trace_id() or ""`, which is consistent. No issue.

---

## 2. Trace Coverage Map

### Entry Points

| Handler | Decorator | Trace Name | `propagate_attributes` | Tags |
|---------|-----------|------------|------------------------|------|
| `handle_query` | `@observe(name="telegram-rag-query")` | `telegram-rag-query` | Delegated to `_handle_query_supervisor` | — |
| `_handle_query_supervisor` | `@observe(name="telegram-rag-supervisor")` | `telegram-rag-supervisor` | `session_id`, `user_id`, `["telegram","rag","agent"]` | ✓ |
| `handle_voice` | `@observe(name="telegram-rag-voice")` | `telegram-rag-voice` | `session_id`, `user_id`, `["telegram","rag","voice"]` | ✓ |
| `cmd_history` | `@observe(name="telegram-history-search")` | `telegram-history-search` | `session_id`, `user_id`, `["telegram","history"]` | ✓ |

### Child Spans

| Tool / Agent Span | Decorator | Curated I/O |
|-------------------|-----------|-------------|
| `rag_search` | `@observe(name="tool-rag-search", capture_input=False, capture_output=False)` | `query_preview` (in), `response_length` (out) |
| `history_search` | `@observe(name="tool-history-search", capture_input=False, capture_output=False)` | `query_preview`, `deal_id` (in), `summary_length`, `history_cache_hit` (out) |
| `crm_get_deal` | `@observe(name="crm-get-deal")` | auto-capture |
| `crm_get_contacts` | `@observe(name="crm-get-contacts")` | auto-capture |
| `crm_create_lead` | `@observe(name="crm-create-lead")` | auto-capture |
| `crm_update_lead` | `@observe(name="crm-update-lead")` | auto-capture |
| `crm_upsert_contact` | `@observe(name="crm-upsert-contact")` | auto-capture |
| `crm_add_note` | `@observe(name="crm-add-note")` | auto-capture |
| `crm_create_task` | `@observe(name="crm-create-task")` | auto-capture |
| `crm_link_contact_to_deal` | `@observe(name="crm-link-contact-to-deal")` | auto-capture |

### Scores Written Per Path

| Path | Score Function | Score Count |
|------|---------------|-------------|
| Text (rag_search tool) | `write_langfuse_scores()` | 14 core + ~12 conditional |
| Text (supervisor) | inline `create_score()` | `supervisor_model`, `user_role`, `tool_calls_total`, `history_save_success` |
| Text (supervisor) | `write_crm_scores()` | 4 CRM scores |
| Voice | `write_langfuse_scores()` | 14 core + ~12 conditional |
| Voice | inline `create_score()` | `history_save_success`, `history_backend` |
| /history | `write_history_scores()` | 4 history scores |
| Feedback callback | `get_langfuse_client().create_score()` | `user_feedback` |
| Guard block (pre-agent) | inline `score()` | `guard_blocked`, `injection_pattern` |

### Orphan Trace Risk

All 4 entry points use `propagate_attributes()` before invoking `@observe`-decorated functions. No orphan traces observed.

---

## 3. Score Integrity

### Idempotency Pattern

The `score()` helper in `scoring.py` enforces idempotency via:

```python
lf.create_score(
    trace_id=trace_id,
    name=name,
    value=value,
    id=f"{trace_id}-{name}",   # ← idempotency key
    **kwargs,
)
```

All calls through `write_langfuse_scores()`, `write_history_scores()`, `write_crm_scores()` use this helper. ✓

### Cross-Trace Leakage (Issue #435)

All scoring functions require explicit `trace_id` parameter:

- `write_langfuse_scores(lf, result, trace_id=tid)` — falls back to `lf.get_current_trace_id()`, returns early if empty ✓
- `write_history_scores(lf, tid, ...)` — positional `trace_id`, returns if empty ✓
- `write_crm_scores(lf, messages, trace_id=tid)` — returns if empty ✓

No ambient trace context without explicit `trace_id`. **Cross-trace leakage risk: LOW.** ✓

### Finding F-01: Inconsistent Idempotency Key Parameter in `handle_feedback`

**File:** `telegram_bot/bot.py:1227`
**Severity:** LOW
**Impact:** Potential duplicate `user_feedback` scores if feedback button clicked twice rapidly

```python
# handle_feedback uses score_id= (not id=)
lf_client.create_score(
    trace_id=trace_id,
    name="user_feedback",
    value=value,
    data_type="NUMERIC",
    comment=f"user_id:{user_id}",
    score_id=f"{trace_id}-user_feedback",  # ← should be id=
)
```

The `score()` helper and all other inline `create_score()` calls in `bot.py` use `id=`. In Langfuse v3 SDK, the idempotency key is `id`. The `score_id` parameter may be silently ignored, allowing duplicate scores on rapid double-clicks.

---

## 4. Metadata Schema Consistency

### Text Path (sdk_agent)

```python
lf.update_current_trace(
    input={"query": message.text},
    output={"response": response_text},
    metadata={
        "pipeline_mode": "sdk_agent",
        "pipeline_wall_ms": wall_ms,
    },
)
```

**Metadata fields:** 2 (minimal)

### Voice Path

```python
lf.update_current_trace(
    input={"voice_duration_s": voice.duration, "stt_text": result.get("stt_text", "")},
    output={"response": result.get("response", "")},
    metadata=_build_trace_metadata(result),  # returns ~15 fields
)
```

**Metadata fields:** ~15 via `_build_trace_metadata()`

### Finding F-02: Text Path Metadata Significantly Thinner Than Voice Path

**Severity:** LOW
**Impact:** Dashboard queries on `metadata.cache_hit`, `metadata.query_type`, etc. will not find text-path traces

`_build_trace_metadata()` includes: `input_type`, `query_type`, `cache_hit`, `search_results_count`, `rerank_applied`, `llm_provider_model`, `llm_ttft_ms`, `response_style`, `response_difficulty`, `stt_duration_ms`, `embedding_error`, `memory_messages_count`, `checkpointer_overhead_proxy_ms`, `pipeline_cleanup_error`.

The text path omits all of these. Text-path behavioral data only exists as Langfuse **scores**, not as trace metadata. This is architecturally consistent (scores are queryable) but creates a dashboard schism.

### `/history` Path

```python
lf.update_current_trace(
    input={"command": "/history", "query": query},
    output={"results_count": len(results), "valid_count": len(valid)},
    metadata={"user_id": user_id, "search_latency_ms": round(search_ms, 1)},
)
```

### Finding F-03: Raw Integer `user_id` in `/history` Trace Metadata

**File:** `telegram_bot/bot.py:607-611`
**Severity:** MEDIUM
**Impact:** Telegram user ID written as raw integer to Langfuse trace metadata

```python
metadata={"user_id": user_id, ...}   # user_id is raw int (e.g. 523847291)
```

Even if PII masking were applied, `mask_pii()` does not handle integers (only strings). The Telegram user ID is PII under GDPR.

### Session ID Format Consistency

All paths use `make_session_id()` → `{type}-{hash8}-{YYYYMMDD}` format ✓

| Path | session_type |
|------|-------------|
| Text | `"chat"` |
| Voice | `"chat"` |
| /history | `"history"` |

---

## 5. PII Masking

### Architecture

```python
# get_langfuse_client() — MASKED (used ONLY in handle_feedback)
def get_langfuse_client() -> Langfuse:
    return Langfuse(mask=mask_pii, flush_at=50, flush_interval=5)

# get_client() — UNMASKED (used by ALL @observe spans)
get_client = _real_get_client   # SDK singleton, no mask= parameter
```

### mask_pii() Coverage

| PII Type | Pattern | Applied To |
|----------|---------|------------|
| Telegram user IDs | `\b\d{9,10}\b` (string) | Strings only |
| Phone numbers | `\+?\d{10,15}` (string) | Strings only |
| Email addresses | `[\w.-]+@[\w.-]+\.\w+` | Strings only |
| Long texts > 500 chars | Truncation | Strings only |
| Integer values | **NOT HANDLED** | Raw integers pass through |

### Finding F-04 (CRITICAL): PII Masking Not Applied to @observe Spans

**Severity:** HIGH
**Impact:** All Langfuse traces created via `@observe()` decorator and `get_client()` SDK calls are **NOT** masked. This includes all `update_current_trace()`, `update_current_span()` calls and all automatically captured span inputs/outputs.

**Root Cause:** The masked `Langfuse(mask=mask_pii)` client from `get_langfuse_client()` is only used in `handle_feedback` (for `user_feedback` score). The SDK singleton returned by `get_client()` (= `_real_get_client()`) is initialized without `mask=`. All `@observe` spans use this unmasked SDK singleton.

**Affected paths:**
- All `rag_search` spans — `query_preview` may contain user queries with names/phones
- All `history_search` spans — curated input includes raw query text
- CRM tools with auto-capture — could capture contact data (names, phones)
- `cmd_history` — `query` field in trace input is unmasked user text
- `_handle_query_supervisor` — `input={"query": message.text}` (unmasked)
- `handle_voice` — `input={"stt_text": ...}` may contain personal information

**Fix:** Initialize SDK with mask at startup:
```python
# In application startup, before @observe runs:
Langfuse(mask=mask_pii)  # initializes the singleton with masking
```
Or use `langfuse.configure(mask=mask_pii)` if the v3 SDK supports it.

### Finding F-05 (MEDIUM): Integer PII Not Handled by mask_pii()

**Severity:** MEDIUM
**Impact:** Integer Telegram user IDs bypass masking

`mask_pii()` only handles `str`, `dict`, `list` — raw integers fall through to `return data`. User IDs passed as integers (e.g., `{"user_id": 523847291}`) are never masked, even with the masked client.

**Fix:** Add int-to-string conversion for 9-10 digit integers:
```python
if isinstance(data, int):
    s = str(data)
    return int(re.sub(r"^\d{9,10}$", "[USER_ID]", s) or data)
    # or store as string: return "[USER_ID]" if re.match(r"^\d{9,10}$", s) else data
```

### Finding F-06 (LOW): Truncation Threshold May Be Too Short

**Severity:** LOW
**Impact:** RAG responses (typically 200-1000 chars) will be truncated at 500 chars in Langfuse

500-char truncation affects LLM response quality review in the Langfuse UI. Consider raising to 2000 or adding a separate threshold for response fields.

---

## 6. Validation Results

### validate_traces.py

```
ERROR LANGFUSE_PUBLIC_KEY not set — cannot authenticate Langfuse API
```

**Reason:** `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` not configured in this dev environment. Bot is not running.

### make validate-traces-fast

```
error while interpolating services.bot.environment.TELEGRAM_BOT_TOKEN:
  required variable TELEGRAM_BOT_TOKEN is missing a value
```

**Reason:** Required env vars not set. Docker Compose environment not fully provisioned.

**Conclusion:** Runtime validation was not possible. All findings are based on static code analysis.

---

## 7. Findings Table

| ID | File | Location | Severity | Finding | Impact | Recommended Fix |
|----|------|----------|----------|---------|--------|-----------------|
| F-01 | `bot.py:1227` | `handle_feedback` | LOW | `score_id=` used instead of `id=` for idempotency | Possible duplicate `user_feedback` scores on rapid re-click | Change `score_id=` to `id=` |
| F-02 | `bot.py:894-901` | `_handle_query_supervisor` | LOW | Text path trace metadata has only 2 fields vs voice path's ~15 | Dashboard metadata filters won't match text-path traces | Extend text-path `update_current_trace(metadata=...)` with `_build_trace_metadata()` |
| F-03 | `bot.py:607` | `cmd_history` | MEDIUM | Raw integer `user_id` written to trace metadata | Telegram user ID (PII) exposed in Langfuse | Pass `"user_id": mask_pii(str(user_id))` |
| F-04 | `observability.py:110-124` | `get_client()` / `get_langfuse_client()` | HIGH | PII masking not applied to SDK singleton used by `@observe` | All RAG traces unmasked — queries, responses, contacts | Initialize SDK singleton with `mask=mask_pii` at startup |
| F-05 | `observability.py:39-54` | `mask_pii()` | MEDIUM | Integer values not handled — raw integer user IDs bypass masking | Integer PII passes unmasked even through masked client | Add integer handling in `mask_pii()` |
| F-06 | `observability.py:47-48` | `mask_pii()` | LOW | 500-char truncation too short for RAG responses | LLM response text truncated in Langfuse UI | Raise threshold to 2000 for response fields, or use field-specific thresholds |

---

## 8. Verdict

### OBSERVABILITY: **CONDITIONAL GO**

**Trace structure is sound:**
- Entry points are fully covered with `@observe` decorators ✓
- `propagate_attributes` used at all entry points (no orphan traces) ✓
- Score isolation via explicit `trace_id` is solid (#435 properly addressed) ✓
- Idempotency key pattern `id=f"{trace_id}-{name}"` enforced via `score()` helper ✓
- Graceful no-op when Langfuse disabled ✓
- Startup mode logging ✓

**Blockers before production approval:**

| Priority | Issue | Action Required |
|----------|-------|-----------------|
| **HIGH** | F-04: PII masking not applied to `@observe` spans | Initialize Langfuse SDK with `mask=mask_pii` at startup |
| **MEDIUM** | F-05: Integer user_ids bypass `mask_pii` | Handle `int` type in `mask_pii()` |
| **MEDIUM** | F-03: Raw `user_id` in `/history` trace metadata | Mask before writing |

**Non-blocking (can be addressed post-launch):**

| Priority | Issue |
|----------|-------|
| LOW | F-01: `score_id=` vs `id=` in `handle_feedback` |
| LOW | F-02: Text-path trace metadata thinness |
| LOW | F-06: 500-char truncation threshold |

**Summary:** The observability infrastructure is architecturally correct and well-designed. The score isolation fix (#435) is correctly implemented. The primary risk is that `mask=mask_pii` is only applied to the `get_langfuse_client()` client (used once for feedback scores), while the main SDK singleton used by all `@observe` traces is unmasked. This means user queries, RAG responses, and potentially CRM contact data flow to Langfuse without PII sanitization.
