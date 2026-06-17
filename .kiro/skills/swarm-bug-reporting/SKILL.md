---
name: swarm-bug-reporting
description: Use in subagent workers to report confirmed bugs as compact Markdown findings for the orchestrator's disposition. Add to the worker finish report or write a standalone bug report.
---

# Swarm Bug Reporting

Report confirmed bugs as Markdown, not prose-only chat.

## Report Shape

Add bugs to the worker finish report or write:

```text
logs/BUGS.{WORKER_NAME}.md
```

Use:

```markdown
# BUG_REPORT
status:
worker:
bug:
evidence:
impact:
recommended_disposition: fix_now|follow_up_issue|ask_user|not_a_bug
scope_fit:
reserved_files:
next:
```

## Rules

- Do not fix bugs outside reserved scope.
- Do not paste secrets or raw logs.
- For each confirmed bug, state whether it is in scope (fix now) or out of scope (follow-up issue).
- `recommended_disposition: fix_now` requires the bug is within `reserved_files`.
- `recommended_disposition: follow_up_issue` means create a GitHub issue after finishing current work.
- `recommended_disposition: ask_user` means the fix requires scope expansion or a decision.

## Completion Signal

After writing the report, output the completion line as the final message:

```
[DONE] {WORKER_NAME} {REPORT_FILE}
```

Replace with `[FAILED]` or `[BLOCKED]` as appropriate.
