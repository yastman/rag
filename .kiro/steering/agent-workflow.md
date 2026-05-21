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
3. **Per-issue git worktree (mandatory).**
   Each issue gets its own worktree under `../wt-<issue>-<slug>/` branched off
   `dev`. Never commit to `main`/`dev` directly. Never reuse a worktree across
   unrelated issues. Example:

   ```bash
   git fetch origin dev
   git worktree add -b kiro/<issue>-<slug> ../wt-<issue>-<slug> origin/dev
   ```

4. **TDD is the default flow.**
   Red → green → refactor for every bug, feature, refactor, or behavior change:
   1. Write a failing test that pins the missing/wrong behavior. Run it; confirm
      it fails for the expected reason.
   2. Make the smallest change that turns it green.
   3. Refactor with tests still green; rerun the focused test set after every
      step. Commit the failing test separately from the fix when scope allows,
      so the diff records the contract.
   Skip TDD only for trivial doc/config moves with no behavior change, and
   record that decision in the PR body.

5. **SDK-first via Context7.**
   Before reimplementing anything that an SDK already provides, query Context7
   (`resolve-library-id` then `query-docs`) for the relevant library. Cite the
   library ID and the specific behavior in the PR body. Custom code is allowed
   only when the SDK lacks the capability, and that gap must be named.

6. Do not use production, secrets, SSH, cloud credentials, or live CRM writes
   unless the issue explicitly approves it. Default verification scope is
   `verify:repo-only` (lint + focused unit tests + relevant contract tests).

7. **PR + cleanup.**
   - Push the branch via the sandbox push tool, open the PR against `dev`,
     reference the issue with `Fixes #N`.
   - In the PR body include: TDD summary (which test was added first), Context7
     library IDs consulted, full verification commands and their results, and
     any skipped checks with justification.
   - After the PR is created, remove the worktree to free disk and avoid stale
     state:

     ```bash
     git worktree remove ../wt-<issue>-<slug>
     git worktree prune
     ```

     Keep the remote branch until merge; only the local worktree is removed.

When the issue lacks acceptance criteria, ask for clarification or add a short
plan before implementation. Do not start coding on `manual-control` or
`kiro-plan-only` issues without an approved plan in the issue thread.
