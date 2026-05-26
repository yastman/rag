---
inclusion: always
---

# Swarm Worker Pipeline Contract

Codifies #1937. Applies to every swarm worker (Kiro Web sub-agent,
`$tmux-swarm-orchestration` worker, manually-launched coding agent, etc.)
that touches this repo.

The contract has two halves:

1. **Required Superpowers per worker type** — pinned chains of skills the
   worker must run before claiming completion.
2. **Required worker-report fields** — schema acceptance tooling scans
   to verify the worker's claim against fresh evidence.

If a worker cannot honour both halves, route the work back through
`writing-plans` and rescope.

## Worker Types and Required Superpowers

| Worker type | Touches code | Required Superpowers (in order) |
|---|---|---|
| **read-only** preflight / secretary / inventory / audit | no | `using-git-worktrees`, `verification-before-completion` |
| **implementation** (feature, refactor, behavior change) | yes | `using-git-worktrees`, `writing-plans`, `executing-plans`, `test-driven-development`, `verification-before-completion` |
| **bug-debug** (bug, security, crash, regression) | yes | implementation chain **plus** `systematic-debugging` |
| **review-fix** (PR feedback, post-review iteration) | yes | implementation chain **plus** `receiving-code-review` |
| **subagent-orchestrator** (only when slices are independent) | yes | implementation chain **plus** `subagent-driven-development` |

Resolution: each Superpower listed above maps to a file under
`skills/superpowers/<name>.md` by file-stem. The chain is sequential —
do not start `executing-plans` before `writing-plans` is complete, do
not claim completion before `verification-before-completion` ran fresh.

Read-only workers are the only category allowed to skip TDD; they must
still produce verification evidence (e.g., the inventory query they ran)
through `verification-before-completion`.

## Worker Prompt Schema

A code-changing worker prompt MUST include a literal `Required Superpowers`
section listing the chain from the table above. Launchers (`-launch`) are
expected to reject or flag prompts that omit it.

```text
Required Superpowers:
- using-git-worktrees
- writing-plans
- executing-plans
- test-driven-development
- verification-before-completion
```

## Worker Report Schema

A worker report MUST include all of the following fields verbatim.
Acceptance tooling (`-acceptance`) scans the report for them; missing
fields are a hard failure.

| Field | Meaning |
|---|---|
| `superpowers_used` | The Superpowers actually executed during the run. Subset of `Required Superpowers`. |
| `skipped_superpowers` | Any required Superpower the worker chose to skip, with one-sentence justification per entry. Empty list if none. |
| `changed_files` | Repo-relative paths the worker touched. Empty list for read-only workers. |
| `tests_run` | Test files / pytest selectors the worker actually invoked, with pass/fail counts. |
| `verification_evidence` | Free-form summary linking changed behavior to fresh test runs, lint runs, runtime probes, or screenshots. |
| `evidence_commands` | Exact shell commands an acceptor can replay to reproduce `verification_evidence`. |

Example (abbreviated):

```yaml
superpowers_used: [using-git-worktrees, writing-plans, executing-plans,
                   test-driven-development, verification-before-completion]
skipped_superpowers: []
changed_files:
  - src/runtime/graph/builder.py
  - src/api/main.py
  - tests/unit/runtime/graph/test_builder.py
tests_run:
  - "tests/unit/runtime/graph/test_builder.py: 8 passed"
  - "tests/contract/: 1170 passed, 4 skipped, 3 xfailed"
verification_evidence: >
  Layering allowlist emptied; no static telegram_bot import remains under
  src/. Layering contract test passes with empty JSON.
evidence_commands:
  - "uv run --python 3.12 pytest tests/contract/ -q -n auto --dist=worksteal"
  - "uv run ruff check src/api/main.py src/runtime/graph/builder.py"
```

## Acceptance Gate

`-acceptance` must:

1. Confirm the report includes every field above.
2. Replay `evidence_commands` against the worker's branch and confirm
   the same outcome the worker claimed.
3. For implementation / bug-debug / review-fix workers, refuse to
   accept until `superpowers_used` is a superset of the required chain
   minus any line-itemised entry in `skipped_superpowers`.
4. Confirm `changed_files` matches the actual diff (no silent edits
   outside the reported paths).

Acceptance based on the worker's claim alone — without re-running
`evidence_commands` — is forbidden.

## Review Gate (P0 / security / destructive)

Code-changing workers in any of the following lanes MUST route through
a separate human or sub-agent review **before** final acceptance, even
if the report is fully populated:

- `P0` priority issues
- `security` label or content (auth, secrets, CSP, RBAC, signing,
  SQL injection, XSS, SSRF, path traversal, deserialization, etc.)
- `destructive` operations (delete data, drop tables, run migrations
  in-place, force-push, mass file rewrite, dependency-version pin
  changes that affect runtime)

The reviewer treats the worker as untrusted: read the diff end-to-end,
re-run `evidence_commands`, and run a focused security or invariant
probe before approving.

## Read-only Workers

Read-only / preflight / secretary / inventory / audit workers are
explicitly excluded from the TDD / `executing-plans` requirements
because they do not change behavior. They MUST still:

- list `superpowers_used` (typically `using-git-worktrees`,
  `verification-before-completion`);
- list any `skipped_superpowers` from the implementation chain with
  the literal justification `read_only_worker`;
- leave `changed_files` empty;
- provide `tests_run` (e.g. `none — read-only`) and
  `verification_evidence` describing what was inspected and why the
  conclusion is sound;
- provide `evidence_commands` so the conclusion can be reproduced.

## Pinned by

`tests/contract/test_swarm_worker_contract_steering_contract.py` —
fails if this file is moved, renamed, or loses any of the required
Superpowers, report fields, or lane distinctions.

## Cross-references

- `skills/superpowers/issue-skill-map.md` — per-issue Superpowers
  mapping.
- `.kiro/steering/agent-workflow.md` — top-level agent workflow.
- `docs/engineering/issue-triage.md` — lane decision model.
- `docs/engineering/test-writing-guide.md` — TDD conventions used by
  `test-driven-development` Superpower.
