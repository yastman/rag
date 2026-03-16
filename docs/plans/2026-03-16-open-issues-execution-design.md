# Open Issues Execution Design

Date: 2026-03-16
Branch: `dev`
Scope: open GitHub issues excluding VPS/ops items `#837`, `#836`, `#841`-`#852` and excluding service issue `#11`

## Purpose

This document defines the execution design for the remaining non-VPS open issues so the backlog can be completed in a controlled order instead of as unrelated ticket work.

The goal is to:

- prepare `dev` for safe merge into `main`
- reduce regression risk in RAG and agent runtime paths
- finish the partially completed SDK realignment work
- deliver product/runtime improvements only after the repo is stable enough to absorb them

## Recommended Execution Model

Three sequencing models were considered:

1. `pre-main first`
2. `product first`
3. `dependency-balanced`

Recommended model: `dependency-balanced`

Reason:

- `pre-main` blockers must be resolved before broader product work
- test and typing gaps make retrieval/runtime changes too expensive and risky
- `#728` already has a merged PR and now needs controlled closure, not another broad migration branch
- product improvements should land only after the runtime safety net is stronger

## In-Scope Issues

Release readiness:

- `#978` Pre-PR / pre-main audit for `dev` before merge to `main`
- `#981` Follow-up: clear residual bandit/vulture findings after pre-main audit

Quality foundation:

- `#855` Missing unit tests for critical RAG nodes: grade, rerank, rewrite
- `#857` Missing coverage for search engines, manager tools, CRM cards, ingestion
- `#858` Mypy silences in core modules

Runtime consolidation:

- `#728` SDK Migration Audit: Custom Code -> SDK Solutions

Product/runtime improvements:

- `#952` Add response streaming to agent (`sdk_agent`) path
- `#956` Multi-layer retrieval quality
- `#901` Index `services.yaml` content into Qdrant for RAG search

Out of scope:

- `#837`, `#836`, `#841`-`#852` as VPS/ops
- `#11` dependency dashboard

## Workstream Design

### Workstream A: Release Readiness

Issues:

- `#978`
- `#981`

Outcome:

- one current source of truth for merge readiness
- explicit blocking vs non-blocking findings
- residual low-severity findings either fixed or converted into narrow follow-up decisions

Primary inputs:

- `docs/plans/2026-03-16-pre-pr-pre-main-audit-report.md`
- current `dev` baseline

Rules:

- do not reopen broad audit scope
- do not mix VPS/infra findings into this stream
- every unresolved finding must end as either accepted residual debt or a separately bounded issue

Acceptance:

- fresh validation rerun on current `dev`
- `#978` updated with final merge recommendation
- `#981` either closed or reduced to a much smaller residual cleanup task

### Workstream B: Quality Foundation

Issues:

- `#855`
- `#857`
- `#858`

Outcome:

- runtime-critical RAG logic has direct coverage
- retrieval and manager-facing surfaces have enough regression protection
- type contracts become trustworthy enough for bounded refactors

Execution order inside the stream:

1. RAG node tests for `grade`, `rerank`, `rewrite`
2. retrieval/search engine coverage
3. manager tools, CRM cards, ingestion coverage
4. mypy silence removal with bounded refactors only where necessary

Rules:

- prioritize runtime-critical paths over broad coverage percentages
- avoid hiding behavior changes inside typing cleanup
- if a typing fix requires architecture movement, split it into a bounded refactor note

Acceptance:

- targeted suites added for all issue areas
- affected general test suites rerun successfully
- `mypy` suppression scope reduced with explicit before/after evidence

### Workstream C: Runtime Consolidation

Issue:

- `#728`

Outcome:

- SDK realignment is treated as completed or intentionally narrowed
- docs, issue state, and remaining follow-ups are synchronized

Current context:

- PR `#972` is merged into `dev`
- `#728` remains open even though the PR body says `Closes #728`
- the likely reason is merge into `dev` rather than the default branch

Required actions:

- confirm what was completed by PR `#972`
- reconcile canonical docs and issue body/comments
- close `#728` manually if appropriate, with explicit links to remaining follow-up issues

Rules:

- no new big-bang SDK migration work
- preserve keeper stack defined in `docs/plans/2026-03-15-sdk-canonical-remediation-plan.md`
- keep SDK-first checks grounded in `.claude/rules/sdk-registry.md`

Acceptance:

- no ambiguity remains about whether `#728` is active work or historical umbrella context
- issue state matches actual repository state

### Workstream D: Product/Runtime Improvements

Issues:

- `#952`
- `#956`
- `#901`

Outcome:

- streaming UX path is stable
- retrieval quality work lands on top of a safer test base
- `services.yaml` becomes a deliberate knowledge source rather than an ad hoc corpus extension

Execution order:

1. `#952` streaming
2. `#956` retrieval quality
3. `#901` `services.yaml` indexing

Reason:

- streaming changes the answer delivery path and observability surfaces
- retrieval quality changes should ride on better tests
- indexing `services.yaml` should happen only after retrieval semantics are stable enough to absorb a new source

Acceptance:

- each feature has explicit runtime validation and issue update
- new knowledge or retrieval behavior preserves service boundaries and existing observability hooks

## Delivery Units

Issues should not be implemented one-by-one without grouping. The delivery shape should be:

### Unit 1: Merge Readiness

Covers:

- `#978`
- as much of `#981` as is directly tied to merge readiness

Deliverables:

- rerun of audit validation
- final blocker/non-blocker decision log
- issue updates and merge recommendation

### Unit 2: RAG Safety Net

Covers:

- `#855`
- retrieval-heavy parts of `#857`

Deliverables:

- tests for grade/rerank/rewrite
- retrieval and path-level regression coverage

### Unit 3: Type Contract Cleanup

Covers:

- `#858`
- remaining quality items from `#857` that depend on type clarity

Deliverables:

- reduced `mypy` silences
- documented contract cleanups where type debt hid real coupling

### Unit 4: SDK Closure

Covers:

- `#728`

Deliverables:

- reconciled documentation
- explicit issue closure path
- follow-up split for anything still genuinely open

### Unit 5: Runtime/Product Lane

Covers:

- `#952`
- `#956`
- `#901`

Deliverables:

- runtime improvements in controlled sequence
- targeted verification per feature

## Validation Model

Each delivery unit must complete the same control loop:

1. confirm baseline on fresh `dev`
2. make scoped changes only for the current unit
3. run targeted verification first
4. run broader regression checks relevant to changed surfaces
5. update issue state and record what remains out of scope

Minimum verification expectations:

- release readiness: fresh rerun of the current audit verification set
- quality foundation: targeted unit/integration suites plus relevant broader regression sweep
- runtime/product: tests plus observability and fallback-path verification

When relevant, base checks remain:

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

If these are skipped or known-red on baseline, the result must explicitly say so and show why the change is still safe.

## Risk Controls

- Do not mix VPS/ops work into non-VPS runtime PRs.
- Do not mix typing cleanup with retrieval behavior changes unless technically required.
- Preserve service boundaries: Telegram transport code must not absorb retrieval or domain logic.
- Preserve LangGraph state contracts and text-path/runtime separation.
- Preserve tracing, scoring, and source-formatting surfaces during streaming and retrieval work.
- Treat SDK registry and canonical SDK plan as constraints, not optional references.

## Issue Hygiene Rules

- Every delivery unit must leave a GitHub issue comment with: what changed, what was verified, and what remains.
- If an issue is effectively done but not auto-closed, close it manually with rationale.
- Do not hide backlog residue inside old umbrella issues.
- Convert leftovers into smaller follow-up issues with narrow, testable scope.

## Final Recommendation

Execute the non-VPS backlog in this order:

1. Workstream A: `#978`, `#981`
2. Workstream B: `#855`, `#857`, `#858`
3. Workstream C: `#728`
4. Workstream D: `#952`, `#956`, `#901`

This sequence best balances merge readiness, regression control, and product progress.
