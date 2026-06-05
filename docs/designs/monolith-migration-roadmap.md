# Monolith Migration Roadmap

Status: draft for `simplification/core` staging
Date: 2026-06-05

Source documents:

- [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md)
- [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)
- [`project-audit-and-stage-4-refactor-plan.md`](project-audit-and-stage-4-refactor-plan.md)

Related staging work:

- PR `#2371` — Stage 4 governance and audit plan
- PR `#2373` — Langfuse hard imports optionalized
- PR `#2375` — opt-in BGE-M3 local provider spike
- PR `#2376` — `simplification/core` opt-in staging governance

## Goal

Move `rag-fresh` from a broad service-heavy RAG platform toward an approved
modular Python monolith, while keeping `dev` protected and preserving the
current proof:

```bash
make local-up
make e2e-core-live
```

This roadmap is not a single rewrite task. It is a queue of small, reviewable
GitHub issues that build evidence in `simplification/core`. Artem receives a
weekly package and decides which staging changes become default behavior or move
to `dev`.

## Target Shape

The future product runtime should look like this:

```text
src/core/
  assistant.py            # stable public entrypoint: run_assistant_request()
  contracts.py            # request/result/HITL/action contracts

src/runtime/
  graph/                  # orchestration and config factories
  retrieval/              # retrieval flow and provider-neutral contracts
  generation/             # LLM generation and grounding
  actions/                # optional CRM/HITL action proposals
  observability/          # structured logs and optional diagnostics

src/providers/
  embeddings/             # BGE-M3 local/HTTP provider implementations
  llm/                    # OpenAI-compatible/LiteLLM SDK/direct SDK adapters
  documents/              # Docling native/batch/HTTP adapters
  storage/                # Qdrant, optional Redis/Postgres adapters

src/ingestion/
  pipelines/              # batch/native indexing flows
  sources/                # source adapters

telegram_bot/
  interface only          # Telegram-specific UI/input/output, no core ownership
```

Required core infrastructure:

- Qdrant for vector search until a separate decision says otherwise.

Optional or staged infrastructure:

- BGE-M3 HTTP container remains a fallback while local provider parity is
  measured.
- Redis is optional cache/checkpoint infrastructure unless a feature needs it.
- Postgres is optional application state unless a product workflow needs it.
- Docling service should become native or batch Python ingestion when proven.
- LiteLLM proxy should become optional; runtime should support in-process SDK or
  direct OpenAI-compatible clients.
- Langfuse/OTel remain diagnostics, not required core path.

## Operating Rules

- One issue equals one branch.
- Branch format: `simplification/<issue-or-task-number>-<short-name>`.
- PR target: `simplification/core`, never `dev`.
- `simplification/core` may receive opt-in/staging spikes after focused
  validation and review.
- Do not change default runtime, required dependencies, container fate, Qdrant
  schema/reindex strategy, CRM/HITL writes, or CI/release gates without an Artem
  decision.
- Every runtime/config/code task must record docs impact.
- Every task that raises an architecture or runtime decision becomes a GitHub
  issue/Project TODO for weekly acceptance.

## Wave 0: Roadmap And Backlog

Purpose:

- turn the current audits into an executable queue;
- avoid one giant refactor branch;
- make the future skeleton visible before code moves.

Issues to create:

1. `roadmap(simplification): monolith migration task map`
   - Output: this roadmap linked from `docs/designs/README.md`.
   - Acceptance: GitHub Project has the first wave issues.

2. `audit(simplification): current skeleton map`
   - Output: current module/service map.
   - Include: core, runtime, Telegram, ingestion, API, Mini App, services,
     Compose, Makefile, tests.
   - Acceptance: each area is classified as `core-required`,
     `optional-by-need`, `interface`, `legacy`, or `candidate-removal`.

3. `design(simplification): target monolith skeleton`
   - Output: target package/module skeleton and ownership table.
   - Acceptance: no code move yet; only interfaces, contracts, and allowed
     boundaries.

Validation:

```bash
git diff --check
```

## Wave 1: Current Skeleton Audit

Purpose:

- understand what exists before moving it;
- avoid deleting code that is still a real dependency;
- identify owners and tests for each future move.

Audit dimensions:

- Import ownership:
  - `src/core`
  - `src/runtime`
  - `telegram_bot`
  - `src/ingestion`
  - `src/api`
  - `services`
  - `mini_app`
- Runtime surfaces:
  - required core proof;
  - bot developer runtime;
  - ingestion runtime;
  - optional observability;
  - optional UI/API surfaces.
- External dependencies:
  - Qdrant;
  - BGE-M3;
  - Redis;
  - Postgres;
  - Docling;
  - LiteLLM;
  - Langfuse/OTel.
- Verification ownership:
  - fast unit/contract tests;
  - focused integration tests;
  - `make e2e-core-live`;
  - optional profile checks.

Issues to create:

1. `audit(simplification): Python ownership and import map`
   - Find reverse-layered imports and re-export shims.
   - Produce a table of "move now", "keep until later", "do not move".

2. `audit(simplification): runtime and Compose profile map`
   - Compare `compose.yml`, `compose.dev.yml`, `DOCKER.md`, Makefile, and
     docs.
   - Identify ghost services and default/profile drift.

3. `audit(simplification): test gate map`
   - Map touched surfaces to focused test commands.
   - Confirm no optional surface is required by fast gates.

Acceptance:

- No code changes except docs/audit output.
- Each finding has a proposed issue or explicit "defer" reason.

## Wave 2: Target Skeleton Design

Purpose:

- define the monolith shape before moving files;
- make future code moves mechanical and reviewable.

Target ownership:

| Area | Owner | Rule |
| --- | --- | --- |
| `src/core` | Product entrypoint | No Telegram, no live CRM writes, no optional diagnostics requirement |
| `src/runtime` | Core orchestration | Provider-neutral factories and retrieval/generation flow |
| `src/providers` | External capability adapters | Thin SDK/native/HTTP wrappers behind stable contracts |
| `src/ingestion` | Document indexing | Batch/native paths, no bot UI ownership |
| `telegram_bot` | Telegram interface | Calls core/runtime, does not own RAG pipeline logic |
| `services` | Optional service fallbacks | No required service boundary unless approved |

Issues to create:

1. `design(simplification): provider contracts`
   - Define embedding provider contract.
   - Define LLM provider contract.
   - Define document parser provider contract.
   - Define storage/cache provider contract.

2. `design(simplification): target package skeleton`
   - Propose directories and README/AGENTS.override ownership.
   - Include "do not move yet" list.

3. `design(simplification): core dependency rules`
   - Core may depend on provider contracts.
   - Core must not depend on Telegram, Mini App, voice, Langfuse, or live CRM
     writes.

Acceptance:

- Design docs only.
- No runtime default behavior changes.

## Wave 3: Provider Spikes And Decisions

Purpose:

- replace service boundaries with in-process providers only when evidence says
  it is safe;
- keep opt-in staging changes in `simplification/core` until Artem decides the
  default migration.

### BGE-M3

Current state:

- Opt-in local provider exists in `simplification/core`.
- HTTP BGE-M3 remains default.

Next issues:

1. `bench(simplification): BGE-M3 HTTP vs local provider parity`
   - Compare dense dimensions and vector value drift.
   - Compare sparse `indices` / `values` contract.
   - Compare ColBERT multivector shape.
   - Record latency, memory, and model loading behavior.

2. `decision(simplification): BGE-M3 default migration`
   - Options:
     - keep HTTP service fallback;
     - make local provider default;
     - reindex with local provider;
     - use in-process ONNX instead of FlagEmbedding.

Do not do without Artem:

- change default provider;
- require `ml-local`/torch for default runtime;
- remove/demote the container;
- change Qdrant schema or reindex strategy.

### LiteLLM

Next issues:

1. `spike(simplification): LiteLLM Python SDK adapter`
   - Preserve current `chat.completions.create(...)` call shape.
   - Keep OpenAI-compatible client path working.
   - Do not make proxy removal part of the first spike.

2. `decision(simplification): LiteLLM SDK vs OpenAI-compatible path`
   - Decide whether LiteLLM SDK is required, optional, or unnecessary.

Do not do without Artem:

- require LiteLLM SDK for default runtime;
- remove proxy/container docs;
- change LLM routing semantics.

### Docling

Next issues:

1. `spike(simplification): Docling native default candidate`
   - Compare native adapter and HTTP service output contracts.
   - Preserve chunk contract.
   - Keep HTTP path as fallback.

2. `decision(simplification): Docling native default`
   - Decide native/batch default versus service fallback.

Do not do without Artem:

- remove docling service;
- change ingestion default for production-like runs;
- require optional ingest extra in default runtime.

## Wave 4: Runtime And Compose Cleanup

Purpose:

- make local runtime surfaces match the target monolith direction;
- stop optional services from looking required;
- keep the protected proof explicit.

Issues to create:

1. `runtime(simplification): split core-up from local-up`
   - `core-up`: minimal services for protected proof.
   - `local-up`: broader bot developer loop.
   - Preserve existing `make local-up && make e2e-core-live` until replacement
     is explicitly accepted.

2. `docs(simplification): Compose profile matrix`
   - Required core.
   - Bot dev.
   - Ingestion.
   - Observability.
   - Voice.
   - Mini App/API.

3. `fix(simplification): LiteLLM ghost listing`
   - Fix Makefile/docs claims where LiteLLM is listed but profile-gated.

4. `runtime(simplification): profile-gate optional surfaces`
   - Docling service.
   - Mini App.
   - User-base.
   - Voice.
   - Langfuse/observability.

Acceptance:

- `make local-up && make e2e-core-live` still passes.
- Fast PR gates remain service-free.
- No optional surface becomes required.

## Wave 5: Code Move And Boundary Cleanup

Purpose:

- move ownership from `telegram_bot` shims into `src/core`, `src/runtime`, and
  `src/providers`;
- reduce reverse-layering;
- avoid broad rewrites.

Rules:

- One move per issue.
- Keep re-export shim until all call sites are migrated.
- Add or preserve focused tests before deleting a shim.
- Do not move UI/Telegram behavior into core.

Candidate issues:

1. `move(simplification): embedding wrappers to provider package`
   - Move canonical provider ownership under future provider skeleton when
     design is accepted.
   - Keep back-compat imports until tests confirm no runtime drift.

2. `move(simplification): LLM client factory to provider package`
   - Keep `GraphConfig.create_llm()` compatibility.
   - Extract provider adapter only after LiteLLM/OpenAI decision.

3. `move(simplification): retrieval flow ownership cleanup`
   - Ensure retrieval logic lives under runtime/core, not Telegram.

4. `move(simplification): CRM action proposal boundary`
   - Keep live writes outside core.
   - Core returns proposed action and HITL requirement.

5. `move(simplification): ingestion parser provider boundary`
   - Separate native/batch/HTTP Docling provider from ingestion orchestration.

Acceptance:

- Each move has before/after import tests or focused regression tests.
- `make e2e-core-live` remains green after each task.

## Wave 6: Optionality And Deletion Candidates

Purpose:

- remove real dead weight only after it is proven optional or unused;
- avoid deleting surfaces prematurely.

Process:

1. Mark candidate as optional/deprecated.
2. Add tests or docs proving default core path does not need it.
3. Keep for one weekly package if risk is non-trivial.
4. Remove/archive only after Artem decision.

Candidate buckets:

- `telegram_bot` re-export shims after call sites move.
- BGE-M3 HTTP service after provider parity/default decision.
- Docling HTTP service after native/default decision.
- LiteLLM proxy after SDK/direct-client decision.
- Mini App/API/User-base if outside product focus.
- Legacy trace/manual propagation after OTel/Langfuse optional diagnostics are
  stable.

Do not delete without Artem:

- user-facing surfaces;
- containers/services;
- CRM/HITL paths;
- trace gates or diagnostics required by accepted workflow;
- anything with unclear ownership.

## Wave 7: Weekly Package To Artem

Purpose:

- turn staging evidence into a clear decision package;
- keep Artem review bounded to architecture/product decisions, not every small
  PR.

Package contents:

- `simplification/core` commit range.
- PR list with short summaries.
- Protected proof results.
- Default behavior changes: yes/no.
- New required dependencies: yes/no.
- New/removal of services: yes/no.
- CRM/HITL changes: yes/no.
- Decisions requested:
  - BGE-M3 default/fallback/reindex;
  - Docling native default;
  - LiteLLM SDK/direct-client path;
  - Redis/Postgres optionality;
  - container/profile cleanup;
  - deletion/archive candidates.

Acceptance question:

```text
Approve, partially approve, or block simplification/core -> dev up to <sha>?
```

## Validation Ladder

For docs/audit tasks:

```bash
git diff --check
```

For focused code/provider tasks:

```bash
UV_PROJECT_ENVIRONMENT=/home/user/projects/rag-fresh/.venv uv run --no-sync pytest <focused-test-file> -q
UV_PROJECT_ENVIRONMENT=/home/user/projects/rag-fresh/.venv uv run --no-sync ruff check <changed-python-files>
```

For core runtime tasks:

```bash
make local-up
make e2e-core-live
```

For optional profile tasks:

```bash
docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml --compatibility config --services
```

Run optional profile checks only for touched profiles. Do not make optional
profiles part of fast PR gates unless a separate decision says so.

## Immediate Next Issues

Create these first:

1. `audit(simplification): current skeleton map`
2. `design(simplification): target monolith skeleton`
3. `bench(simplification): BGE-M3 HTTP vs local provider parity`
4. `runtime(simplification): split core-up from local-up`
5. `docs(simplification): Compose profile matrix`
6. `fix(simplification): LiteLLM ghost listing`
7. `spike(simplification): LiteLLM Python SDK adapter`
8. `spike(simplification): Docling native default candidate`
9. `audit(simplification): Redis and Postgres optionality`
10. `audit(simplification): deletion and archive candidates`

Recommended first execution order:

```text
1. current skeleton map
2. target monolith skeleton
3. BGE-M3 parity benchmark
4. core-up/local-up split
5. Compose profile matrix
```

This order gives enough evidence to keep moving in `simplification/core` while
preparing a concise weekly package for Artem.
