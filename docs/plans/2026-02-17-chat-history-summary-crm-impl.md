# ADR: Chat History + CRM (Kommo) Unified Implementation Plan

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Date** | 2026-02-17 |
| **Decision** | 10-step implementation plan for unified supervisor + CRM runtime |
| **Related issues** | #305, #310, #312, #313, #314, #315, #316, #317, #318, #319, #320, #322, #324 |
| **Supersedes** | n/a |

Scope: `telegram_bot/**`, `src/**`, `docker-compose.dev.yml`, `tests/**`

## 1) Current State Audit (as-is)

- Foundation from #305 is **DONE** (PR #309, merged 2026-02-17):
  - `SessionSummary` Pydantic v2 model in `telegram_bot/services/session_summary.py`;
  - `generate_summary()` with `responses.parse` primary + `beta.chat.completions.parse` fallback;
  - `format_summary_as_note()` for CRM note formatting;
  - `get_session_turns()` in `telegram_bot/services/history_service.py` (Qdrant scroll, pagination, 500 cap);
  - Feature flags in `telegram_bot/config.py`: `session_summary_enabled`, `kommo_enabled`, `use_supervisor`;
  - 36 unit tests (18 for session_summary + 8 for get_session_turns + config tests).
- Supervisor architecture implemented, but monolith path still active by default:
  - `telegram_bot/config.py`: `use_supervisor=false` (default).
  - `telegram_bot/bot.py`: legacy `build_graph()` path remains primary.
  - `telegram_bot/graph/nodes/classify.py` and monolith route not removed.
- No runtime Kommo CRM integration yet:
  - config fields `kommo_*` exist;
  - no `KommoClient` / CRM toolchain (`create deal`, `link contact`, `add note`, `task`).
- Test baseline is stable:
  - `make check` PASS
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit` PASS

## 2) Goal

Build a unified production path:

`Telegram -> LangGraph Supervisor Tools -> Qdrant/Redis -> Kommo CRM -> Langfuse`

Without parallel monolith runtime, with SDK-first policy and reproducible local prod-like validation.

## 3) Confirmed Residual Risks

1. Need to confirm `langfuse.openai.AsyncOpenAI` stable support for `responses.parse` in target environment (#315).
2. Kommo needs a PoC decision between community SDK and first-party async adapter (`httpx`) before full lifecycle implementation (#313).
3. Until #310 closes, dual path (supervisor + legacy) complicates observability and regression validation.

## 4) Implementation Plan (10 steps)

### Step 1. Lock plan/ADR baseline for #305/#312/#313 -- DONE

- Fixed this file as source-of-truth for Chat History + CRM implementation.
- Updated issue bodies in #305/#312/#313 to reference existing documents.
- ADR headers added to design and impl docs.
- Phase 1 (#305) marked DONE (PR #309, merged 2026-02-17).
- Doc-link drift fixed: collection name `conversation_history` (not `chat_history`).
- Tracked in: #324 Step 1.

### Step 2. Close `responses.parse` risk (#315)
- Add integration-safe tests for `generate_summary()`:
  - path A: `responses.parse`;
  - path B: fallback `beta.chat.completions.parse`;
  - path C: controlled fail-soft.
- DoD: stable tests without network, no dependency on specific vendor endpoint.

### Step 3. Kommo SDK decision PoC (#313)
- Compare 2 approaches:
  - A: first-party `KommoClient` (`httpx`, async, retries, typed errors);
  - B: best community SDK.
- Minimal PoC scope: token refresh, contact upsert, deal create, note add, task create.
- DoD: `Adopt/Reject` decision fixed in `docs/plans/2026-02-17-kommo-sdk-poc-decision.md`.

### Step 4. Implement unified Kommo client contract (#312)
- Create `telegram_bot/services/kommo_client.py`:
  - `upsert_contact_by_telegram`
  - `create_deal`
  - `link_contact_to_deal`
  - `add_lead_note`
  - `create_followup_task`
- DoD: unified API contract, idempotent request keys, fail-soft error mapping.

### Step 5. Add CRM tools in supervisor path (#312)
- Implement tool layer:
  - `crm_generate_deal_draft`
  - `crm_finalize_deal_from_session`
  - helper tools for note/task/contact.
- Link summary output (`SessionSummary`) to `DealDraft` transformation.
- DoD: deal lifecycle executes via tools path without insertions in legacy handlers.

### Step 6. Remove monolith query runtime (#310)
- Switch default to supervisor-only.
- Remove/freeze legacy query route in `bot.py` (except controlled rollback via release revert).
- DoD: single runtime path for text queries goes through supervisor graph.

### Step 7. Unified observability (LangGraph + Langfuse) (#241)
- Verify supervisor + CRM tools write one trace tree and score signals:
  - `agent_used`
  - `crm_write_success`
  - `crm_deal_created`
  - `crm_deal_create_latency_ms`
- DoD: no split-trace behavior for a single user request.

### Step 8. SDK-first cleanup (#314, #316)
- `src/evaluation/search_engines.py`: replace raw REST Qdrant calls with SDK.
- Consolidate duplicate local model wrappers into one internal SDK layer.
- DoD: no duplicate custom HTTP wrappers for the same endpoint groups.

### Step 9. Local prod-like validation (bot + Docker)
- Rebuild and verify minimal profile:
  - `docker compose --compatibility -f docker-compose.dev.yml --profile bot build`
  - `USE_SUPERVISOR=true docker compose --compatibility -f docker-compose.dev.yml --profile bot up -d`
  - `make docker-ps`
  - `make test-smoke-routing`
- Separately close infra issues: #318, #319, #320, #322.
- DoD: bot starts and processes supervisor path in local environment.

### Step 10. Final quality gate and release checklist
- Required checks:
  - `make check`
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
  - `uv run pytest tests/integration/test_graph_paths.py -v`
  - targeted CRM/supervisor tests.
- DoD: unified changelog/issue-status update + ready to merge to `main`.

## 5) Queue and Prioritization (current backlog)

1. #299 + #296: #299 already closed, focus on #296.
2. #283
3. #268
4. #306
5. #281
6. #267 + #291 + #249 + #243
7. #310 -> #241 -> #312 (critical architectural track)
8. #225/#226/#227
9. #232 + #228 (blocked)
10. #233 -> #234 (blocked)

Note: CRM lifecycle progress requires prior completion of item 7.

## 6) Plan Assessment

This plan is realistic and technically correct. Summary of current state:

- strong: supervisor + history foundation already exists (Phase 1 DONE);
- critical gap: Kommo tools lifecycle not yet implemented;
- critical gap: legacy monolith runtime not yet removed;
- organizational gap: resolved -- plan docs now exist and have ADR headers.

After completing Steps 2-10 the system becomes truly unified.
