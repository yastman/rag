***REMOVED*** Test Operator Skill Design

***REMOVED******REMOVED*** Context

This repository already has a meaningful local and nightly test split, but the operational contract is spread across several places:

- `/repo/Makefile` defines the main local entry points such as `test`, `test-unit`, `test-unit-loadscope`, `test-full`, and `test-store-durations`;
- `/repo/pyproject.toml` defines pytest defaults, markers, and the default `--dist=loadscope` addopt;
- `/repo/.github/workflows/ci.yml` runs unit tests in CI with `-n auto --dist=worksteal`;
- `/repo/.github/workflows/nightly-heavy.yml` runs the heavy tier with `-n auto --dist=loadscope`;
- `/repo/.test_durations` already exists, so duration-aware optimization is not hypothetical.

The repository is also explicitly multi-system: bot, mini app, ingestion, voice, retrieval, and runtime services all contribute tests. A test-automation skill for this repository cannot behave like a generic pytest helper. It must understand the repo's current contracts and choose the smallest safe change that improves the local feedback loop.

***REMOVED******REMOVED*** Problem

The desired skill is not just a "fix failing test" assistant and not just a "speed up pytest" assistant.
It must do both in one operator workflow:

- run the correct local test commands under native WSL;
- investigate and auto-fix failures in tests, fixtures, config, or production code;
- prefer SDK- or framework-native solutions before custom patches;
- optimize local parallelism based on measured behavior, not folklore;
- preserve a clean separation between fast local gates and nightly heavy suites.

Without that discipline, the skill would likely make one of three mistakes:

- stop at "tests are green" without improving the local loop;
- chase speed by switching schedulers blindly and destabilize test behavior;
- apply custom fixes where pytest, xdist, or existing project contracts already provide the right solution.

***REMOVED******REMOVED*** Goals

- Produce a repository-specific skill for `rag-fresh`, not a generic polyglot test skill.
- Treat native `WSL/Linux` as the supported local runtime contract.
- Auto-fix failing tests by finding the root cause before patching.
- Optimize local speed for the day-to-day developer loop.
- Keep nightly-heavy behavior explicit and separate from the fast local gate.
- Use SDK-first and framework-native solutions before custom code.
- Require measured verification before declaring improvement.

***REMOVED******REMOVED*** Non-Goals

- This design does not optimize Windows host execution outside WSL.
- This design does not make CI the primary optimization target.
- This design does not guarantee the fastest possible heavy-tier run on every machine.
- This design does not replace broader repo hygiene, release, or deployment workflows.
- This design does not authorize unrelated refactors under the label of test optimization.

***REMOVED******REMOVED*** Current-State Findings

***REMOVED******REMOVED******REMOVED*** Test Surface

- The repository currently contains `432` test files and `13` `conftest.py` files.
- The largest surface is `tests/unit/`, followed by integration, smoke, baseline, benchmark, chaos, load, contract, and e2e tiers.

***REMOVED******REMOVED******REMOVED*** Existing Day/Night Split

- The main local fast gate is centered on `make test-unit` and related `worksteal` targets.
- CI unit tests in `/repo/.github/workflows/ci.yml` also use `-n auto --dist=worksteal`.
- Nightly heavy tests in `/repo/.github/workflows/nightly-heavy.yml` use `-n auto --dist=loadscope` and target `requires_extras`, `load`, `chaos`, `e2e`, and `benchmark`.

***REMOVED******REMOVED******REMOVED*** Local Audit Results

The local audit was run in native WSL:

- runtime: `WSL2`, `Ubuntu-24.04`;
- CPU availability: `12` logical CPUs on the current machine.

Measured local results:

- `make test-unit` passed with `5606 passed, 17 skipped` in `66.13s` real on `--dist=worksteal`;
- a repeated `worksteal` run with durations enabled passed with the same `5606 passed, 17 skipped` in `53.82s` real;
- the slowest fast-gate test was `tests/unit/ingestion/test_qdrant_writer_behavior.py::TestUpsertChunksSyncEdgeCases::test_oversized_payload_skipped_with_error` at about `19.25s`;
- `make test-unit-loadscope` was not a safe faster substitute: it ran a broader unit set, took `830.54s` real, and failed one ingestion test on timeout.

***REMOVED******REMOVED******REMOVED*** Key Operational Insight

For this repository and this local machine, `loadscope` is not universally "better for local speed." The current evidence says:

- `worksteal` is the safer default for the local fast gate;
- `loadscope` may still be useful for specific fixture-heavy subsets or nightly-heavy suites;
- scheduler choice must be validated against both wall-clock speed and stability.

***REMOVED******REMOVED*** Recommended Approach

Build a repository-specific skill tentatively named `test-operator`.

The skill should operate as a combined:

- failure investigator;
- auto-fix operator;
- local test-performance tuner;
- pytest/xdist workflow normalizer.

This is better than a narrow debugging-only skill because the repository already has multiple runner strategies and test tiers. It is also better than a generic optimization skill because the correct answer depends on `rag-fresh` contracts such as `test-unit`, nightly-heavy markers, and WSL-native execution.

***REMOVED******REMOVED*** Skill Scope

The skill may change any repository surface directly involved in test correctness or local speed, including:

- `/repo/tests/**`;
- `/repo/**/conftest.py`;
- `/repo/Makefile`;
- `/repo/pyproject.toml`;
- `/repo/.github/workflows/*.yml`;
- production code when the real bug is outside the tests themselves.

The skill should prefer the smallest safe blast radius:

- first fix the failing test or broken fixture contract if that is the root cause;
- then fix runner selection, marker placement, or config drift if that is the root cause;
- only then widen into production-code changes when the test correctly exposes a real implementation bug.

***REMOVED******REMOVED*** Trigger Conditions

The skill should trigger for requests like:

- fix failing tests;
- make local tests faster;
- optimize parallel test execution;
- audit pytest setup;
- tune xdist, split, durations, markers, or fixture scopes;
- stabilize local WSL test runs.

The skill should not trigger for unrelated documentation-only or deployment-only tasks unless they directly affect the test workflow.

***REMOVED******REMOVED*** Operating Contract

***REMOVED******REMOVED******REMOVED*** Runtime Contract

The skill assumes:

- tests run inside native `WSL/Linux`;
- local commands should use repository-native tooling such as `uv run pytest` and `make`;
- Windows host Python, PowerShell-only commands, or host-path assumptions are out of scope unless the user explicitly asks for them.

***REMOVED******REMOVED******REMOVED*** Repository Contract

The skill must read before making changes:

- `/repo/README.md`;
- `/repo/AGENTS.md`;
- any nearer `AGENTS.override.md` for touched areas;
- `/repo/Makefile`;
- `/repo/pyproject.toml`;
- relevant workflow files;
- `/repo/docs/engineering/sdk-registry.md`.

***REMOVED******REMOVED*** Workflow

The skill should follow a strict workflow.

***REMOVED******REMOVED******REMOVED*** Phase 1: Preflight

- confirm the local runtime is native WSL/Linux;
- identify the requested target:
  - failing command,
  - local fast gate,
  - heavy/nightly tier,
  - or broader audit;
- inspect current test entry points and marker definitions;
- note whether `.test_durations` exists and whether it is likely stale.

***REMOVED******REMOVED******REMOVED*** Phase 2: Baseline Audit

- run the canonical local command before inventing a custom reproduction;
- capture:
  - pass/fail result,
  - real/user/sys time,
  - slowest tests,
  - skip profile,
  - scheduler and worker settings;
- map the relevant tier to day/local or nightly/heavy behavior.

***REMOVED******REMOVED******REMOVED*** Phase 3: Root Cause Investigation

Use the systematic-debugging rule set:

- read the failing output fully;
- reproduce consistently;
- identify whether the failure is in:
  - test code,
  - fixture scope or shared state,
  - runner configuration,
  - environment assumptions,
  - or production code;
- avoid speculative "performance fixes" before understanding why the current behavior fails.

***REMOVED******REMOVED******REMOVED*** Phase 4: SDK-First Research

Before custom fixes, the skill should check:

1. `/repo/docs/engineering/sdk-registry.md`;
2. current repository usage patterns;
3. MCP or official docs for version-sensitive pytest, xdist, split, or framework behavior;
4. custom implementation only when the above does not cover the need.

Typical SDK-first checks include:

- whether pytest markers or xdist grouping already solve the isolation problem;
- whether scheduler selection should use existing xdist behavior instead of custom orchestration;
- whether fixture scope, built-in pytest parametrization, or plugin-native options cover the need better than custom wrappers.

***REMOVED******REMOVED******REMOVED*** Phase 5: Auto-Fix

The skill may patch:

- broken tests;
- fixture scopes and isolation boundaries;
- xdist grouping;
- scheduler defaults;
- suite selection and marker hygiene;
- Make targets;
- workflow tier alignment;
- production code if the test failure is a real implementation bug.

The guiding rule is:

- fix the true source of failure or waste;
- do not stack multiple speculative changes in one step;
- avoid adding custom infrastructure when pytest or a project-native contract already solves the problem.

***REMOVED******REMOVED******REMOVED*** Phase 6: Optimization Pass

The skill should compare local strategies using measured runs. Candidate dimensions include:

- `--dist=worksteal` versus `--dist=loadscope`;
- `-n auto` versus a smaller worker count when contention is visible;
- fast gate subset versus broader unit selection;
- fixture-heavy subsets separated from the default fast gate;
- updating `.test_durations` when duration-aware logic is part of the optimization path.

The skill should treat scheduler changes as invalid if they:

- slow the local fast gate materially;
- cause new timeouts or shared-state failures;
- blur the boundary between daily local checks and nightly-heavy suites.

***REMOVED******REMOVED******REMOVED*** Phase 7: Verification

Before claiming success, the skill must rerun:

- the failing command or targeted suite;
- the canonical local fast gate if it was affected;
- any directly impacted optimization benchmark command.

The verification output must support both claims:

- correctness improved;
- local speed or stability improved, or at minimum did not regress for the intended path.

***REMOVED******REMOVED*** Decision Rules For Parallelization

The skill should use explicit decision rules rather than one-size-fits-all advice.

***REMOVED******REMOVED******REMOVED*** Default Local Fast Gate

Use the fastest verified stable strategy for the local developer loop.

Based on the audit captured in this design, the default local preference is:

- keep the fast gate on `worksteal` unless future measurements prove another default is better.

***REMOVED******REMOVED******REMOVED*** Fixture-Heavy Or Grouped Workloads

Use `loadscope` only when measurements show that fixture reuse outweighs the scheduling and timeout risks for that specific subset.

The skill should prefer creating a separate target for that subset over replacing the default fast gate blindly.

***REMOVED******REMOVED******REMOVED*** Worker Count

`-n auto` is a candidate default, not a law.

The skill may reduce worker count when:

- worker startup dominates the suite;
- contention or heavy serialization causes regressions;
- WSL resource behavior makes fewer workers faster in practice.

***REMOVED******REMOVED******REMOVED*** Shared-State Tests

When tests are parallel-safe only within a constrained grouping, prefer native controls such as:

- marker hygiene;
- `xdist_group`;
- fixture scope cleanup;
- tier isolation.

Do not solve test-order or global-state bugs by disabling useful parallelism across the whole repository unless the evidence leaves no better option.

***REMOVED******REMOVED*** Day Versus Night Policy

The skill should explicitly preserve the repository's two operational lanes:

***REMOVED******REMOVED******REMOVED*** Day / Local Lane

Purpose:
- fast, stable developer feedback on the most relevant local surfaces.

Properties:
- optimized for wall-clock speed;
- avoids dragging in heavy extras by default;
- should remain green and predictable under native WSL.

***REMOVED******REMOVED******REMOVED*** Night / Heavy Lane

Purpose:
- catch broader issues in extras-heavy, load, chaos, benchmark, and e2e surfaces.

Properties:
- allowed to be slower;
- may use a different scheduler if evidence supports it;
- should not redefine the local fast gate by accident.

If marker placement or workflow configuration causes drift between those lanes, fixing that drift is part of the skill's job.

***REMOVED******REMOVED*** Guardrails

- Never claim optimization without measured before/after evidence.
- Never prefer a custom workaround over a known pytest or plugin-native solution without justification.
- Never switch the default scheduler globally based on one subset.
- Never silently broaden the local fast gate while calling it an optimization.
- Never assume CI behavior is the same as local WSL behavior.
- Never stop at "green" if the user explicitly asked for speed and parallelization improvements too.

***REMOVED******REMOVED*** Success Criteria

The skill is done only when all relevant conditions are true:

- the target test command or suite is green;
- the chosen local execution strategy is verified under native WSL;
- day and night tiers remain intentionally separated;
- any scheduler, worker-count, or fixture-scope recommendation is backed by measurement;
- the final output explains:
  - what was failing or slow,
  - what was changed,
  - what local command is now recommended,
  - and what verification was run.

***REMOVED******REMOVED*** Expected Skill Outputs

For each task run, the skill should produce a concise operator report with:

- failing or slow surface summary;
- root cause;
- SDK-first findings;
- changes made;
- before/after timing when optimization was part of the task;
- any residual risks, such as heavy-tier surfaces not revalidated in the same run.

***REMOVED******REMOVED*** Implementation Notes

The implementation phase should keep the skill lean and procedural:

- the main `SKILL.md` should describe the workflow and decision rules;
- bundled references may hold repo-specific command maps and optimization heuristics;
- helper scripts are justified only when they remove repeated boilerplate or make measurements more deterministic.

The skill should be designed to cooperate with existing skills, especially:

- `systematic-debugging` for root-cause discipline;
- `verification-before-completion` for measured closeout;
- `sdk-research` for native-solution checks.

***REMOVED******REMOVED*** Recommendation

Proceed with a repository-specific `test-operator` skill that treats local WSL execution as first-class, keeps `worksteal` as the current default fast-gate assumption unless re-measured otherwise, and makes "green plus verified local optimization" the completion bar.
