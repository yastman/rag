# Issue Triage Workflow Design

## Context

This repository mixes production runtime surfaces, retrieval behavior, bot UX, ingestion pipelines, and infrastructure code. The open issue backlog contains both very small local fixes and large cross-system changes. We need a repeatable way to choose the next issue and decide whether to execute it directly or route it through a design and plan workflow.

## Problem

Without a stable triage policy, the session can drift in two bad directions:

- small safe fixes get over-processed and slow down delivery;
- larger runtime or architectural changes get under-scoped and create regressions.

We also want the selection process to be explicitly SDK-first, DRY-aware, and biased toward existing project patterns rather than ad hoc code.

## Goals

- Classify each issue before starting implementation.
- Use existing SDK and framework capabilities before inventing custom code.
- Avoid introducing duplicate logic or unstable abstractions.
- Reserve heavyweight planning for issues with real cross-system risk.
- Keep the workflow simple enough to run at the start of each session.

## Non-Goals

- This design does not define the implementation of any specific issue.
- This design does not replace repo-wide validation rules from `AGENTS.md`.
- This design does not require a full spec for every typo, rename, or isolated fix.

## Core Decision Model

Each issue is classified on four axes:

1. `Scope`: how many modules or subsystems are likely to change.
2. `Risk`: whether the issue touches runtime, deployment, retrieval, graph state, ingestion determinism, or other critical invariants.
3. `SDK coverage`: whether the problem is already solvable through an existing SDK or framework feature used by the repository.
4. `Reuse pressure`: whether the change should stay local or whether a shared abstraction is clearly stable and worth extracting now.

These axes determine one of three execution lanes:

- `Quick execution`
- `Plan needed`
- `Design first`

## Research Order

Before choosing an execution lane, use this lookup order:

1. Read `docs/engineering/sdk-registry.md`.
2. Check current project usage in the codebase.
3. Use Context7 for official and version-sensitive SDK or framework behavior.
4. Use broad web search only if the previous three steps do not answer the question.

This means small issues can still include documentation research, but the research is scoped and SDK-first.

## Execution Lanes

### 1. Quick Execution

Choose this lane when all of the following are true:

- the issue is local to one narrow module or a very small set of related files;
- the contract is already established in the repository;
- the implementation can follow an existing pattern or a straightforward SDK usage path;
- verification is narrow and concrete;
- the change does not alter service boundaries or critical invariants.

Typical examples:

- remove dead code in a focused area;
- use an existing SDK API correctly;
- eliminate a small duplicate where the shared shape is already obvious;
- fix a narrow bug with a targeted test or compose validation.

### 2. Plan Needed

Choose this lane when the issue is still implementation-oriented but needs explicit sequencing. Common triggers:

- multiple related files or modules;
- refactor or decomposition work;
- dependency updates with possible ripple effects;
- runtime-impacting paths such as `compose*.yml`, `services/**`, `mini_app/**`, `src/api/**`, `src/voice/**`, `src/ingestion/unified/**`, or `k8s/**`;
- changes where verification requires several deliberate steps rather than one local test.

This lane routes through:

- `brainstorming` if the shape is still ambiguous;
- `writing-plans` for the task breakdown;
- `executing-plans` for implementation.

### 3. Design First

Choose this lane when the issue is not just large, but structurally ambiguous. Common triggers:

- moving ownership across subsystem boundaries;
- introducing a new cross-cutting abstraction;
- changing retrieval, cache, graph, or ingestion contracts;
- large monolith splits or migrations;
- situations where there are multiple plausible architectures and the trade-off needs to be written down first.

This lane requires:

- short design discussion;
- written spec;
- user review of the spec;
- then `writing-plans`.

## DRY, SOLID, and Reuse Rules

The default is pragmatic reuse, not abstraction for its own sake.

- Prefer local fixes when repeated code is still evolving or only superficially similar.
- Extract shared code only when the repeated shape is stable and the abstraction reduces change risk.
- Use SOLID ideas only when they improve testability, replaceability, or safety in this repository.
- Do not create wrappers around SDKs or framework features unless the codebase already benefits from that boundary.

Inferred default for ambiguous small issues:

- if the duplicate is obvious, stable, and already touched by the issue, perform the small deduplication now;
- if the reuse shape is uncertain, fix locally and record a follow-up issue;
- if deduplication crosses subsystem boundaries or changes contracts, route to `Plan needed` or `Design first`.

## Session Workflow

For each new session:

1. Review current backlog candidates.
2. For each candidate, identify touched surfaces and likely blast radius.
3. Run SDK-first research using the repo registry, local code, and Context7 as needed.
4. Decide whether the issue is `Quick execution`, `Plan needed`, or `Design first`.
5. Start only one issue after its lane is explicit.

## Verification Rules By Lane

### Quick Execution

Use the smallest sufficient proof:

- targeted unit tests;
- narrow lint/type/test command;
- compose config validation for runtime surfaces;
- specific smoke validation if tests are not available.

### Plan Needed and Design First

Use repo validation rules from `AGENTS.md`, plus any stricter local override:

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

For runtime-impacting changes, also validate effective Compose service sets and image consistency:

- `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services`
- `COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config --services`
- `make verify-compose-images`

## Current Backlog Classification Snapshot

Based on the current issue list discussed in session:

- `Quick execution` candidates: `#1075`, `#1076`, `#1078`, `#1079`
- `Plan needed` candidates: `#1071`, `#1073`, `#1074`, `#1080`, `#1081`, `#1082`, `#1083`
- `Design first` candidate: `#1070`

This snapshot is only a starting point. The exact lane can change after issue-specific code discovery.

## Recommended Default

Use a hybrid policy:

- small, local, well-understood fixes can be executed directly after brief SDK-first research;
- medium and runtime-sensitive work should go through `writing-plans`;
- large or structurally ambiguous work should go through design, written spec, and then planning.

This gives fast throughput on low-risk fixes without normalizing under-scoped work on production-critical surfaces.
