# Issue 1090 Kommo Coverage Plan

> **For agentic workers:** Use `superpowers:executing-plans`, `superpowers:test-driven-development`, `superpowers:requesting-code-review`, and `superpowers:verification-before-completion`.

**Goal:** Add deterministic Kommo CRM error, token, lead operation, and lead-score sync coverage without real Kommo/Redis/network calls.

**Architecture:** Coverage-only work split into disjoint test files. Keep production code unchanged unless a focused test exposes a real defect.

**Tech Stack:** pytest, pytest-httpx/httpx mocks, AsyncMock, tenacity wait patching already used in Kommo tests.

---

## Routing

Lane: `Full plan` because #1090 is `lane:plan-needed`, business-critical CRM behavior, and spans request errors, OAuth token lifecycle, and lead operations.

Workers:
- `W-1090-errors`: request/HTTP error and retry behavior.
- `W-1090-tokens`: OAuth token edge cases.
- `W-1090-leads`: lead operations and lead-score sync edge cases.
- `W-1090-final`: integrate branches, verify, create PR.

## Constraints

- Root `AGENTS.md` and `telegram_bot/AGENTS.override.md` apply.
- Preserve service boundaries: tests target `telegram_bot/services/**`.
- Do not add dependencies.
- Use existing Kommo client/token store patterns.
- Coverage-only TDD: characterization tests for existing behavior; red phase is optional unless a real defect is found.
- Part workers must not create PRs.

## Worker Slices

### Task 1: Request Error/Retry Coverage

**Owner:** `W-1090-errors`

**Files:**
- Create: `tests/unit/services/test_kommo_client_error_paths.py`

**Acceptance Criteria:**
- 400 Bad Request raises `httpx.HTTPStatusError` and does not force-refresh.
- 429 Rate Limit retries through `_request` tenacity policy with wait disabled.
- 500/503 retries through `_request` tenacity policy with wait disabled.
- Network timeout/transport error retries and then succeeds.
- 401 refresh failure from no refresh token re-raises original 401 HTTPStatusError.

**Commands:**
- `uv run pytest tests/unit/services/test_kommo_client_error_paths.py -q`
- `make check`

### Task 2: OAuth Token Edge Coverage

**Owner:** `W-1090-tokens`

**Files:**
- Create: `tests/unit/services/test_kommo_tokens_edge_cases.py`

**Acceptance Criteria:**
- `force_refresh()` raises `RuntimeError` when no refresh token is stored.
- `_exchange_auth_code()` rejects malformed token payloads without saving.
- `_refresh_tokens()` rejects malformed refresh payloads without saving.
- `_token_request()` rejects non-dict JSON response.
- `_load_tokens()` decodes mixed bytes/str Redis hash values.

**Commands:**
- `uv run pytest tests/unit/services/test_kommo_tokens_edge_cases.py -q`
- `make check`

### Task 3: Lead Operations And Score Sync Coverage

**Owner:** `W-1090-leads`

**Files:**
- Create: `tests/unit/services/test_kommo_client_lead_operations_edges.py`
- Create: `tests/unit/services/test_lead_score_sync_edges.py`

**Acceptance Criteria:**
- `create_lead()` sends alias-aware payload list and parses embedded lead.
- `update_lead()` sends PATCH payload with excluded `None` fields.
- `search_leads()` preserves embedded contacts without mutating caller-owned payload unexpectedly.
- `update_lead_score()` propagates idempotency header.
- `sync_pending_lead_scores()` continues after one failed score and syncs later records.

**Commands:**
- `uv run pytest tests/unit/services/test_kommo_client_lead_operations_edges.py tests/unit/services/test_lead_score_sync_edges.py -q`
- `make check`

### Task 4: Final Integration

**Owner:** `W-1090-final`

**Steps:**
- Merge `origin/fix/1090-errors-tests`, `origin/fix/1090-token-tests`, and `origin/fix/1090-lead-tests`.
- Run focused tests from all new files.
- Run `make check`.
- Create PR against `dev` with `Closes #1090`.

**Done Definition:**
- Plan exists before implementation.
- Part branches have focused verification evidence.
- PR targets `dev`, links #1090, and includes verification.
- Orchestrator reviews diff and checks CI before merge.
