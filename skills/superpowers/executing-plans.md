***REMOVED*** Skill: executing-plans

Use when executing an approved plan in one session.

Required workflow:

1. Follow the plan task by task.
2. Keep each step small and independently checkable.
3. Run the plan's verification command after each task or slice.
4. Stop on failed verification and fix before continuing.
5. Report completed tasks, skipped checks, and remaining risks in the PR or
   issue.

Prefer this over ad hoc implementation when the issue has several steps but does
not need parallel workers.
