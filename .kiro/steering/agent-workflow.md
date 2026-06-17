---
inclusion: always
---

# Agent Workflow Steering

Follow the repo-local skills in `.kiro/skills/` before working on GitHub issues.

Required references:

- `.kiro/skills/README.md`
- `.kiro/steering/swarm-worker-contract.md` (Required Superpowers per worker type)
- `AGENTS.md`
- `docs/README.md`
- `docs/engineering/test-writing-guide.md`
- `docs/LOCAL-DEVELOPMENT.md`

For GitHub issue tasks:

1. Identify the issue number.
2. Select the required skills for the work from the Superpowers matrix in
   `.kiro/steering/swarm-worker-contract.md` (or `.kiro/skills/shared/superpowers-map.md`),
   and load them. In the swarm pipeline, `swarm-plan` assigns
   `required_superpowers` per worker.
3. Create isolated work in a dedicated branch/worktree or Kiro sandbox.
4. Use test-first workflow for bug, feature, refactor, and behavior changes.
5. Do not use production, secrets, SSH, cloud credentials, or live CRM writes
   unless the issue explicitly approves it.
6. Before opening a PR or claiming completion, include fresh verification
   evidence and list skipped checks.

When the issue lacks acceptance criteria, ask for clarification or add a short
plan before implementation.
