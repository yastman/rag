# Orchestrator Finish Protocol

## Purpose

This protocol defines the end state for orchestrated work in `yastman/rag`.

Worker handoff is not the final finish for implementation work. A task is finished only after the accepted pull request is merged into `dev`, linked issue state is verified, and safe cleanup instructions are recorded or performed.

Use this together with [`orchestrator-playbook.md`](orchestrator-playbook.md) and [`repo-hygiene-runbook.md`](repo-hygiene-runbook.md).

## Ownership

- Implementation workers create/update scoped PRs and stop at handoff unless explicitly told otherwise.
- The orchestrator or human merger makes the merge decision.
- The merger owns the final `dev` merge, post-merge verification, and cleanup handoff.

Do not weaken the worker rule: workers must not merge unless explicitly instructed.

## Finish State

For an implementation PR, the normal finish state is:

1. The PR is accepted by the orchestrator or human owner.
2. The PR is merged into `dev` using merge commit strategy.
3. The merge result is verified.
4. Linked implementation issues are closed as completed when `Fixes` / `Closes` applies.
5. Coordination or launch issues remain open unless the orchestrator explicitly closes them.
6. Local worktrees and branches are cleaned up only when safe.

Audit-only or no-code closeout work may finish with an evidence comment instead of a PR, but the comment must state why no PR is needed and what can be closed manually.

## Pre-Merge Gate

Before merging an accepted PR, verify:

```text
- PR is open and not draft, unless intentionally merging a draft is explicitly approved.
- PR base is `dev`.
- Current PR head SHA equals the validated commit from the handoff.
- Required GitHub checks are visible and green.
- `statusCheckRollup` is not empty, or the equivalent workflow runs were verified.
- PR is mergeable.
- Changed files match issue scope.
- No unresolved process/workflow/control-plane contamination exists unless the PR is a process PR.
- Focused validation passed, or skipped/baseline checks are documented with reasons.
- No security uncertainty remains.
```

If the PR head changed after validation, validation is stale. Re-run or request re-run of the relevant checks before merge.

## Merge Command / Strategy

Use merge commit strategy unless the user explicitly instructs otherwise.

When using GitHub tooling, pass the expected head SHA so GitHub rejects the merge if the branch moved between verification and merge.

Never merge into `main` unless explicitly instructed.

## Post-Merge Verification

After merge, verify and report:

```text
- PR state is closed and merged.
- Merge commit SHA.
- Base branch was `dev`.
- Linked issue state for every `Fixes` / `Closes` issue.
- Coordination / launch issue state, if any.
- Any no-code closeout issues that still need manual closure.
```

If a linked issue did not close automatically, comment with the merge evidence and close it manually only when the orchestrator/human has accepted that outcome.

## Cleanup Protocol

After a PR is merged, clean up only safe local state.

Recommended local sequence:

```bash
git fetch origin --prune
make git-hygiene
```

For a project-local worktree created for the merged branch:

```bash
git worktree list --porcelain
git status --short <worktree-path>
git worktree remove <worktree-path>
```

Remove a local branch only after confirming it is merged into `dev` and is not checked out in any worktree:

```bash
git branch --merged origin/dev
git branch -d <branch>
```

Delete the remote head branch only when it is not used by a stacked PR, follow-up PR, or active worker:

```bash
git push origin --delete <branch>
```

Never force-remove dirty worktrees or branches with unpushed commits as part of routine finish. If cleanup is unsafe or local checkout access is unavailable, record cleanup as skipped and name the branch/worktree for the operator.

## Copy-Paste Cleanup Prompt

Use this prompt after an implementation PR is merged or when a worker reports final handoff with local checkout access.

```text
Clean up after the completed PR, but only safe local state.

Context:
- Repo: `yastman/rag`.
- Merged PR: #<PR>.
- Merged branch: `<branch>`.
- Merge commit: `<sha>`.
- Base branch: `dev`.

Rules:
- Do not delete dirty worktrees.
- Do not delete branches with unpushed commits.
- Do not delete branches checked out in any worktree.
- Do not delete a remote branch if it is used by a stacked PR, follow-up PR, or active worker.
- Do not touch unrelated local branches or worktrees.

Tasks:
1. Run `git fetch origin --prune`.
2. Run `git worktree list --porcelain` and identify any worktree for `<branch>`.
3. If a worktree for `<branch>` exists, run `git status --short <worktree-path>`.
4. If that worktree is clean, remove it with `git worktree remove <worktree-path>`.
5. Confirm `<branch>` is merged into `origin/dev` with `git branch --merged origin/dev` or equivalent.
6. If the local branch is merged and not checked out anywhere, delete it with `git branch -d <branch>`.
7. Check whether the remote branch is still needed by any open PR or stacked work.
8. If safe, delete the remote branch with `git push origin --delete <branch>`.
9. Run `make git-hygiene` or document why it is unavailable.

Report:
- Worktree: removed / skipped with reason / not found.
- Local branch: deleted / skipped with reason / not found.
- Remote branch: deleted / skipped with reason / not found.
- Remaining manual cleanup: none / details.
```

If local checkout access is unavailable, do not pretend cleanup happened. Report the exact branch and worktree path, if known, for the operator.

## Handoff Wording

Final orchestrator handoff should include:

```text
Status:
- PR #<n> merged into `dev`.
- Merge commit: <sha>.
- Linked issue(s): <closed/open/manual action>.
- Coordination issue: <preserved/closed with reason>.

Cleanup:
- Local worktree: <removed/skipped/not available>.
- Local branch: <deleted/skipped/not available>.
- Remote branch: <deleted/skipped/not available>.
- Remaining manual cleanup: <none/details>.
```
