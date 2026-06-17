# Shared: Required Superpowers per worker type

> Single source of truth for the Superpowers matrix. Referenced by `swarm-plan`,
> `swarm-launch`, and `swarm-pr-review-flow` instead of being restated in each
> (#2305 P2). Mirrors `.kiro/steering/swarm-worker-contract.md`.

| Worker type | Required Superpowers |
|---|---|
| read-only / secretary / intake / forensics / preflight | `verification-before-completion` (TDD/executing-plans skippable with `read_only_worker` rationale) |
| implementation (feature / refactor / behavior) | `executing-plans`, `test-driven-development`, `verification-before-completion` |
| bug-debug (bug / security / crash / regression) | implementation chain **plus** `systematic-debugging` |
| review-fix (PR feedback) | implementation chain **plus** `receiving-code-review` |
| subagent-orchestrator (independent slices) | implementation chain **plus** `subagent-driven-development` |

Notes:

- Do not require `using-superpowers`, `using-git-worktrees`, or
  `finishing-a-development-branch` for ordinary workers.
- Secretary/docs/intake/forensics/preflight may set
  `required_superpowers: none` only with a short `skipped_superpowers`
  rationale.
- The chain is sequential: do not start `executing-plans` before `writing-plans`
  is complete; do not claim completion before `verification-before-completion`
  ran fresh.
