---
inclusion: always
---

# Agent Workflow Steering

Follow the repo-local agent workflow in `skills/superpowers/` before working on
GitHub issues.

Required references:

- `skills/superpowers/README.md`
- `skills/superpowers/issue-skill-map.md`
- `AGENTS.md`
- `docs/README.md`
- `docs/engineering/test-writing-guide.md`
- `docs/LOCAL-DEVELOPMENT.md`

For GitHub issue tasks:

1. Identify the issue number.
2. Read `skills/superpowers/issue-skill-map.md` and load the required skills.
3. Create isolated work in a dedicated branch/worktree or Kiro sandbox.
4. Use test-first workflow for bug, feature, refactor, and behavior changes.
5. Do not use production, secrets, SSH, cloud credentials, or live CRM writes
   unless the issue explicitly approves it.
6. Before opening a PR or claiming completion, include fresh verification
   evidence and list skipped checks.

When the issue lacks acceptance criteria, ask for clarification or add a short
plan before implementation.
