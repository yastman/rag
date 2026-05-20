***REMOVED*** Skill: using-git-worktrees

Use when starting implementation for any issue.

Required workflow:

1. Create a dedicated git worktree/branch for the issue.
2. Prefer `.worktrees/` when present; verify it is ignored before use.
3. Run project setup if needed.
4. Run a focused baseline verification command before changes.
5. Record the worktree path, branch, baseline command, and result in the issue
   or PR.

Do not implement directly in the main working tree unless the issue is
explicitly documentation-only and the operator approves skipping isolation.
