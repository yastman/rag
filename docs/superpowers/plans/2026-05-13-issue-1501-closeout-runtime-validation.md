# Issue 1501 Closeout And Runtime Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the #1501 code-complete work responsibly by linking the merged implementation evidence, separating unrelated broad-suite instability, and collecting fresh non-production Telegram HIT/MISS Langfuse trace evidence through tmux swarm execution.

**Architecture:** Treat #1501 as a completed code change with one remaining runtime evidence lane. Keep GitHub issue management, runtime trace validation, and unrelated xdist investigation as separate bounded work items so workers do not conflate implementation correctness with environment/runtime validation. Runtime validation must use local/non-production credentials only and must produce redacted evidence suitable for a GitHub issue comment.

**Tech Stack:** GitHub CLI, tmux-swarm-orchestration, OpenCode workers, Docker Compose local stack, Telegram bot native runtime, Telethon E2E runner, Langfuse local `http://localhost:3001`, pytest, Makefile validation targets.

---

## Linked Issue

- Primary issue: [#1501](https://github.com/yastman/rag/issues/1501) `perf: reduce pre-agent BGE latency in client-direct RAG traces`
- Merged implementation PRs:
  - [#1503](https://github.com/yastman/rag/pull/1503) `57e8f280` bot pre-agent deferral
  - [#1505](https://github.com/yastman/rag/pull/1505) `a3792366` dense helper + BGE span capture suppression
  - [#1506](https://github.com/yastman/rag/pull/1506) `ee015d07` `bge_model_processing_ms` propagation
- Existing evidence comment: <https://github.com/yastman/rag/issues/1501#issuecomment-4433184357>

## Current Audit Decision

Code is complete on `origin/dev@ee015d07` and focused tests cover the intended regressions. The remaining gap is not code implementation; it is fresh runtime trace evidence for Telegram semantic cache HIT and MISS after the merged changes.

Closeout policy:

- Do not use real/prod Telegram credentials, VPS, CRM write paths, SSH, cloud credentials, or production Langfuse.
- If non-production Telegram credentials are available, collect fresh HIT/MISS traces and close #1501 with evidence.
- If non-production credentials are not available, close or mark #1501 code-complete only if the maintainer accepts focused test evidence; otherwise create a linked follow-up issue for runtime validation.
- Always create a separate issue for broad `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit` instability. It is not a #1501 blocker unless a failure reproduces in #1501 touched tests.

## File Structure

This closeout plan is mostly issue/runtime work. Code edits are not expected unless the runtime worker finds a confirmed #1501 regression.

- Create or update GitHub issue comments:
  - `#1501` final code-complete or validation-pending comment
  - optional follow-up issue: runtime HIT/MISS trace validation
  - separate follow-up issue: xdist/pytest-timeout or `test_validate_trace_runtime` instability
- Read-only references:
  - `docs/LOCAL-DEVELOPMENT.md`
  - `docs/indexes/local-runtime.md`
  - `docs/runbooks/LANGFUSE_TRACING_GAPS.md`
  - `Makefile`
  - `scripts/e2e/langfuse_trace_validator.py`
  - `tests/unit/e2e/test_langfuse_trace_validator.py`
- No planned source modifications.

If a source modification becomes necessary, stop and reclassify into a new implementation issue and PR. Do not patch source code directly from this closeout plan.

## tmux Swarm Execution

Use `$tmux-swarm-orchestration` for execution. Classification: `sequential` with one runtime worker and one issue-management worker. Runtime workers count as 2 active slots because they contend for local Docker/Langfuse/Telegram services.

### Swarm Constraints

- Base branch: `dev`
- Workers must use dedicated git worktrees.
- Workers must not modify source files unless the orchestrator explicitly reclassifies a newly confirmed bug.
- Docs lookup policy: local repo docs only. No web search.
- Required OpenCode skills:
  - Runtime validation worker: `swarm-pr-finish`
  - Issue-management worker: no full DONE JSON required unless launched as a full worker; if launched as `pr-worker`, use `swarm-pr-finish`
- Secrets policy:
  - Do not print `.env`, token values, Telethon session content, chat IDs, phone numbers, CRM payloads, or raw Telegram messages.
  - Evidence must use trace IDs, span names, boolean flags, timings, and redacted summaries only.

### Worker Wave 1: #1501 Closeout Issue Operator

**Worker name:** `W-1501-closeout-issue-operator`

**Route:** quick issue-management worker through `tmux-swarm-orchestration`

**Reserved files:** none

**Purpose:** Update GitHub issue state without touching code.

**Inputs:**
- #1501 is open.
- Implementation PRs #1503/#1505/#1506 are merged.
- Focused verification on `origin/dev@ee015d07`:
  - `uv run pytest tests/unit/test_bot_handlers.py::TestPreAgentCacheCheck -q` -> `34 passed`
  - `uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings -q` -> `7 passed`
  - `uv run pytest tests/unit/test_observability_span_metadata.py::TestBGEIntegrationWrapperSpanMetadata -q` -> `8 passed`
  - `uv run pytest tests/unit/pipelines/test_client_pipeline.py -k "pre_agent or sparse_and_colbert or semantic_cache_already_checked or bge_model_processing" -q` -> `6 passed`

**Expected output:** A GitHub issue comment on #1501 that links this plan and states the next runtime validation path.

### Worker Wave 2: Non-Production Runtime HIT/MISS Trace Validation

**Worker name:** `W-1501-runtime-hit-miss-traces`

**Route:** runtime validation worker through `tmux-swarm-orchestration`

**Reserved files:** none

**Purpose:** Produce fresh local Langfuse Telegram traces proving #1501 runtime behavior.

**Prerequisite:** The operator has explicitly confirmed non-production Telegram bot credentials and a safe Telethon/session setup are available. If not confirmed, the worker must return `BLOCKED`.

**Expected output:** DONE or BLOCKED artifact with redacted trace evidence.

### Worker Wave 3: Broad Suite Instability Follow-Up

**Worker name:** `W-test-unit-xdist-followup`

**Route:** quick issue-management or bug investigation worker through `tmux-swarm-orchestration`

**Reserved files:** none for issue creation; reserve test files only if a separate bugfix issue is approved.

**Purpose:** Create a separate GitHub issue for broad `make test-unit` instability so #1501 stays scoped to BGE/pre-agent changes.

**Expected output:** A linked issue number and comment back on #1501.

---

### Task 1: Record The Closeout Plan On #1501

**Files:**
- Create: `docs/superpowers/plans/2026-05-13-issue-1501-closeout-runtime-validation.md`
- GitHub: comment on `#1501`

- [ ] **Step 1: Verify #1501 state**

Run:

```bash
gh issue view 1501 --json number,title,state,labels,url --jq '{number,title,state,url,labels:[.labels[].name]}'
```

Expected: issue `1501` is open and has `domain:observability`, `domain:retrieval`, `domain:bot`, and `performance` labels.

- [ ] **Step 2: Add plan link comment**

Run:

```bash
gh issue comment 1501 --body-file /tmp/issue-1501-closeout-plan-comment.md
```

Use this body:

```markdown
## Closeout / validation plan

Code for #1501 is merged via #1503, #1505, and #1506. The next step is tracked in the local plan:

`docs/superpowers/plans/2026-05-13-issue-1501-closeout-runtime-validation.md`

Planned execution route: `$tmux-swarm-orchestration`.

Scope split:
- #1501 code-complete evidence: focused tests on `origin/dev@ee015d07`.
- Runtime evidence lane: fresh non-production Telegram HIT/MISS Langfuse traces.
- Separate follow-up: broad `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit` instability, because it has not reproduced as a #1501 touched-surface regression.
```

- [ ] **Step 3: Verify the comment exists**

Run:

```bash
gh issue view 1501 --json comments --jq '.comments[-1].body'
```

Expected: output contains `Closeout / validation plan` and the plan path.

### Task 2: Create Runtime Validation Follow-Up If Needed

**Files:**
- GitHub: create issue only if #1501 will be closed without runtime traces, or if runtime credentials are not immediately available.

- [ ] **Step 1: Decide whether runtime credentials are available**

Check only presence, not values:

```bash
test -f .env && {
  grep -q '^TELEGRAM_BOT_TOKEN=' .env && echo TELEGRAM_BOT_TOKEN_PRESENT || true
  grep -q '^TELEGRAM_API_ID=' .env && echo TELEGRAM_API_ID_PRESENT || true
  grep -q '^TELEGRAM_API_HASH=' .env && echo TELEGRAM_API_HASH_PRESENT || true
  grep -q '^E2E_BOT_USERNAME=' .env && echo E2E_BOT_USERNAME_PRESENT || true
}
```

Expected: presence-only output. Do not print values.

- [ ] **Step 2: If credentials are real/prod or unavailable, create a validation follow-up**

Run:

```bash
RUNTIME_ISSUE_URL=$(gh issue create \
  --title "validation: capture fresh Telegram HIT/MISS Langfuse traces for #1501" \
  --label "domain:observability" \
  --label "domain:bot" \
  --label "performance" \
  --label "testing" \
  --body-file /tmp/issue-1501-runtime-validation-followup.md)
RUNTIME_ISSUE_NUMBER="${RUNTIME_ISSUE_URL##*/}"
printf 'Runtime validation issue: #%s\n' "$RUNTIME_ISSUE_NUMBER"
```

Use this body:

```markdown
## Goal

Collect fresh non-production Telegram Langfuse traces for #1501 after #1503, #1505, and #1506 merged into `dev`.

## Parent

Parent: #1501

## Required evidence

- One semantic cache MISS Telegram trace.
- One repeated-query semantic cache HIT Telegram trace.
- HIT trace must not emit pre-agent `bge-m3-hybrid-colbert-embed` before returning.
- MISS trace must preserve retrieval behavior and reach the expected RAG/Qdrant path.
- Trace metadata/scores should show:
  - `pre_agent_cache_check_ms`
  - `pre_agent_embed_ms` when dense is computed
  - `bge_model_processing_ms` when BGE service processing time is available
- BGE wrapper spans must not capture full dense/sparse/ColBERT vector payloads.

## Safety

Use only local/non-production Telegram bot credentials, local Langfuse, and local Docker services. Do not use production credentials, VPS, CRM write paths, SSH, or cloud credentials.

## Suggested route

Execute through `$tmux-swarm-orchestration` with one runtime validation worker. Runtime workers count as 2 slots.

## Suggested commands

```bash
make local-up
make docker-ml-up
make test-bot-health
make bot
make e2e-test-traces-core
```

If `make e2e-test-traces-core` is too broad for the current credentials, send one safe query twice through the non-production bot and inspect local Langfuse manually.
```

- [ ] **Step 3: Link the follow-up back to #1501**

Run:

```bash
test -n "$RUNTIME_ISSUE_NUMBER"
gh issue comment 1501 --body "Runtime HIT/MISS trace validation split into follow-up: #${RUNTIME_ISSUE_NUMBER}."
```

Expected: #1501 links to the new validation issue.

### Task 3: Create Broad Suite Instability Follow-Up

**Files:**
- GitHub: create one issue for unrelated broad unit-suite instability.

- [ ] **Step 1: Create the issue**

Run:

```bash
XDIST_ISSUE_URL=$(gh issue create \
  --title "test: investigate xdist/pytest-timeout instability in make test-unit" \
  --label "testing" \
  --label "tech-debt" \
  --body-file /tmp/issue-test-unit-xdist-instability.md)
XDIST_ISSUE_NUMBER="${XDIST_ISSUE_URL##*/}"
printf 'xdist instability issue: #%s\n' "$XDIST_ISSUE_NUMBER"
```

Use this body:

```markdown
## Problem

During #1501 final validation, broad local unit runs with:

```bash
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

did not produce a stable pass. The observed failures were not in #1501 touched surfaces.

## Evidence

- First run reported xdist/pytest-timeout internal error around `tests/unit/ingestion/test_unified_manifest.py::TestGDriveManifest::test_different_content_different_id`.
- The exact test later passed standalone.
- The full `tests/unit/ingestion/test_unified_manifest.py` module later passed under xdist.
- A second broad run failed elsewhere, including `tests/unit/test_query_preprocessor_unit.py::TestGetRRFWeights::test_rrf_weights[floor]`, again through local xdist/timeout behavior.
- A later audit worker saw a deterministic-looking failure in `tests/unit/test_validate_trace_runtime.py::test_guard_blocks_ci_fallback_with_existing_postgres_volume`, expected `exit_code == 2`, actual `0`.

## Scope

Investigate broad local test scheduler/runtime instability separately from #1501. Do not block #1501 unless a failure reproduces in the focused #1501 checks.

## Suggested validation

```bash
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
uv run pytest tests/unit/test_validate_trace_runtime.py::test_guard_blocks_ci_fallback_with_existing_postgres_volume -q
uv run pytest tests/unit/ingestion/test_unified_manifest.py -n auto --dist=worksteal -q
```
```

- [ ] **Step 2: Link it back to #1501**

Run:

```bash
test -n "$XDIST_ISSUE_NUMBER"
gh issue comment 1501 --body "Broad local unit-suite instability split into follow-up: #${XDIST_ISSUE_NUMBER}. Not treated as a #1501 blocker unless it reproduces in #1501 focused checks."
```

Expected: #1501 now has a clear separation between code-complete evidence and unrelated broad-suite instability.

### Task 4: Run Non-Production Runtime HIT/MISS Validation

**Files:**
- No planned file changes.
- Runtime evidence only.

- [ ] **Step 1: Confirm safe credentials**

Before running the bot, confirm with the operator that the credentials are non-production.

Expected answer: explicit confirmation that the Telegram bot token, Telethon session, and Langfuse target are local/test-only.

- [ ] **Step 2: Start local runtime services**

Run:

```bash
make local-up
make docker-ml-up
make test-bot-health
```

Expected:
- Redis reachable with configured auth.
- Qdrant collection exists.
- LiteLLM readiness is OK.
- BGE service health is OK.

- [ ] **Step 3: Start the native bot in a dedicated tmux worker window**

Run in the runtime worker window:

```bash
make bot
```

Expected: bot starts and keeps running without polling-lock conflict.

- [ ] **Step 4: Send a MISS query**

Use one safe non-sensitive RAG query through the non-production Telegram bot.

Preferred repo command for a fixed safe text query:

```bash
uv run python -m scripts.e2e.quick_test
```

Expected:
- Telegram returns an answer.
- Local Langfuse gets a recent `telegram-message` trace.

- [ ] **Step 5: Send the same query again for HIT**

Send the same query a second time after the first answer is cached.

Preferred repo command:

```bash
uv run python -m scripts.e2e.quick_test
```

Expected:
- Telegram returns a cached/reused answer.
- Local Langfuse gets a second recent `telegram-message` trace.

- [ ] **Step 6: Inspect Langfuse traces without printing secrets**

Use the local Langfuse CLI or validator commands available in the repo. Prefer trace IDs, span names, score names, and timings only.

Example:

```bash
LANGFUSE_HOST="${LANGFUSE_HOST:-http://localhost:3001}" lf --host "$LANGFUSE_HOST" traces list --name telegram-message --limit 5
```

Expected HIT evidence:
- `cache-check` or equivalent semantic cache span reports HIT.
- No pre-agent `bge-m3-hybrid-colbert-embed` span before return.
- No full vector payload capture in BGE wrapper spans.

Expected MISS evidence:
- `cache-check` reports MISS.
- Retrieval path still reaches expected RAG/Qdrant spans.
- `bge_model_processing_ms` is present when dense helper computed the query vector.

- [ ] **Step 7: Write redacted evidence comment**

Run:

```bash
gh issue comment 1501 --body-file /tmp/issue-1501-runtime-evidence.md
```

Use this structure:

```markdown
## Runtime validation evidence

Local/non-production runtime only.

MISS trace:
- trace id: `<TRACE_ID>`
- root family: `telegram-message`
- cache decision: MISS
- retrieval path: `<observed qdrant/rag span names>`
- `bge_model_processing_ms`: `<value or not emitted because dense was cached>`
- vector capture: no full vector payload observed

HIT trace:
- trace id: `<TRACE_ID>`
- root family: `telegram-message`
- cache decision: HIT
- pre-agent hybrid/ColBERT before return: not observed
- vector capture: no full vector payload observed

Commands:
- `make local-up`
- `make docker-ml-up`
- `make test-bot-health`
- `<trace inspection command, redacted>`
```

### Task 5: Final #1501 Disposition

**Files:**
- GitHub: close or keep #1501 open depending on runtime status.

- [ ] **Step 1: If runtime evidence exists, close #1501**

Run:

```bash
gh issue close 1501 --comment "Implemented in #1503, #1505, and #1506. Focused checks passed on origin/dev@ee015d07, runtime HIT/MISS Langfuse evidence attached above. Broad xdist instability is tracked separately."
```

Expected: #1501 state is `CLOSED`.

- [ ] **Step 2: If runtime evidence is blocked, leave #1501 open or mark validation pending**

If non-production credentials are unavailable and the maintainer requires runtime evidence before closure, run:

```bash
test -n "$RUNTIME_ISSUE_NUMBER"
gh issue edit 1501 --add-label "blocked"
gh issue comment 1501 --body "Code is complete and focused checks pass, but fresh runtime HIT/MISS traces are blocked pending non-production Telegram credentials. Runtime validation is tracked in #${RUNTIME_ISSUE_NUMBER}."
```

Expected: #1501 remains open with a concrete blocker.

- [ ] **Step 3: If maintainer accepts code-complete closure without runtime evidence, close with explicit caveat**

Run:

```bash
test -n "$RUNTIME_ISSUE_NUMBER"
gh issue close 1501 --comment "Implemented in #1503, #1505, and #1506. Focused checks passed on origin/dev@ee015d07. Fresh Telegram HIT/MISS runtime traces require non-production credentials and are tracked separately in #${RUNTIME_ISSUE_NUMBER}."
```

Expected: #1501 state is `CLOSED`, and runtime validation remains visible in the linked follow-up.

## Verification Checklist

- [ ] #1501 has a comment linking this plan.
- [ ] #1501 has the focused verification evidence summarized.
- [ ] Runtime validation is either attached to #1501 or split into a linked follow-up.
- [ ] Broad `make test-unit` instability is split into a linked follow-up.
- [ ] No secrets, token values, chat IDs, Telethon session data, CRM data, or raw Telegram payloads are included in comments or worker artifacts.
- [ ] No source files are modified from this closeout plan unless a new implementation issue is created.
