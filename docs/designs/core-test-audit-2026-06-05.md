# Core Test Boundary Audit — 2026-06-05

Status: audit complete, implementation backlog proposed.

## Scope

This audit reviews the test suite as a blocker map for the product-core
simplification work. The goal is not to reduce test count. The goal is to stop
old tests from preserving the current mixed boundary:

```text
src/core -> telegram_bot -> graph/services/agents
```

The target boundary for the next refactor wave is:

```text
src/core -> src.runtime
telegram_bot -> adapter/shims around src.runtime
```

The audit was run from native WSL/Linux on branch
`simplification/test-audit-core-boundaries`, based on `simplification/core` at
`a0de67fb7d16d52919dc20228e925bc2432f2c31`.

## Source Evidence

Commands and files inspected:

- `uname -a`
- `Makefile`
- `pyproject.toml`
- `.github/workflows/ci.yml`
- `.github/workflows/nightly-heavy.yml`
- `docs/engineering/test-writing-guide.md`
- `tests/unit/core/test_assistant_entrypoint.py`
- `tests/e2e/test_core_live_ingest_answer.py`
- `tests/e2e_core/live_harness.py`
- `tests/unit/e2e_core/test_live_harness.py`
- `tests/unit/runtime/graph/test_builder.py`
- `tests/integration/test_graph_paths.py`
- `tests/unit/graph/test_graph.py`
- `tests/smoke/test_langgraph_smoke.py`
- `tests/contract/test_core_live_gate_contract.py`
- `tests/contract/test_core_live_gate_placement_contract.py`
- `tests/contract/test_runtime_phase1_modules_present_contract.py`
- `tests/contract/test_layering_no_telegram_bot_imports_contract.py`

Suite shape from file inventory:

| Area | Test files |
|---|---:|
| Total `test_*.py` files | 660 |
| `tests/unit/` | 505 |
| `tests/contract/` | 112 |
| `tests/integration/` | 16 |
| `tests/smoke/` | 12 |
| `tests/e2e/` | 2 |
| `tests/e2e_core/` | 1 |

The count is not itself a problem. The problem is that many fast-lane tests
still encode Telegram graph/agents as the canonical runtime owner.

## Current Lane Contract

Local fast lanes:

- `make test` runs `tests/unit/` plus `tests/integration/test_graph_paths.py`
  with `-m "not legacy_api and not requires_extras and not slow"`.
- `make test-unit` runs `tests/unit/` with the same marker expression.
- `make test-contract` runs `tests/contract/` as static/no-Docker guardrails.

CI:

- Pull-request CI runs guardrails, Semgrep, lint, lockfile check, and Compose
  config. It does not run pytest.
- Nightly runs integration/smoke/baseline on GitHub-hosted Ubuntu and heavy
  tiers on the self-hosted runner.

Implication: tests that preserve the old core/Telegram dependency can block
the refactor locally even if PR CI stays green.

## Findings

### 1. Core unit tests contain the direct legacy runtime bridge

File: `tests/unit/core/test_assistant_entrypoint.py`

This file has two different responsibilities:

- stable core contract: `UserContext`, `CoreDependencies`, `CrmAction`,
  `AssistantResult`, `AssistantError`, import isolation, request IDs, product
  event shape;
- legacy runtime bridge: dependency-backed `run_assistant_request()` patches
  `telegram_bot.agents.rag_pipeline.rag_pipeline` and
  `telegram_bot.services.generate_response.generate_response`.

The core contract part should stay under `tests/unit/core/`.

The legacy runtime bridge part should move to `tests/unit/runtime/` or be
rewritten after the runtime facade lands. Keeping it in `tests/unit/core/`
will keep teaching future changes that core owns Telegram wiring.

Recommended classification: rewrite/move.

### 2. Existing runtime builder tests already expose the right seam

File: `tests/unit/runtime/graph/test_builder.py`

This file tests `src.runtime.graph.builder.resolve_pipeline_factory()` and
`RAG_GRAPH_FACTORY`. It intentionally resolves the default
`telegram_bot.graph.graph:build_graph` by string, not static import.

This is the correct pattern for the next runtime graph factory PR. It should be
extended, not replaced.

Recommended classification: keep and extend.

### 3. Graph behavior tests still use Telegram graph as canonical owner

Files:

- `tests/integration/test_graph_paths.py`
- `tests/unit/graph/test_graph.py`
- `tests/smoke/test_langgraph_smoke.py`

These tests import `telegram_bot.graph.graph.build_graph` and
`telegram_bot.graph.state.make_initial_state` directly. That is valid while
Telegram owns the graph implementation, but it will become wrong once the
canonical graph factory moves to `src.runtime`.

Recommended classification:

- keep behavior coverage;
- change canonical imports to `src.runtime` after the factory migration;
- keep one Telegram adapter/shim test that proves
  `telegram_bot.graph.graph.build_graph` re-exports or delegates correctly.

### 4. Core live E2E is the right product proof

Files:

- `tests/e2e/test_core_live_ingest_answer.py`
- `tests/e2e_core/live_harness.py`
- `tests/unit/e2e_core/test_live_harness.py`
- `tests/contract/test_core_live_gate_contract.py`
- `tests/contract/test_core_live_gate_placement_contract.py`

These tests are mostly aligned with the simplification target:

- `tests/e2e/test_core_live_ingest_answer.py` calls
  `src.core.assistant.run_assistant_request()`.
- `tests/e2e_core/live_harness.py` already uses `src.runtime.graph.config` and
  `src.runtime.services.qdrant`.
- core live gate contracts prevent Telegram, Langfuse, voice, Mini App, k8s,
  and trace validation from becoming required for the proof.

Gap: before PR #2378, the Makefile proof service startup is still broader
`local-up`; PR #2378 adds `core-up`/`core-down` and narrows this further.

Recommended classification: keep and strengthen.

### 5. Layering contract is useful but currently broad

File: `tests/contract/test_layering_no_telegram_bot_imports_contract.py`

This contract protects `src/` and `mini_app/` from new `telegram_bot` imports.
It is correct for future architecture. During the assistant decoupling wave it
needs a shrink-only allowlist for the known `src/core/assistant.py` bridge until
that bridge is moved to `src.runtime`.

PR #2378 adds this explicit guardrail and should be merged before the next
runtime refactor.

Recommended classification: keep and shrink.

### 6. Phase-1 shim contract is useful but not enough for the core wave

File: `tests/contract/test_runtime_phase1_modules_present_contract.py`

This contract locks already-completed moves:

- `telegram_bot/graph/state.py` -> `src/runtime/graph/state.py`
- `telegram_bot/graph/config.py` -> `src/runtime/graph/config.py`
- `telegram_bot/scoring.py` -> `src/scoring.py`
- `telegram_bot/phone_utils.py` -> `src/phone_utils.py`
- `telegram_bot/services/content_loader.py` -> `src/services/content_loader.py`
- `telegram_bot/observability.py` -> `src/observability.py`

It should not be overloaded with the next core assistant/factory work. Add a
new focused contract for the next phase instead.

Recommended classification: keep.

### 7. Many tests are Telegram adapter tests and should not be core blockers

Inventory found 85 test files referencing `telegram_bot.graph`,
`telegram_bot.agents`, or `telegram_bot.services.generate_response`.

These files are not bad. They become a problem only when they are used to prove
core ownership. Keep them as Telegram adapter, bot behavior, or legacy shim
coverage. Do not use them as the main acceptance signal for the core runtime
boundary.

Recommended classification: keep, but re-label mentally as adapter/runtime
coverage.

## Test Disposition Table

| File or group | Current role | Disposition | Next action |
|---|---|---|---|
| `tests/e2e/test_core_live_ingest_answer.py` | Live product proof | Keep | After PR #2378, run with `make core-up && make e2e-core-live && make core-down`. |
| `tests/e2e_core/live_harness.py` | Live proof harness | Keep | Keep dependencies on `src.runtime`; avoid adding Telegram imports. |
| `tests/unit/e2e_core/test_live_harness.py` | Harness unit coverage | Keep | Add coverage only for runtime/core proof helpers. |
| `tests/unit/core/test_assistant_entrypoint.py` dataclasses/import isolation/request ID sections | Core API contract | Keep | Split into `test_assistant_contract.py` before assistant decoupling. |
| `tests/unit/core/test_assistant_entrypoint.py` dependency-backed runtime section | Legacy bridge via Telegram | Move/rewrite | Move to runtime facade tests after `src.runtime` facade exists. |
| `tests/unit/runtime/graph/test_builder.py` | Runtime graph factory seam | Keep/extend | Add default `src.runtime` factory tests in graph factory PR. |
| `tests/unit/graph/test_graph.py` | Graph assembly behavior | Move canonical import | Switch to `src.runtime` canonical build path after factory migration. |
| `tests/integration/test_graph_paths.py` | Graph path behavior | Move canonical import | Switch canonical import to `src.runtime`; retain one Telegram shim test. |
| `tests/smoke/test_langgraph_smoke.py` | Graph smoke | Move canonical import | Use `src.runtime` for graph smoke; keep Telegram adapter smoke separately. |
| `tests/contract/test_layering_no_telegram_bot_imports_contract.py` | Reverse layering ratchet | Keep/shrink | Add then shrink allowlist; target zero `src/core` Telegram imports. |
| `tests/contract/test_runtime_phase1_modules_present_contract.py` | Completed phase-1 shim lock | Keep | Do not expand for assistant/factory; add new phase contract instead. |
| `tests/unit/agents/*` | Agent/domain behavior | Keep | Treat as Telegram/domain runtime coverage, not core proof. |
| `tests/unit/services/*` | Service behavior | Keep | Migrate individual services only when canonical ownership moves. |

## Backlog For Next PRs

### PR A: Test Guardrails Baseline

This is PR #2378.

Expected outcome:

- add `core-up`/`core-down`;
- add `tests/contract/test_core_monolith_boundaries_contract.py`;
- add `tests/contract/test_core_proof_compose_contract.py`;
- add `tests/unit/core/test_assistant_provider_contract.py`;
- allowlist the current `src/core/assistant.py` bridge explicitly;
- keep `local-up` as broader bot-dev runtime.

Merge this before changing canonical graph ownership.

### PR B: Split Core Assistant Tests

Create:

- `tests/unit/core/test_assistant_contract.py`
- `tests/unit/runtime/test_assistant_runtime_bridge.py`

Move from `tests/unit/core/test_assistant_entrypoint.py`:

- keep dataclass/import/request/result tests in
  `tests/unit/core/test_assistant_contract.py`;
- move dependency-backed Telegram bridge tests to runtime bridge test file;
- add a contract that no `tests/unit/core/**` file patches `telegram_bot.*`.

Do not change production behavior in this PR.

Verification:

```bash
uv run pytest tests/unit/core/ tests/unit/runtime/test_assistant_runtime_bridge.py -v
make test-contract
git diff --check
```

### PR C: Runtime Graph Factory Canonicalization

Modify:

- `src/runtime/graph/builder.py`
- likely add `src/runtime/graph/factory.py`
- `telegram_bot/graph/graph.py` as shim/delegator if needed
- `tests/unit/runtime/graph/test_builder.py`
- `tests/unit/graph/test_graph.py`
- `tests/integration/test_graph_paths.py`
- `tests/smoke/test_langgraph_smoke.py`

Expected outcome:

- canonical graph construction is reachable from `src.runtime`;
- `RAG_GRAPH_FACTORY` remains compatible;
- Telegram graph path remains adapter/shim-compatible;
- graph behavior tests import the canonical runtime path;
- one explicit Telegram shim test proves backward compatibility.

Verification:

```bash
uv run pytest tests/unit/runtime/graph/test_builder.py tests/unit/graph/test_graph.py -v
uv run pytest tests/integration/test_graph_paths.py -v
uv run pytest tests/smoke/test_langgraph_smoke.py -v
make test-contract
```

### PR D: Assistant Core Decoupling

Modify:

- `src/core/assistant.py`
- new or existing runtime facade under `src/runtime/`
- `tests/unit/core/test_assistant_contract.py`
- `tests/unit/runtime/test_assistant_runtime_bridge.py`
- `tests/e2e/test_core_live_ingest_answer.py` only if the public core API
  shape changes; avoid changing it otherwise.

Expected outcome:

- `src/core/assistant.py` no longer imports or dynamically imports
  `telegram_bot.*`;
- `tests/data/known_layering_violations.json` removes `src/core/assistant.py`;
- core result/CRM/HITL contract remains unchanged;
- `make e2e-core-live` still passes.

Verification:

```bash
uv run pytest tests/unit/core/ tests/unit/runtime/test_assistant_runtime_bridge.py -v
uv run pytest tests/e2e/test_core_live_ingest_answer.py -v -m "e2e and requires_services"
make test-contract
make core-up
make e2e-core-live
make core-down
```

## Delete Candidates

No immediate delete candidates were identified for this wave.

Reason: the risky tests are mostly useful behavior coverage with the wrong
canonical owner. They should be moved or rewritten after ownership moves, not
deleted preemptively.

Delete only after a follow-up PR proves one of these:

- the test checks behavior that no longer exists;
- the same behavior is covered by a more precise core/runtime test;
- the test exists only to preserve a deprecated Telegram implementation path.

## Risks If Audit Is Ignored

- `tests/unit/core/` will continue to patch Telegram internals and will block a
  clean core boundary.
- Graph tests will keep `telegram_bot.graph.graph.build_graph` as the canonical
  factory, making the runtime factory move look like a regression.
- Broad unit tests will continue to be interpreted as core proof even when they
  are really adapter/domain runtime coverage.
- Allowlists will grow instead of shrinking, making future boundary violations
  harder to see.

## Recommended Next Step

After PR #2378 is merged, implement PR B: split core assistant tests. It is the
lowest-risk cleanup because it changes test ownership only and prepares the
assistant decoupling without changing production behavior.
