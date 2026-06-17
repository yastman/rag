# .kiro/skills_reference/

This directory is the **install target for reference-only upstream skills**,
populated by `scripts/install_ready_skills.sh`.

It is intentionally separate from `.kiro/skills/` (the active skills):

| Directory | Purpose |
|---|---|
| `.kiro/skills/` | Active skills — loaded and activated by Kiro workers |
| `.kiro/skills_reference/` | Reference-only upstream copies — read context, NOT activated |

## Why it exists

`install_ready_skills.sh` pulls four skills from
[obra/superpowers](https://github.com/obra/superpowers) that are used for
**orchestrator reading context** (`using-superpowers`, `executing-plans`,
`dispatching-parallel-agents`, `subagent-driven-development`) but should not
be activated in worker sessions. They live here to stay out of the active
`.kiro/skills/` tree while remaining accessible as reference.

## Kiro-only note

On a Kiro-only deployment none of these are needed at runtime — the active
`.kiro/skills/` copies are the canonical source. To prune:

1. Delete this directory.
2. Remove the `REFERENCE_OBRA` block from `scripts/install_ready_skills.sh`.
3. Remove the `reference_only` field from `scripts/list_installed_skills.sh`.
