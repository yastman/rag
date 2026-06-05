# Project Audit And Stage 4 Refactor Plan

Status: draft for Artem weekly planning
Date: 2026-06-05

Source documents:

- [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md)
- [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)
- [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- [`product-simplification-weekly-acceptance-2026-06-04.md`](product-simplification-weekly-acceptance-2026-06-04.md)

Worker audit artifacts:

- `logs/INTAKE.project-audit-stage4.md`
- `logs/AUDIT.compose-profile-stage4.md`
- `logs/AUDIT.python-boundary-stage4.md`
- `logs/AUDIT.test-gate-stage4.md`

## Goal

Create a safe audit-first path from the current broad RAG platform toward the
approved modular Python monolith direction.

The immediate goal is **not** to rewrite the system in one step. The immediate
goal is to:

1. capture the current state of required and optional runtime surfaces;
2. create GitHub Project tasks for the refactor;
3. record questions that need Artem's decision;
4. execute small task branches that preserve the protected proof:

```bash
make local-up
make e2e-core-live
```

## Target Shape

Target product shape:

```text
user query
  -> run_assistant_request()
  -> classify
  -> retrieve from Qdrant
  -> generate answer
  -> verify grounding
  -> propose optional CRM action
  -> HITL confirmation before write
```

Target runtime direction:

```text
Modular Python monolith
+ Qdrant as required external infrastructure
+ optional Redis / Postgres where product features need them
+ local BGE-M3 provider or explicitly approved service fallback
+ Docling as native/batch Python path
+ LiteLLM Python SDK or direct provider SDK path
+ structured JSON logs
+ optional Langfuse diagnostics
```

## Audit Skeleton

Run the audit as read-only worker tasks before implementation. Each worker must
return candidate GitHub issues, required Artem decisions, risks, and evidence
commands. Workers must not edit files, run production paths, access secrets, or
touch real CRM writes.

### Audit 1: Runtime And Compose Boundaries

Purpose:

- classify services as required core, optional-by-need, or optional surface;
- compare Compose profiles, Makefile targets, and docs against Stage 0/Stage 4;
- identify where `make local-up` differs from the minimal core proof.

Inputs:

- `compose.yml`
- `compose.dev.yml`
- `DOCKER.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/indexes/`
- `Makefile`

Known findings from first audit:

- `make e2e-core-live` requires Qdrant and BGE-M3.
- `make local-up` includes Postgres, Redis, Qdrant, BGE-M3, and lists LiteLLM,
  but LiteLLM is profile-gated and does not actually start without `bot`.
- Langfuse, voice, and observability stacks are correctly optional.
- Docling, Mini App, and user-base need a clearer default/profile decision.

### Audit 2: Python Boundaries

Purpose:

- identify internal HTTP boundaries in the core path;
- identify optional-surface imports that still make core code hard-dependent on
  optional systems;
- verify that `src/core/assistant.py` remains the clean entrypoint contract.

Inputs:

- `src/core/`
- `src/runtime/`
- `telegram_bot/graph/`
- `telegram_bot/services/`
- `src/ingestion/`

Known findings from first audit:

- `src/core/assistant.py` is clean and dependency-injected.
- `src/core/pipeline.py` has a module-level Langfuse import and should not be
  part of a required no-Langfuse core path until fixed.
- BGE-M3 query-time embeddings still go through HTTP to the BGE-M3 service.
- Docling already has a native adapter, but HTTP remains the default path.
- LiteLLM is currently used as an OpenAI-compatible proxy endpoint rather than
  as the Python SDK inside the app.

### Audit 3: Test And Gate Boundaries

Purpose:

- verify that fast PR gates remain service-free;
- verify that live E2E remains explicit/manual/nightly;
- verify that trace, Langfuse, Telegram, voice, Mini App, k8s, and CRM writes
  are not required for the protected core proof.

Inputs:

- `Makefile`
- `.github/workflows/`
- `tests/e2e/test_core_live_ingest_answer.py`
- `tests/e2e_core/`
- `tests/contract/`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/engineering/test-writing-guide.md`

Known findings from first audit:

- Test/gate boundaries are currently consistent with Stage 4.
- `make e2e-core-live` is correctly isolated from fast PR gates.
- Langfuse/trace targets are optional diagnostics.
- CRM/HITL is mock-isolated in the core E2E.

## GitHub Project Workflow

GitHub Project is the operational source of truth for the current queue. The
design docs remain the source of truth for architecture and constraints.

For each Stage 4 task:

- create one GitHub issue or Project item;
- use one branch:

```text
simplification/<issue-or-task-number>-<short-name>
```

- target PRs to `simplification/core`, not `dev`;
- include allowed files, forbidden surfaces, acceptance checks, and docs impact;
- mark `requires Artem decision` when the task touches runtime surfaces,
  service/container boundaries, dependencies, CRM/HITL writes, core entrypoint
  API, or CI/release gate semantics.

Do not merge simplification work into `dev` without explicit Artem approval of
the weekly package.

## Refactor Roadmap

### Track 0: Governance Before Code

Goal:

- make the agent gateway match the workflow before workers implement Stage 4.

Tasks:

1. Commit the current `AGENTS.md` governance update on a task branch.
2. Resolve or intentionally ignore unrelated untracked files before
   implementation work.
3. Create Stage 4 Project items from this plan.

Acceptance:

- `AGENTS.md` says docs are strategic truth and GitHub Project is operational
  truth.
- `AGENTS.md` says one task equals one branch.
- `AGENTS.md` says `dev` merge requires Artem approval.
- `AGENTS.md` says Artem decision questions become GitHub TODOs.

### Track 1: Low-Risk Optionalization

Goal:

- remove obvious optional-surface hard dependencies without changing runtime
  architecture.

First candidate task:

- Make Langfuse optional in `src/core/pipeline.py` by replacing the module-level
  `from langfuse import observe` with the repo's no-op-capable observability
  facade or a local guarded decorator.

Acceptance:

- core imports do not require Langfuse;
- existing optional trace tests still pass;
- no Docker, CRM, Telegram, Qdrant, or BGE-M3 behavior changes.

### Track 2: Core Runtime Split

Goal:

- separate the minimal core proof from the broader bot developer runtime.

Candidate tasks:

- create or design a `core-up` path for Qdrant plus the currently required
  embedding provider;
- keep `local-up` as the bot development loop when Postgres/Redis are needed;
- fix the misleading LiteLLM listing in `LOCAL_SERVICES` or docs.

Acceptance:

- docs clearly distinguish core proof runtime from bot development runtime;
- `make e2e-core-live` remains the protected proof;
- no optional surface becomes a required fast gate.

### Track 3: BGE-M3 Provider Decision

Goal:

- decide and then implement the embedding boundary.

Decision needed:

- move BGE-M3 in-process now, or keep the BGE-M3 service as an approved fallback
  while the monolith migration is staged?

Audit questions:

- Can the in-process path preserve dense vector dimensions and normalization?
- Can it preserve sparse and ColBERT outputs used by Qdrant?
- What are CPU/RAM/concurrency limits?
- Does ingestion need a separate CLI/job queue?

Acceptance for a future implementation task:

- output compatibility is tested before switching defaults;
- `make e2e-core-live` still passes;
- memory/concurrency limits are documented.

### Track 4: Docling Native Default

Goal:

- move ingestion parsing toward native/batch Python execution instead of a
  persistent service, if approved.

Current state:

- native Docling adapter already exists;
- HTTP backend remains the default.

Decision needed:

- make native Docling the default backend, or keep HTTP as default until
  packaging/runtime cost is measured?

Acceptance:

- ingestion behavior is equivalent for the fixture corpus;
- Docling service is optional/profile-gated if native becomes default;
- docs explain how to opt into the HTTP backend.

### Track 5: LiteLLM Python SDK Monolith

Goal:

- evaluate replacing the LiteLLM proxy dependency with an in-process LiteLLM SDK
  adapter.

Current state:

- runtime LLM calls use OpenAI-compatible clients with `LLM_BASE_URL`;
- LiteLLM proxy is optional/profile-gated but still part of some runtime docs;
- the `litellm` Python package is not currently installed in the local env.

Decision needed:

- add LiteLLM Python SDK as an app dependency and provide an adapter, or keep
  the OpenAI-compatible client path and treat LiteLLM proxy as optional?

Acceptance for a future implementation task:

- adapter preserves the current `chat.completions.create(...)` call shape;
- streaming, usage/model extraction, `extra_body`, reasoning controls, fallback
  behavior, and structured-output paths are covered;
- `instructor.from_openai(...)` paths are not broken.

### Track 6: AutoResearch As Separate Initiative

Goal:

- decide whether the untracked AutoResearch prompt becomes a future development
  issue.

Current state:

- `rockfresh-autoresearch-summary-and-implementation-prompt.md` is an untracked
  proposal artifact;
- it is aligned with the monolith direction, but it is not part of current
  Stage 4 runtime simplification.

Decision needed:

- create a separate GitHub issue for a safe `autoresearch/` skeleton, or defer.

Acceptance if approved later:

- no production self-modification;
- candidate-only skill/report loop;
- mock evaluator first;
- no CRM write, Docker, Langfuse, Qdrant runtime, or Telegram changes.

## Artem Decisions To Record

Record these as GitHub Project TODOs before implementation:

1. Confirm Stage 4 audit scope: core-vs-optional boundary first.
2. Decide BGE-M3 in-process now versus service fallback during migration.
3. Decide Redis mandatory versus optional/degraded mode for core.
4. Decide Postgres in `local-up` versus separate `core-up`.
5. Decide Docling native default.
6. Decide LiteLLM Python SDK adapter versus OpenAI-compatible client path.
7. Decide whether AutoResearch becomes a separate future issue.

## Immediate Next Actions

1. Create branch `simplification/agent-gateway-stage4-rules`.
2. Commit `AGENTS.md` governance changes.
3. Create GitHub Project items from this plan.
4. Ask Artem to confirm the decision list above.
5. Start with the lowest-risk code task: make Langfuse optional in
   `src/core/pipeline.py`.

## Non-Goals For The First Refactor Wave

- Do not rewrite the whole RAG pipeline.
- Do not remove Docker services without explicit approval.
- Do not touch real CRM write paths.
- Do not make Langfuse, OTel, voice, Mini App, k8s, or trace validation
  required again.
- Do not merge directly to `dev`.
- Do not implement AutoResearch inside the production request path.
