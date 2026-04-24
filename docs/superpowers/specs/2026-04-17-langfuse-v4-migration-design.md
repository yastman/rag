# Langfuse V4 Migration Design

## Context

Issue `#1174` tracks a blocked dependency upgrade: the repository intentionally held `langfuse` at `3.14.6` because the current codebase still depends on v3-only tracing APIs.

This repository is not a single application. Langfuse spans several runtime surfaces:

- Telegram bot request handling and pipelines in `/home/user/projects/rag-fresh/telegram_bot/`;
- FastAPI request handling in `/home/user/projects/rag-fresh/src/api/`;
- voice lifecycle tracing in `/home/user/projects/rag-fresh/src/voice/`;
- ingestion lifecycle tracing in `/home/user/projects/rag-fresh/src/ingestion/unified/`;
- evaluation and developer-facing observability helpers in `/home/user/projects/rag-fresh/src/evaluation/`.

The migration therefore needs to be repo-wide, not a narrow fix in one helper file.

Official Langfuse v4 documentation changes the mental model from trace-centric mutation to an observation-first model:

- correlating attributes such as `user_id`, `session_id`, `tags`, `metadata`, and `trace_name` should be propagated via `propagate_attributes(...)`;
- spans should be created via `start_as_current_observation(as_type="span", ...)`;
- observation data should be written via `observation.update(...)` or current-observation update methods;
- LangChain `CallbackHandler(update_trace=...)` is no longer valid.

## Problem

The repository currently relies on patterns that are either removed or no longer the primary integration path in Langfuse v4:

- `update_current_trace(...)`;
- `start_as_current_span(...)`;
- child span creation with `start_as_current_span(...)`;
- LangChain `CallbackHandler(update_trace=...)`;
- tests that assert those v3-specific APIs directly.

If we only change the dependency version without changing these patterns, observability will either fail at runtime or silently drift in ways that break dashboards, trace continuity, or debugging workflows.

If we add a custom compatibility layer to preserve v3 calling conventions, we would keep the codebase anchored to the old mental model and carry an unnecessary maintenance boundary around an SDK that already has a documented v4 migration path.

## Goals

- Upgrade the repository to native `Langfuse 4.x` usage.
- Remove v3-only tracing patterns across the repo.
- Preserve useful observability semantics where they matter:
  - request or lifecycle trace continuity;
  - current `session_id`, `user_id`, `tags`, and diagnostic metadata;
  - existing score names and latency metrics where practical.
- Keep the migration aligned with official Langfuse documentation rather than inventing repo-local tracing abstractions.
- Re-run the validation set for issue `#1174`, plus repo-wide checks appropriate for a cross-system dependency migration.

## Non-Goals

- This design does not introduce a new observability framework on top of Langfuse.
- This design does not try to emulate v3 APIs indefinitely inside the repository.
- This design does not redesign unrelated telemetry, logging, or metrics systems.
- This design does not guarantee identical trace rendering in the Langfuse UI when the upstream data model itself changed between v3 and v4.

## Current-State Findings

### Blocking v3 Patterns

Current repo usage includes:

- `update_current_trace(...)` in runtime request paths, pipeline paths, evaluation helpers, and API handling;
- `start_as_current_span(...)` in evaluation examples and middleware-oriented tracing helpers;
- `CallbackHandler(update_trace=...)` expectations in LangChain callback creation;
- test suites that explicitly mock and assert the old methods.

### Primary Runtime Surfaces

The migration affects at least these areas:

- `/home/user/projects/rag-fresh/telegram_bot/observability.py`
- `/home/user/projects/rag-fresh/telegram_bot/bot.py`
- `/home/user/projects/rag-fresh/telegram_bot/middlewares/langfuse_middleware.py`
- `/home/user/projects/rag-fresh/telegram_bot/pipelines/client.py`
- `/home/user/projects/rag-fresh/src/api/main.py`
- `/home/user/projects/rag-fresh/src/voice/observability.py`
- `/home/user/projects/rag-fresh/src/ingestion/unified/observability.py`
- `/home/user/projects/rag-fresh/src/evaluation/langfuse_integration.py`

The test surface is also broad because many unit tests currently assert call shapes for old methods rather than repository behavior under the new model.

### Main Migration Constraint

The repo already has a useful observability entrypoint in `/home/user/projects/rag-fresh/telegram_bot/observability.py`. That file should remain the common initialization and safe-export location for the SDK, but it must not become a custom shim that redefines v4 in v3 terms.

## Recommended Approach

Use a repo-wide native Langfuse v4 migration.

This means:

1. keep one shared SDK initialization and export surface;
2. migrate all runtime call sites to v4 concepts directly;
3. rewrite tests to validate v4 behavior and observability outcomes instead of old method names;
4. avoid introducing a compatibility layer or wrapper that hides the new Langfuse model.

This is better than the alternatives:

- better than a narrow blocker-only fix, because the current repo already contains v3 patterns beyond the issue body and hidden failures would remain;
- better than a compatibility shim, because the official migration path already exists and the shim would become tech debt immediately.

## Target V4 Model

### Core Rule

The repository should treat Langfuse v4 as observation-first.

That means:

- use `propagate_attributes(...)` for correlating attributes;
- use `start_as_current_observation(as_type="span", ...)` for root and nested spans;
- use `observation.update(...)` or current-observation update methods for input, output, and metadata updates tied to an active observation;
- keep trace-level I/O helpers only if a concrete legacy requirement remains after migration review.

### Trace and Observation Semantics

The migration should preserve the repository's functional tracing intent:

- a request, callback, pipeline execution, ingestion command, or voice lifecycle should still form one coherent trace lineage;
- nested work should still appear as child observations where the runtime already has that structure;
- tags, session identifiers, and user identifiers should still be queryable in Langfuse.

The migration does not require preserving the old implementation detail that these values were imperatively written to a trace object after the fact.

### Root Observation Ownership

Every major runtime entrypoint should have a clear root observation owner:

- Telegram request handling owns bot-request traces;
- API endpoint handling owns API traces;
- voice lifecycle helpers own voice-session traces;
- ingestion command helpers own ingestion traces;
- evaluation helpers own evaluation traces.

That ownership prevents the current pattern where unrelated code paths each try to mutate the "current trace" implicitly.

## Migration Pattern Mapping

### Pattern A: `update_current_trace(...)`

Old use:

- set `session_id`, `user_id`, `tags`, `metadata`, and sometimes `input` and `output` on the active trace.

New use:

- `propagate_attributes(...)` for correlating attributes;
- root observation input and output written on the active observation;
- use trace-level I/O fallback only if a real legacy evaluator or dashboard requires it.

Migration rule:

- split correlation from I/O;
- do not replace one imperative trace mutation with another repo-local helper that hides the split.

### Pattern B: `start_as_current_span(...)`

Old use:

- create a root or child span and rely on trace-centric updates later.

New use:

- `start_as_current_observation(as_type="span", ...)` for root and nested spans;
- direct `.update(...)` on the returned observation where the code already has a handle;
- current-observation update methods only when direct access is awkward and there is an active context.

### Pattern C: `CallbackHandler(update_trace=...)`

Old use:

- LangChain callback handler performs trace updates using v3 semantics.

New use:

- `CallbackHandler(...)` without `update_trace`;
- enclosing `propagate_attributes(...)` establishes the context for callbacks and descendants;
- when needed, an explicit enclosing observation frames the LangChain request.

### Pattern D: Tests Coupled To Old APIs

Old use:

- tests assert `update_current_trace.assert_called_once()` or similar;
- tests mock `start_as_current_span(...)`.

New use:

- assert `propagate_attributes(...)` context usage where it is the core contract;
- assert active observation creation and update behavior;
- prefer outcome assertions over method-name assertions:
  - metadata is attached;
  - tags are preserved;
  - scores are written;
  - errors remain fail-soft;
  - trace continuity fields are forwarded.

## Component Design

### `/home/user/projects/rag-fresh/telegram_bot/observability.py`

Role after migration:

- initialize Langfuse;
- retain bootstrap and safe degradation behavior;
- export native SDK functions used across the repo;
- keep shared masking and model-definition synchronization utilities.

Constraints:

- no repo-local v3 emulation layer;
- no "compat" helper that reintroduces `update_current_trace(...)` semantics under a different name.

### `/home/user/projects/rag-fresh/telegram_bot/bot.py`

Role after migration:

- define request-level root observation ownership for bot flows;
- propagate request attributes before downstream graph, retrieval, and LLM work;
- write root observation input and final output in a v4-compatible way;
- preserve score writing and latency metrics.

Primary risk:

- this file contains many existing trace updates, so migration must group work by request lifecycle rather than line-by-line substitution.

### `/home/user/projects/rag-fresh/telegram_bot/middlewares/langfuse_middleware.py`

Role after migration:

- open or frame Telegram event observations early;
- propagate request-correlating attributes into handler execution;
- stop depending on v3 span creation names.

### `/home/user/projects/rag-fresh/telegram_bot/pipelines/client.py`

Role after migration:

- preserve pipeline observability and latency reporting;
- move trace metadata propagation to v4 context propagation;
- keep score emission semantics stable where possible.

### `/home/user/projects/rag-fresh/src/api/main.py`

Role after migration:

- continue using `@observe`;
- make API root observation own request input, output, and metadata;
- preserve `langfuse_trace_id` continuity where supported by the v4 API flow;
- remove trace-centric assumptions that are no longer primary in v4.

### `/home/user/projects/rag-fresh/src/voice/observability.py`

Role after migration:

- model voice lifecycle events through v4 observations and propagated attributes;
- keep stable session naming for voice calls;
- preserve best-effort behavior so tracing failures do not break voice runtime.

### `/home/user/projects/rag-fresh/src/ingestion/unified/observability.py`

Role after migration:

- keep ingestion command family traces coherent;
- move lifecycle updates into v4-compatible context and observation updates;
- preserve fail-soft behavior for CLI and ingestion flows.

### `/home/user/projects/rag-fresh/src/evaluation/langfuse_integration.py`

Role after migration:

- become the canonical in-repo example of v4 usage;
- remove v3 examples from code and docstrings;
- explicitly model retrieval and evaluation spans using v4 observation APIs.

## Data Flow Design

### Telegram And API Requests

Target flow:

1. create or enter a root observation for the request;
2. apply `propagate_attributes(...)` with request identity and tags;
3. execute downstream graph, retrieval, and LLM work inside that context;
4. update the root observation with final output and relevant metadata;
5. emit scores and latency measurements;
6. flush or best-effort complete according to existing runtime behavior.

### Voice And Ingestion Lifecycles

Target flow:

1. establish stable session identifiers from the existing lifecycle keys;
2. propagate lifecycle attributes through v4 context;
3. update the active observation with status and event metadata;
4. preserve current fail-soft tracing behavior.

### LangChain Callback Paths

Target flow:

1. open an enclosing observation when a distinct request-level frame is needed;
2. apply `propagate_attributes(...)` before invoking the chain;
3. pass `CallbackHandler()` without `update_trace`;
4. rely on v4 propagation for tags, user, session, and metadata continuity.

## Invariants

The migration must preserve these repo-level invariants:

- transport-layer code still must not absorb unrelated retrieval or domain logic;
- no new cross-system observability abstraction layer should appear;
- existing score names should remain stable unless a concrete v4 incompatibility makes that impossible;
- trace continuity fields already passed across bot or API boundaries must not be dropped silently;
- tracing failures must remain non-fatal for production request paths;
- evaluation and example files must no longer teach or demonstrate removed v3 APIs.

## Risks And Mitigations

### Risk: Silent Semantics Drift

Some data that used to appear attached to a trace object may now live on the root observation.

Mitigation:

- preserve names, tags, and metadata keys where possible;
- prefer behavior-based verification over UI-shape assumptions;
- document known unavoidable v4 display differences after validation.

### Risk: Incomplete Repo Migration

Because v3 patterns are spread across many files, a blocker-only pass could leave hidden failures.

Mitigation:

- inventory all direct v3 API usages before implementation;
- treat runtime code and tests as part of the same migration, not separate follow-up work.

### Risk: Over-Customization

The repo may be tempted to introduce helpers that recreate old semantics.

Mitigation:

- keep helpers limited to shared initialization, masking, and safe utility concerns;
- reject helpers whose main job is to translate v3 calling conventions into v4.

### Risk: OpenTelemetry Export Drift

Langfuse v4 changes default OpenTelemetry export behavior.

Mitigation:

- validate whether the repo depends on non-LLM exported spans today;
- if needed, configure export behavior explicitly instead of assuming v3 defaults persist.

## Verification Strategy

### Issue-Level Validation

Run the validation set recorded on issue `#1174`:

- `uv run pytest tests/unit/dialogs/test_dialog_dependency_baseline.py tests/unit/services/test_generate_response.py tests/integration/test_graph_paths.py -q`
- `uv run pytest tests/unit/retrieval -q`
- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- `uv run pytest tests/integration/test_graph_paths.py -n auto --dist=worksteal -q`

### Focused Regression Validation

Add or update targeted tests for:

- middleware observation creation and propagation;
- callback handler creation without `update_trace`;
- bot and pipeline request metadata propagation;
- API trace continuity with provided trace ids;
- voice and ingestion lifecycle metadata updates;
- evaluation helper v4 span structure;
- fail-soft behavior when Langfuse calls raise.

### Migration Completion Check

Before declaring the migration complete:

- search for remaining direct v3-only API names;
- confirm dependency constraints now allow `langfuse 4.x`;
- verify examples and docs in touched source files no longer instruct v3 usage.

## Implementation Order

1. Inventory all remaining v3-only Langfuse API usages and callback-handler call sites.
2. Update dependency constraints to permit `langfuse 4.x`.
3. Migrate the shared observability entrypoint to clean v4-native exports.
4. Migrate middleware, voice, ingestion, and API boundary helpers.
5. Migrate bot and pipeline request flows.
6. Migrate evaluation helpers and examples.
7. Update unit and integration tests to assert v4 behavior.
8. Run the full validation set and document any unavoidable semantic differences.

## Completion Criteria

The migration is complete when all of the following are true:

- the repo no longer depends on removed Langfuse v3 APIs;
- LangChain callback integration no longer uses `update_trace=...`;
- runtime request and lifecycle paths still produce coherent observability context;
- the issue `#1174` validation set passes;
- repo-wide checks pass or any skipped validation is explicitly justified;
- the repository's touched source files and examples now reflect native Langfuse v4 usage.
