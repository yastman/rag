# Langfuse Coverage & Trace Quality — Execution Plan

**Date:** 2026-05-07
**Branch:** `plan/langfuse-coverage-trace-quality`
**Base:** `dev`
**Planner:** `W-langfuse-coverage-plan`
**Scope:** #1307, #1367, #1369, #1253 (parent roadmap #1415)

---

## 1. Executive Summary

This plan reconciles stale GitHub comments with current code and issue states, then defines the smallest executable slices to close the Langfuse coverage/trace-quality queue.
**No code changes are made in this worker; only planning artifacts are produced.**

### Closed / Resolved Context

| Issue / PR | State | Notes |
|---|---|---|
| #1305 | **CLOSED** | Runtime-events analyzer delivered; available for correlation work. |
| #1362 | **CLOSED** | `langfuse.openai.AsyncOpenAI` orphan-trace issue closed; audit evidence in #1307 remains relevant because flat `litellm-acompletion` traces are still the dominant trace family. |
| PR #1290 (#1253) | **CLOSED unmerged** | `fix/1253-trace-context-propagation` was closed 2026-05-04 15:31 UTC without merge (`mergedAt: null`). The 2026-05-04 issue comment claiming PR #1290 is **open** is **stale** as of 2026-05-07. |

### Open Issues — Snapshot

| Issue | State | Remaining Risk |
|---|---|---|
| #1307 | OPEN, `in-progress` | Local Langfuse bring-up is **blocked** by stale images, Postgres password drift, and invalid secrets (see `docs/audits/2026-05-07-docker-langfuse-health-audit.md`). Trace-coverage verification cannot proceed until the stack starts. |
| #1367 | OPEN, `lane:plan-needed` | 5 modules still have **zero** `@observe` coverage after PRs #1374 and #1375. |
| #1369 | OPEN, `lane:plan-needed` | Duplicate `detect-agent-intent` fixed by PR #1376; `service-generate-response` WARNING-level semantics remain to audit. |
| #1253 | OPEN, `has-pr` label stale | Trace-context propagation between RAG pipeline and SDK agent graphs is **unimplemented** (PR #1290 closed unmerged). |
| #1415 | OPEN | Parent observability roadmap; these four issues are the next concrete slices. |

---

## 2. Stale Comment Reconciliation

### #1253 — Stale PR state
- **Comment dated 2026-05-04 11:32 UTC** says: "PR #1290 (`fix/1253-trace-context-propagation`) is open against `dev`."
- **Current fact (2026-05-07):** PR #1290 state = `CLOSED`, `mergedAt: null`, `closedAt: 2026-05-04T15:31:59Z`.
- **Impact:** The `has-pr` label on #1253 is stale and should be removed. Implementation must be replanned because the branch (`fix/1253-trace-context-propagation`) contains the unmerged commit `5cf5d66e` but never reached `dev`.

### #1307 — Stale blocker references
- Issue body and comments reference #1305 as a dependency for runtime-events analyzer correlation.
- **Current fact:** #1305 is CLOSED. The correlation phase is **unblocked** and can proceed once Langfuse is healthy.

### #1362 — Stale orphan-trace framing
- Audit evidence (`docs/audits/2026-05-05-langfuse-trace-8d79036a-audit.md`) frames flat `litellm-acompletion` traces as caused by #1362.
- **Current fact:** #1362 is CLOSED. The flat traces persist because the **LiteLLM proxy callback** (`docker/litellm/config.yaml: success_callback: ["langfuse"]`) creates its own traces independently of the bot's `@observe` instrumentation. This is a **product/config gap**, not the same orphan-trace bug.

---

## 3. Issue-by-Issue Plan

### 3.1 #1307 — Local Langfuse bring-up and trace coverage verification

**Current blockers (runtime, not code):**
1. Stale Python 3.14 images for `bot`, `mini-app-api`, `rag-api` → `langfuse` v4 crashes with Pydantic v1 `ConfigError`.
2. Postgres data-volume password mismatch → Langfuse web/worker Prisma P1000 auth failures.
3. Invalid `ENCRYPTION_KEY` / `SALT` / `NEXTAUTH_SECRET` lengths → Langfuse worker Zod validation error.

**These are documented in `docs/audits/2026-05-07-docker-langfuse-health-audit.md` and must be resolved before any trace-validation work can begin.**

**Implementation slices (post-blocker):**

| Slice | Task | Type | Reserved Files | Tests / Evidence |
|---|---|---|---|---|
| 1307-A | Rebuild Python images (`docker compose build bot mini-app-api rag-api`) and fix Langfuse secrets/Postgres credentials. | Runtime validation | `docker/litellm/config.yaml`, `compose*.yml` (docs-only recommendations) | `docker compose ps`, `curl ${LANGFUSE_HOST}/api/public/health` |
| 1307-B | Run `make run-bot` with Langfuse enabled and exercise text-RAG, apartment search, history, HITL paths. | Runtime validation | N/A (runtime only) | `logs/bot-run.log` must show `Startup verdict: OK` and no 401 OTEL errors |
| 1307-C | Validate traces using `make validate-traces-fast` and trace-contract tests (`tests/contract/test_trace_families_contract.py`). | Heavy check | `tests/contract/*`, `tests/observability/trace_contract.yaml` | `pytest tests/contract/test_trace_families_contract.py -v` |
| 1307-D | Correlate Langfuse traces with #1305 runtime-events analyzer output. | Runtime validation | N/A | Cross-reference `telegram_bot/runtime_events` JSON with trace IDs |
| 1307-E | Produce coverage gap report: list covered vs missing spans/paths, create follow-up issues with exact file/function references. | Docs / Planning | `docs/runbooks/LANGFUSE_TRACING_GAPS.md` | Markdown report |

**Focused tests for #1307:**
- `tests/contract/test_trace_families_contract.py` — static AST check that required families have `@observe` decorators.
- `tests/contract/test_span_coverage_contract.py` — verifies `capture_input=False, capture_output=False` on sensitive spans.
- `tests/observability/trace_contract.yaml` — canonical contract; update if new spans are discovered.

**Heavy checks (require running Langfuse):**
- `make validate-traces-fast`
- `langfuse api traces list --name telegram-message --limit 5`
- `langfuse api traces list --name rag-api-query --limit 5`
- `langfuse api traces list --name voice-session --limit 5`

**Decision required:** Whether to disable LiteLLM proxy's Langfuse callback (`success_callback: []`) to eliminate flat `litellm-acompletion` noise, or to keep it for raw LLM-cost tracking. This is a **product decision** (#1415).

---

### 3.2 #1367 — Blind spots: 7 modules with zero Langfuse coverage

**Done (merged to `dev`):**
- PR #1374 (merged 2026-05-05) — Added `@observe` to contextualization providers (`src/contextualization/{claude,openai,groq}.py`).
- PR #1375 (merged 2026-05-05) — Added `@observe` to cross-encoder reranker (`src/retrieval/reranker.py:67`).

**Remaining zero-coverage modules (confirmed by AST scan 2026-05-07):**

| Module | Missing Instrumentation | Complexity | Proposed Slice |
|---|---|---|---|
| `src/retrieval/search_engines.py:359,532,709` | `embedding_model.encode()` | Medium | 1367-A |
| `src/core/pipeline.py:119` | `embedding_model.encode()` | Low | 1367-B |
| `src/ingestion/indexer.py:376` | `embedding_model.encode()` | Medium | 1367-C |
| `services/bge-m3-api/app.py` | All `/encode/*` and `/rerank` endpoints | Medium | 1367-D |
| `services/user-base/main.py:123,133` | `model.encode()` | Low | 1367-E |

**SDK guidance gap:** `src/contextualization/openai.py` still imports plain `openai.AsyncOpenAI` (line 4) instead of `langfuse.openai.AsyncOpenAI`. The `@observe` decorator captures the function boundary, but the inner LLM call is **not auto-traced** by Langfuse's OpenAI drop-in. This is a **separate slice**:

| Slice | Task | Type | Reserved Files | Tests |
|---|---|---|---|---|
| 1367-F | Switch `src/contextualization/openai.py` to `langfuse.openai.AsyncOpenAI` (or verify plain client is intentional). | Implementation | `src/contextualization/openai.py` | Unit test for contextualization path |

**Focused tests for #1367:**
- `tests/contract/test_trace_families_contract.py::test_all_contract_spans_exist_in_codebase` — will fail if new spans are added but not documented in `trace_contract.yaml`.
- `tests/contract/test_span_coverage_contract.py::test_sensitive_spans_have_capture_disabled` — any new sensitive span must have `capture_input=False, capture_output=False`.
- `tests/contract/test_span_coverage_contract.py::test_all_observed_spans_accounted_for` — drift detection for spans with `capture_input=False`.

**Implementation notes:**
- `services/bge-m3-api/app.py` and `services/user-base/main.py` are **FastAPI services** outside the `telegram_bot/` package. They need their own `initialize_langfuse()` call or env-based client setup.
- `src/ingestion/indexer.py` runs in CLI/batch mode; `@observe` works but `propagate_attributes()` must wrap the entry-point (`src/ingestion/unified/observability.py` already has some patterns).
- `src/retrieval/search_engines.py` and `src/core/pipeline.py` are in the `src/` package; use `@observe(name="...", capture_input=False, capture_output=False)` on the `encode()` wrapper methods.

---

### 3.3 #1369 — Duplicate `detect-agent-intent` and `service-generate-response` WARNING level

**Done (merged to `dev`):**
- PR #1376 (merged 2026-05-05) — Removed duplicate `detect-agent-intent` by passing precomputed `agent_intent` into `run_client_pipeline()`.

**Remaining scope:**

#### 1369-A — Audit `service-generate-response` WARNING semantics

**Current code (`telegram_bot/services/generate_response.py`):**
- Line 829: `level="WARNING"` when streaming fails and falls back to non-streaming.
- Line 979: `level="WARNING"` when TTFT drift exceeds threshold (default 500 ms).

**Trace contract (`tests/observability/trace_contract.yaml`) allows:**
```yaml
- span: service-generate-response
  level: ERROR
  trigger: "Generation failed"
- span: service-generate-response
  level: WARNING
  trigger: "Streaming/fallback degradation"
```

**Question to resolve:** Are both WARNING sites justified, or is one of them incorrectly downgrading the entire `service-generate-response` span for a condition that should be a child-span warning or a score instead?

**Investigation steps:**
1. Check recent traces in Langfuse UI for `service-generate-response` spans with `level=WARNING` where the final response was successfully delivered.
2. If TTFT drift WARNING appears on successful streaming responses, consider moving it to a child span (`generate-answer`) or to a score key (`llm_ttft_drift_ms`).
3. If streaming-fallback WARNING appears when the fallback also succeeds, the contract is correct but the visual noise may be excessive; document the behavior in `docs/runbooks/LANGFUSE_TRACING_GAPS.md`.

**Type:** Design-first / PR review task.
**Reserved files:** `telegram_bot/services/generate_response.py`, `tests/observability/trace_contract.yaml`
**Focused tests:** `tests/unit/services/test_generate_response.py` (check WARNING assertions)

---

### 3.4 #1253 — Trace context propagation between RAG pipeline and SDK agent graphs

**Current state:**
- PR #1290 (`fix/1253-trace-context-propagation`) is **CLOSED unmerged** (`mergedAt: null`).
- The branch `fix/1253-trace-context-propagation` contains commit `5cf5d66e` but it never reached `dev`.
- Issue #1253 still has the stale `has-pr` label.

**Problem restated:**
When `bot.py` routes a query through the agent graph (`agent.ainvoke()`) and the agent uses the `rag_search` tool, the RAG pipeline graph produces a **separate top-level trace** in Langfuse. There is no parent-child relationship.

**Root cause:**
- `telegram_bot/agents/rag_tool.py` calls the RAG pipeline directly (intra-process).
- Langfuse trace context is **not propagated** across this boundary.
- `src/voice/agent.py` already solves this for voice→RAG API by passing `langfuse_trace_id` via HTTP header.

**Proposed implementation slices:**

| Slice | Task | Type | Reserved Files | Tests |
|---|---|---|---|---|
| 1253-A | Extract current trace ID in `telegram_bot/agents/rag_tool.py` and pass it into the pipeline invocation. | Implementation | `telegram_bot/agents/rag_tool.py` | Unit test mocking `get_client().get_current_trace_id()` |
| 1253-B | Accept `langfuse_trace_id` in `telegram_bot/pipelines/client.py::run_client_pipeline()` and wrap with `propagate_attributes()`. | Implementation | `telegram_bot/pipelines/client.py` | Unit test for trace ID propagation |
| 1253-C | Verify that `telegram_bot/graph/graph.py` compiled graph respects the propagated context when calling `@observe`-decorated nodes. | PR review | `telegram_bot/graph/graph.py` | `tests/unit/graph/test_error_spans.py` |
| 1253-D | Add contract test: `tests/contract/test_trace_context_propagation.py` — assert that agent→pipeline calls reuse the same trace ID. | Focused test | `tests/contract/test_trace_context_propagation.py` | pytest |
| 1253-E | Runtime validation: run a bot query that triggers agent→RAG tool, then inspect Langfuse trace tree for nested spans. | Heavy check | N/A | Manual Langfuse CLI check |

**SDK-native approach (preferred per SDK registry):**
- Use `propagate_attributes(session_id=..., user_id=..., trace_id=...)` at the RAG tool entry-point.
- Pass `langfuse_trace_id` as a string argument through the tool→pipeline boundary.
- Avoid custom trace-propagation wrappers; prefer native Langfuse APIs.

**Decision required:** Should #1253 reuse the unmerged PR #1290 branch, or start fresh? The branch is 5+ days old and may have drifted from `dev`. **Recommendation:** Start fresh from `dev`, cherry-pick any reusable commits, and open a new PR.

---

## 4. Task DAG

```
# Blockers (must resolve first)
1307-A  [Runtime] Fix local Docker stack (images, secrets, Postgres)
   │
   ▼
# Parallel implementation slices (no cross-dependencies)
├─ 1307-B  [Runtime] Bot smoke-test with Langfuse enabled
├─ 1307-C  [Test]    Trace-family contract validation
├─ 1367-A  [Impl]    search_engines.py @observe
├─ 1367-B  [Impl]    core/pipeline.py @observe
├─ 1367-C  [Impl]    ingestion/indexer.py @observe
├─ 1367-D  [Impl]    services/bge-m3-api/app.py @observe
├─ 1367-E  [Impl]    services/user-base/main.py @observe
├─ 1367-F  [Impl]    contextualization/openai.py langfuse.openai
├─ 1369-A  [Review]  service-generate-response WARNING audit
├─ 1253-A  [Impl]    rag_tool.py trace ID extraction
├─ 1253-B  [Impl]    client.py propagate_attributes wrapper
├─ 1253-C  [Review]  graph.py context respect verification
├─ 1253-D  [Test]    Contract test for trace propagation
│
# After 1307-A + 1307-B
├─ 1307-D  [Runtime] Correlate traces with runtime-events analyzer
├─ 1307-E  [Docs]    Coverage gap report
├─ 1253-E  [Heavy]   Runtime validation of nested agent→pipeline traces
```

**Critical path:** `1307-A` → `1307-B` → (`1307-D`, `1307-E`, `1253-E`).

---

## 5. Reserved Files for Implementation Waves

### Wave 1 — #1367 zero-coverage modules
- `src/retrieval/search_engines.py`
- `src/core/pipeline.py`
- `src/ingestion/indexer.py`
- `services/bge-m3-api/app.py`
- `services/user-base/main.py`
- `src/contextualization/openai.py`
- `tests/contract/test_trace_families_contract.py`
- `tests/contract/test_span_coverage_contract.py`
- `tests/observability/trace_contract.yaml`

### Wave 2 — #1253 trace propagation
- `telegram_bot/agents/rag_tool.py`
- `telegram_bot/pipelines/client.py`
- `telegram_bot/graph/graph.py`
- `tests/contract/test_trace_context_propagation.py` (new)

### Wave 3 — #1369 WARNING semantics
- `telegram_bot/services/generate_response.py`
- `tests/observability/trace_contract.yaml`
- `tests/unit/services/test_generate_response.py`

### Wave 4 — #1307 runtime validation
- `docs/runbooks/LANGFUSE_TRACING_GAPS.md`
- `docs/audits/` (append-only)
- `tests/contract/test_trace_families_contract.py`
- `tests/contract/test_span_coverage_contract.py`

---

## 6. Test Strategy

### Local-fast (no Docker, no Langfuse)
| Test | Command | Why |
|---|---|---|
| Trace families contract | `pytest tests/contract/test_trace_families_contract.py -v` | AST scan for `@observe` decorators |
| Span coverage contract | `pytest tests/contract/test_span_coverage_contract.py -v` | Capture flags and as_type contracts |
| Error span contract | `pytest tests/contract/test_error_contract.py -v` | Allowed `update_current_span(level=ERROR/WARNING)` files |
| Unit: generate_response | `pytest tests/unit/services/test_generate_response.py -v` | WARNING-level assertions |
| Unit: observability | `pytest tests/unit/test_observability.py -v` | Client init, PII masking |

### Heavy (requires Langfuse + bot runtime)
| Test | Command | Why |
|---|---|---|
| Trace validation fast | `make validate-traces-fast` | Required trace families exist and are fresh |
| Bot smoke test | `timeout 120 make run-bot` | Bot starts, polling begins, no OTEL 401s |
| Langfuse health | `curl -s ${LANGFUSE_HOST}/api/public/health \| jq` | Langfuse web healthy |
| Trace tree inspection | `langfuse api traces get <id> --fields core,io,scores,observations,metrics` | Manual verification of nested spans |

---

## 7. Heavy Checks — Local Langfuse Contract

Before any runtime-validation slice, confirm:

1. **Images rebuilt:** `docker compose -f compose.yml -f compose.dev.yml build bot mini-app-api rag-api`
2. **Secrets valid:** `ENCRYPTION_KEY` is 64 hex chars, `SALT` and `NEXTAUTH_SECRET` are ≥ 32 chars.
3. **Postgres aligned:** `docker exec -i dev_postgres_1 psql ...` accepts the current env password over Docker network.
4. **Langfuse healthy:** `curl -s http://127.0.0.1:3001/api/public/health` returns `{"status":"ok"}`.
5. **Bot starts without OTEL 401:** `logs/bot-run.log` shows `urllib3 ... "POST /api/public/otel/v1/traces HTTP/1.1" 200`.

These are **not started by this planner**; they are prerequisites for the runtime-validation workers.

---

## 8. New Bugs / Findings

| Finding | Evidence | Disposition |
|---|---|---|
| Stale PR #1290 comment on #1253 | Issue comment 2026-05-04 says PR is open; GH API shows `CLOSED`/`mergedAt: null` | Update issue label `has-pr` → remove; add comment |
| `src/contextualization/openai.py` uses plain `openai.AsyncOpenAI` | Line 4: `from openai import AsyncOpenAI` despite SDK registry requiring `langfuse.openai.AsyncOpenAI` | Address in slice 1367-F |
| `litellm-acompletion` flat traces are ~40% of recent traces | Audit `2026-05-05-langfuse-recent-traces-structure-audit.md` | Product decision (#1415): disable LiteLLM callback or keep for cost tracking |
| Local `dev` stack non-functional | Audit `2026-05-07-docker-langfuse-health-audit.md` | Runtime blocker for #1307 and #1253-E |
| #1362 label still on some issues/comments | #1362 is CLOSED but referenced as active blocker in 2026-05-05 audit | Update comments to reference #1415 or current open issues |

---

## 9. Recommended Actions (Not in this PR)

1. **Remove stale `has-pr` label from #1253.**
2. **Update `docs/runbooks/LANGFUSE_TRACING_GAPS.md`** with the `litellm-acompletion` product-gap note (proxy-generated flat traces are expected noise).
3. **Re-audit trace `8d79036a-36f4-4398-84aa-6839a1fcf040`** after local stack is healthy to confirm whether the flat trace is still produced by LiteLLM proxy or if bot-native traces now appear.
4. **Schedule product decision on LiteLLM callback** under #1415.

---

*End of plan.*
