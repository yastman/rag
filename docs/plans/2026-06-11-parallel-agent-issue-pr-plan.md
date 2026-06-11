# Parallel Agent Issue + PR Execution Plan

Date: 2026-06-11
Branch: `coordination/parallel-agent-plan-20260611`
Repository: `yastman/rag`
Base checked: `dev` at `13b1a53af6f7240ccea713128f23c9a45936b96e`
Scope: distribute open issues and open PRs across parallel agents.
Runtime code changes in this branch: none.

---

## 1. Goal

Speed up development by running multiple agents in parallel without merge conflicts, duplicate work, or unsafe deletions.

This plan separates two queues:

```text
Queue A: PR Review / Merge Queue
Queue B: Issue Execution Queue
```

Rule:

```text
No execution agent should touch files already owned by an open PR unless assigned to review/rebase that PR.
```

---

## 2. Current open PR queue

| PR | Title | Status | Plan |
|---:|---|---|---|
| #2472 | `docs: add open issues execution roadmap` | mergeable, docs-only, but likely superseded by newer audit files | PR-review agent should compare with newer audit docs. Either merge as historical roadmap or close/supersede. Do not let execution agents depend on it. |
| #2473 | `fix: resolve MyPy errors in adapters and generation service` | mergeable=true, but PR body shows a failing unit test and MyPy still reports errors | PR-review agent should re-review carefully. Do not merge until test failure / claims are reconciled. May overlap with #2474. |
| #2453 | `refactor(deps): make heavy observability deps optional` | mergeable=false, closes #2431, 5 files changed | PR-review agent should rebase/resolve conflicts or mark blocked. Do not start new dependency-diet PRs against the same files until this is resolved. |

---

## 3. Merge / integration order

Recommended order:

```text
1. Decide PR #2472 fate: merge as historical docs or close as superseded.
2. Resolve/rebase/review PR #2473 before MyPy-related issue work.
3. Resolve/rebase/review PR #2453 before dependency diet / observability optionalization work.
4. Start new P0 execution branches only after PR ownership is clear.
```

Do not merge code PRs after stale docs if docs will mislead new agents. If #2472 contradicts newer audits, update or close it.

---

## 4. Parallel agent roster

Use short-lived branches per agent. Each agent gets one lane and should not drift outside allowed files.

### Agent 0 — PR Review / Merge Coordinator

Purpose:

```text
Review open PRs, decide merge/rebase/close, prevent duplicate execution work.
```

Assigned PRs:

```text
#2472
#2473
#2453
```

Allowed work:

```text
- inspect PR diffs
- check whether PR is superseded by newer docs/audits
- add PR review comments
- rebase only if explicitly assigned
- update PR body with current status
```

Forbidden:

```text
- do not create new architecture changes
- do not merge without human confirmation
- do not edit runtime code unless specifically fixing that PR
```

Output:

```text
PR triage report:
- merge now
- rebase needed
- close/superseded
- blocked by issue
```

---

### Agent 1 — Docs Truth / ADR Alignment

Purpose:

```text
Make docs stop contradicting ADR-0019 before agents execute code.
```

Assigned issues:

```text
#2479
part of #2411
```

Allowed files:

```text
docs/designs/monolith-core-plan.md
docs/designs/README.md
docs/adr/README.md if needed
```

Forbidden files:

```text
src/
telegram_bot/
pyproject.toml
compose.yml
```

Definition of done:

```text
- monolith-core-plan.md says core text path is procedural per ADR-0019
- no unresolved create_agent-vs-procedural blocker remains
- create_agent is described only as adapter/conversational shell, not product core owner
```

Branch suggestion:

```text
docs/adr-0019-monolith-plan-sync
```

Can run in parallel with:

```text
Agent 0 only
```

Blocks:

```text
Agent 2, Agent 3, Agent 4 should read the fixed docs before coding.
```

---

### Agent 2 — Generation Ownership / Circular Dependency

Purpose:

```text
Break the most dangerous runtime ownership cycle.
```

Assigned issues:

```text
#2486
first slice of #2478
```

Allowed files:

```text
src/runtime/pipeline/assistant_pipeline.py
src/runtime/generation/service.py
src/runtime/generation/contracts.py
tests/unit/runtime/test_assistant_pipeline.py
tests/data/known_runtime_telegram_bot_couplings.json
```

Forbidden files:

```text
telegram_bot/services/generate_response.py except tiny compatibility adjustments
pyproject.toml
compose.yml
src/runtime/pipeline/rag.py
src/runtime/services/query_preprocessor.py
```

Definition of done:

```text
- assistant_pipeline.py no longer dynamically imports telegram_bot.services.generate_response
- generation non-streaming path uses runtime generation seam directly
- test_assistant_pipeline updated to avoid monkeypatching Telegram module
- allowlist entry for assistant_pipeline.py removed if applicable
```

Branch suggestion:

```text
core/remove-telegram-generation-from-assistant-pipeline
```

Can run in parallel with:

```text
Agent 1
Agent 5 planning only
Agent 6 planning only
```

Must not run in parallel with:

```text
Agent 3 if both touch generation/service.py
Agent 8 if it deletes generation functions
```

---

### Agent 3 — Prompt / Style / Generation Policy Ownership

Purpose:

```text
Move product generation policy out of Telegram-owned modules.
```

Assigned issues:

```text
#2489
second slice of #2478
```

Allowed files:

```text
telegram_bot/integrations/prompt_manager.py
telegram_bot/integrations/prompt_templates.py
telegram_bot/services/response_style_detector.py
telegram_bot/services/coverage_mode.py
telegram_bot/services/metrics.py
src/runtime/integrations/prompt_manager.py or src/runtime/services/prompt_manager.py
src/runtime/integrations/prompt_templates.py or src/runtime/services/prompt_templates.py
src/runtime/services/response_style_detector.py
src/runtime/services/coverage_mode.py
src/runtime/services/metrics.py
src/runtime/generation/service.py
tests/data/known_runtime_telegram_bot_couplings.json
```

Forbidden files:

```text
src/runtime/pipeline/rag.py
src/runtime/pipeline/assistant_pipeline.py unless Agent 2 already merged
pyproject.toml
compose.yml
```

Definition of done:

```text
- runtime generation imports runtime-owned prompt/style/coverage modules, not telegram_bot.*
- telegram_bot keeps re-export shims only
- corresponding coupling entries removed from allowlist
- behavior and prompts unchanged
```

Branch suggestion:

```text
runtime/move-generation-policy-from-telegram
```

Can run in parallel with:

```text
Agent 4 after contracts are clear
Agent 5 if not touching generation
```

Must coordinate with:

```text
Agent 2
Agent 8
```

---

### Agent 4 — Core Dependencies / AssistantApp Builder

Purpose:

```text
Make the core dependency seam typed and ready for adapter reuse.
```

Assigned issues:

```text
#2480
#2404
```

Allowed files:

```text
src/core/contracts.py
src/core/dependencies.py
src/core/assistant.py
tests/unit/core/
tests/contract/
```

Forbidden files:

```text
telegram_bot/bot.py
src/runtime/pipeline/rag.py
src/runtime/generation/service.py unless Protocols require import-only typing
pyproject.toml
compose.yml
```

Definition of done:

```text
- CoreDependencies fields use Protocols or typed minimal interfaces
- optional crm field exists explicitly if needed
- no vendor-specific protocols leak into core
- existing core tests pass or are updated
```

Branch suggestion:

```text
core/type-core-dependencies
```

Can run in parallel with:

```text
Agent 1
Agent 5
Agent 6 planning
```

Should wait for:

```text
Agent 2 if the generation seam shape is changing heavily
```

---

### Agent 5 — API + Minimal Core Runtime Surface

Purpose:

```text
Make optional API/runtime surfaces call the core instead of owning separate graph paths.
```

Assigned issues:

```text
#2483
#2485
```

Allowed files:

```text
src/api/main.py
src/api/schemas.py
compose.core.yml or compose.dev.yml if adding minimal profile
docs/LOCAL-DEVELOPMENT.md
DOCKER.md
tests/unit/api/
tests/contract/compose or api contracts
```

Forbidden files:

```text
src/runtime/generation/service.py
src/runtime/pipeline/rag.py
telegram_bot/services/generate_response.py
pyproject.toml unless only docs mention extras
```

Definition of done:

```text
- API path can call src.core.run_assistant_request or has a documented migration shim
- minimal core compose path exists or is clearly proposed
- Mini App / voice / Langfuse remain optional
```

Branch suggestion:

```text
api/adapter-over-core
```

Can run in parallel with:

```text
Agent 2 if it does not depend on new CoreDependencies shape
Agent 6
```

Should coordinate with:

```text
Agent 4 for dependency builder
Agent 0 if PR #2453 changes dependency/compose assumptions
```

---

### Agent 6 — LLM + Dependency Hygiene

Purpose:

```text
Choose one canonical LLM path and prepare dependency cleanup without fighting open PRs.
```

Assigned issues:

```text
#2481
#2454
#2429
#2451
```

Allowed files:

```text
src/runtime/llm/router.py
src/adapters/llm/litellm_provider.py
src/adapters/llm/factory.py
docs/engineering/litellm-sdk-router.md
docs/runbooks/LITEllm_FAILURE.md
scripts/benchmark_llm.py
k8s/base/configmaps/litellm-config.yaml only if cleanup is explicitly approved
```

Forbidden files:

```text
pyproject.toml until PR #2453 is resolved
uv.lock until dependency removal is explicitly assigned
src/runtime/generation/service.py unless only switching LLM provider call site
```

Definition of done:

```text
- canonical LLM path declared: prefer src/runtime/llm/router.py
- litellm_provider either wraps router or issue updated with migration plan
- stale Docker/proxy docs/env/k8s references identified
- no dependency deletion before PR #2453 status is resolved
```

Branch suggestion:

```text
llm/consolidate-router-path
```

Can run in parallel with:

```text
Agent 1
Agent 4
Agent 5
```

Must coordinate with:

```text
Agent 0 on PR #2453
```

---

### Agent 7 — Retrieval + Embeddings Deduplication

Purpose:

```text
Clarify boundaries for retrieval and embeddings without changing algorithms prematurely.
```

Assigned issues:

```text
#2476
#2475
```

Allowed files:

```text
src/retrieval/search_engines.py
src/runtime/services/qdrant.py
src/runtime/retrieval/ if created
src/adapters/embeddings/
src/services/bge_m3_client.py
src/runtime/integrations/embeddings.py
tests/unit/retrieval/
tests/unit/services/test_rag_core.py
tests/unit/test_bge_m3_endpoints.py
```

Forbidden files:

```text
src/runtime/pipeline/rag.py unless Agent 2/3 work is merged
src/runtime/generation/service.py
pyproject.toml
compose.yml
```

Definition of done:

```text
- QdrantService declared canonical runtime Qdrant SDK gateway
- search_engines.py marked benchmark/eval/strategy-only or moved under runtime/retrieval
- BGEM3Client remains low-level HTTP client
- adapters/embeddings declared provider layer
- runtime/integrations/embeddings reduced to wrapper/shim or migration plan created
```

Branch suggestion:

```text
runtime/clarify-retrieval-embedding-boundaries
```

Can run in parallel with:

```text
Agent 1
Agent 6
```

Should wait for:

```text
Agent 2/3 before touching rag.py
```

---

### Agent 8 — Dead Code / Complexity Cleanup

Purpose:

```text
Verify dead-code candidates and refactor complexity only after ownership seams are stable.
```

Assigned issues:

```text
#2488
#2492
#2487
```

Allowed files for first pass:

```text
docs/audits/*
issue comments only
maybe tests proving false positives
```

Forbidden files until #2486/#2489 are resolved:

```text
src/runtime/generation/service.py
src/runtime/generation/policy.py
telegram_bot/services/generate_response.py
telegram_bot/bot.py
src/runtime/pipeline/rag.py
```

Definition of done for first pass:

```text
- #2492 false positives removed/re-scoped
- #2488 becomes umbrella verification issue, not delete list
- no deletion of nested callbacks, dataclass lifecycle, public client methods, or used fallback/history helpers
```

Branch suggestion:

```text
cleanup/verify-dead-code-candidates
```

Can run in parallel with:

```text
Agent 1
Agent 0
```

Must wait for code deletion until:

```text
Agent 2 and Agent 3 are merged
```

---

### Agent 9 — Observability / Optional Surfaces

Purpose:

```text
Keep observability optional and avoid deleting useful graceful-degradation tests.
```

Assigned issues:

```text
#2452
#2431
#2490
#2491
#2430
```

Allowed files:

```text
docs/runbooks/observability docs
tests/contract/test_langfuse_optional_core_contract.py
tests/contract/test_obsolete_observability_assets_removed_contract.py
src/observability.py only after #2490 repro is confirmed
pyproject.toml only after PR #2453 resolved
mini_app docs only unless #2430 is explicitly approved
```

Forbidden files:

```text
runtime generation/retrieval core
major dependency deletion while #2453 is open
Mini App deletion without archive decision
```

Definition of done:

```text
- #2490 either gets exact line-level repro or is re-scoped/closed
- #2491 either gets exact line-level repro or is re-scoped/closed
- #2452 is re-scoped from deletion to optionalization/stale asset cleanup
- #2431 work coordinates with PR #2453
```

Branch suggestion:

```text
observability/rescope-optionalization-cleanup
```

Can run in parallel with:

```text
Agent 1
Agent 8 docs-only pass
```

Must coordinate with:

```text
Agent 0 on PR #2453
```

---

## 5. Work that should NOT be parallelized yet

Do not run these as independent code agents now:

```text
#2426 remove create_agent from voice
#2427 remove StateGraph/middleware shims
#2428 drop LangChain/LangGraph deps
#2482 split GraphConfig
#2300 Python/Node migration
#2437 external offline traces/eval proposal
```

Reason:

```text
They are downstream of core ownership cleanup or optional-surface decisions.
Starting them now will create churn and conflicts.
```

---

## 6. File conflict map

High-conflict files:

```text
src/runtime/generation/service.py      -> Agent 2 / Agent 3 only
telegram_bot/services/generate_response.py -> Agent 2 / Agent 3 only
src/runtime/pipeline/rag.py            -> Agent 3 later / Agent 7 later
src/runtime/graph/config.py            -> Agent 4 / Agent 5 / later Agent 10, coordinate
pyproject.toml                         -> Agent 0 / Agent 6 / Agent 9 only after #2453
compose.yml                            -> Agent 5 only after PR review
telegram_bot/bot.py                    -> avoid until Agent 8 complexity pass later
```

Low-conflict files:

```text
docs/designs/monolith-core-plan.md     -> Agent 1
src/adapters/llm/*                     -> Agent 6
src/adapters/embeddings/*              -> Agent 7
src/services/bge_m3_client.py          -> Agent 7
src/api/*                              -> Agent 5
tests/contract/*                       -> depends on lane
```

---

## 7. Recommended branch naming

```text
review/pr-2473-mypy-status
review/pr-2453-optional-deps-rebase
docs/adr-0019-monolith-plan-sync
core/remove-telegram-generation-from-assistant-pipeline
runtime/move-generation-policy-from-telegram
core/type-core-dependencies
api/adapter-over-core
llm/consolidate-router-path
runtime/clarify-retrieval-embedding-boundaries
cleanup/verify-dead-code-candidates
observability/rescope-optionalization-cleanup
```

---

## 8. Agent prompt template

Use this template for every execution agent:

```text
You are working in yastman/rag.
Read docs/plans/2026-06-11-parallel-agent-issue-pr-plan.md first.
Work only on your assigned lane.
Do not touch forbidden files.
Do not merge.
Do not close issues.
Create a focused branch.
Make the smallest useful PR.
Update tests for the touched seam only.
In the PR body, include:
- assigned issue(s)
- allowed files touched
- validation run
- conflicts/blockers
- next follow-up issue if scope remains
```

---

## 9. Suggested parallel launch batch

Safe first batch:

```text
Agent 0: review #2472/#2473/#2453
Agent 1: fix #2479 docs truth
Agent 2: fix #2486 first slice of #2478
Agent 6: plan/patch #2481 LLM router consolidation, avoiding pyproject
Agent 8: re-scope #2492/#2488 docs/comments only, no code deletion
Agent 9: re-scope #2490/#2491/#2452, no code deletion
```

Do not start yet:

```text
Agent 3 until Agent 2 branch is clear or merged
Agent 5 until Agent 4/Agent 0 clarify dependency builder / PR #2453
Agent 7 can plan, but should not touch rag.py until Agent 2/3 settle generation ownership
```

---

## 10. Final recommendation

Run parallelism by lane, not by issue number.

The fastest safe route is:

```text
1. PR review lane clears existing PRs.
2. Docs truth lane removes contradictory instructions.
3. Generation ownership lane removes the biggest circular dependency.
4. Other lanes work only on non-overlapping boundaries.
```

Primary KPI:

```text
known_runtime_telegram_bot_couplings.json shrinks every core PR.
```

Secondary KPI:

```text
Open PR count stays small: no more than 5 active code PRs at once.
```
