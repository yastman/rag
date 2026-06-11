# Agent Workflow Modes

Use this guide before assigning an agent to GitHub work. Pick exactly one mode
for the task and do not mix modes in the same assignment. If the task needs a
mode switch, finish the current mode with a clear handoff, then start a new task.

## Mode selection

| Request is about | Use mode | Do not also do |
|---|---|---|
| Existing open pull requests, merge queue, PR review, rebase, close/supersede decisions | [PR Coordinator](#pr-coordinator-mode) | New issue execution or architecture refactors |
| Implementing an accepted issue or backlog item | [Issue Executor](#issue-executor-mode) | Open-PR merge coordination or backlog-wide audit planning |
| Auditing current issues/PRs/docs and producing a plan | [Audit Planner](#audit-planner-mode) | Code implementation or merge decisions |

## Global rules

- Start every mode by syncing local knowledge with fresh `dev` refs.
- Keep the task scope to the selected mode only.
- Prefer focused validation first; expand to broader gates only when the changed
  surface requires it.
- Record skipped checks and why they were skipped.
- Do not create a new feature/refactor PR while operating in PR Coordinator mode.

## PR Coordinator Mode

Use this mode only when the task is about existing pull requests.

### Required flow

1. Fresh fetch / pull `dev`.
2. Get the list of open PRs.
3. For each PR under review:
   - check state and mergeability;
   - read the PR body;
   - inspect changed files;
   - inspect the diff;
   - check comments, reviews, and status checks;
   - decide one outcome: `merge`, `rebase`, `close`, `request changes`, or
     `superseded`.
4. Run only relevant checks for the PR type.
5. Do not create new feature or refactor changes.

### Forbidden in this mode

- Do not take new issues.
- Do not create new architecture PRs.
- Do not run the full issue execution pipeline.
- Do not run full `make test` for docs-only PRs by default.
- Do not create a separate worktree for each docs-only review unless the checkout
  is dirty or the PR needs edits.

### Test policy

| PR type | Checks |
|---|---|
| Docs-only PR | `git diff --check`; markdown/link checks when available |
| MyPy/type PR | targeted MyPy; `make check`; focused tests |
| Dependency PR | lockfile check; import/dependency contract tests; `make check`; `make test` only before final merge if runtime-wide |

### Merge policy

Merge only when all conditions are true:

- the PR is current relative to fresh `dev`;
- conflicts are resolved;
- relevant checks are green;
- the PR is not superseded by newer audit docs, dependency audits, or already
  merged implementation PRs.

## Issue Executor Mode

Use this mode only when implementing accepted issues or roadmap tasks.

### Required flow

1. Fresh fetch / pull `dev`.
2. Confirm the issue is still open, not superseded, and not already covered by an
   open PR.
3. Create one isolated worktree and branch for the issue or approved issue
   cluster.
4. Follow TDD:
   - add or update the failing focused test/contract first;
   - implement the smallest change that passes it;
   - run focused checks;
   - run broader checks required by the touched surface.
5. Commit the completed issue work on that branch.
6. Create exactly one PR for that issue or approved issue cluster.
7. Do not start another issue in the same worktree unless the plan explicitly
   defines the issues as one cluster.

### Forbidden in this mode

- Do not merge unrelated existing PRs.
- Do not close/supersede PRs without switching to PR Coordinator mode.
- Do not broaden the implementation beyond the accepted issue scope.
- Do not skip tests because a previous issue ran them in another worktree.

### Test policy

- Start with focused tests for the changed module.
- Add contract tests for architectural boundaries, dependency removal, or docs
  promises that must not regress.
- Use the local validation ladder from [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).
- Run `make test` when the issue affects runtime behavior, shared contracts, or
  a broad dependency surface.

## Audit Planner Mode

Use this mode only when the requested output is a plan, roadmap, audit, or
backlog analysis.

### Required flow

1. Fresh fetch / pull `dev`.
2. Collect current open issues, open PRs, and relevant docs/audits.
3. Separate open PR work from unstarted issue work.
4. Mark every item with one lane: `quick execution`, `plan needed`,
   `design first`, `external/manual`, or `close/no-op`.
5. Identify blockers, superseded items, and manual owner-controlled actions.
6. Produce a roadmap with dependency order and explicit next PR candidates.

### Forbidden in this mode

- Do not implement code changes.
- Do not merge PRs.
- Do not create feature branches for issues.
- Do not claim issues are completed unless the corresponding code/docs PR has
  already been merged or explicitly verified.

### Validation policy

- Validate generated plans with lightweight sanity checks, such as expected issue
  counts, required sections, and link/reference checks.
- Do not run full runtime test suites for docs-only audit output unless the docs
  change includes executable contracts or generated assets.
