# Skill Maintenance Guardrails

This document captures process bugs found during orchestrator review and turns them into reusable worker and reviewer rules.

Use it when updating:

- `docs/engineering/orchestrator-playbook.md`
- `docs/engineering/codex-web-prompt.md`
- `docs/engineering/gh-pr-review.md`
- PR templates or agent contract tests

---

## 1. Orchestrator responsibility

The orchestrator owns prompt and skill freshness.

After every worker or reviewer failure, the orchestrator must classify the failure:

```text
code bug | validation gap | PR process failure | prompt/skill failure | contract-test gap
```

If the failure could repeat, the orchestrator must create a process PR or include a copyable prompt-improvement block that updates the right worker/reviewer/orchestrator skill.

Do not hide these improvements inside unrelated runtime PRs. Process/control-plane changes belong in a separate process PR unless the user explicitly asked to include them.

---

## 2. Re-scoped issue source of truth

When an issue body is stale but later comments or audit docs re-scope the work, use the latest re-scope as the source of truth.

Before approving or assigning work for a re-scoped issue:

1. Read the issue body.
2. Read recent issue comments.
3. Read linked audit docs if referenced.
4. Classify old checklist items as `current`, `stale`, or `follow-up`.
5. Require the worker/PR body to state which interpretation was used.

A PR must not be accepted just because it satisfies an old issue body while ignoring newer issue comments.

---

## 3. Removed dependency / service reverse-search gate

When removing a dependency, service, environment variable, endpoint, or config file, workers and reviewers must run reverse searches before the PR is marked ready.

Minimum searches:

```bash
# Removed dependency
rg -n "import <dep>|from <dep>|<dep>\." .

# Removed service / endpoint / env / config
rg -n "<SERVICE_NAME>|<HOST>:<PORT>|<ENV_VAR>|<old config path>|<old health endpoint>" .
```

Block the PR if any of these remain:

- unconditional imports for a removed dependency;
- active runtime/default/test paths pointing at a removed service endpoint;
- docs claiming migration is complete while scripts/runbooks/tests still default to the removed surface;
- lockfile/dependency removal without matching import cleanup.

Allowed only with explicit documentation:

- legacy opt-in compatibility paths;
- historical docs that are clearly archived;
- optional extras that still declare the dependency they import.

---

## 4. New central shim coverage

When a worker introduces or changes a central compatibility shim, router, adapter, or facade, the PR must include direct unit tests for the shim itself, not only caller tests.

Coverage must prove:

- input translation into the downstream SDK/API contract;
- dropping or preserving wrapper-only kwargs intentionally;
- parsing/normalizing return values;
- failure propagation to caller fallback paths;
- at least one regression case for the bug that caused the shim.

---

## 5. PR body and handoff freshness

A PR touched by a reviewer or worker must not be reported as ready unless the PR body contains:

- duplicate PR preflight;
- changed files / scope;
- validation run on the current head;
- skipped checks with reasons;
- failed-check triage;
- follow-up issues for intentionally deferred work;
- risk / rollback;
- Agent Handoff with `Validated commit` equal to current head.

If the head changes after validation, validation is stale and must be rerun.
