---
name: swarm-review-fix
description: Use in the orchestrator PR review and review-fix swarm workers to report blockers, fix only named PR blockers on the same branch, and return Markdown reports by default.
---

# Swarm Review And Review-Fix

## PR Review Workers

Read-only review workers inspect the assigned PR/head SHA and write:

```text
logs/PR_REVIEW.<worker>.md
```

Required sections:

- `status`
- `pr`
- `head_sha`
- `review_decision`: clean | blockers | escalate
- `blockers`
- `new_bugs`
- `evidence_commands`
- `next`

They must not edit, commit, push, merge, delete branches, or clean worktrees.

For repo/code discovery, follow `shared/indexed-tool-contract.md` (Code Indexer
first, CodeGraph for exact source-backed symbols, `rg`/`find` fallback only;
native freshness via `codeindexer jobs` / `doctor` / `doctor --fix`, no custom
git hooks).

## Review-Fix Workers

Review-fix workers fix only named blockers on the same PR branch. They write:

```text
logs/REVIEW_FIX.<worker>.md
```

Required sections:

- `status`
- `pr`
- `head_sha`
- `fixed_blockers`
- `changed_files`
- `commands`
- `remaining_blockers`
- `new_bugs`
- `next`

The orchestrator verifies diff, PR metadata, and focused checks directly. Worker Markdown
is evidence, not proof.

For `rag-fresh`, run Python validation through the existing root `.venv` when
available:

```bash
UV_PROJECT_ENVIRONMENT=/home/user/projects/rag-fresh/.venv uv run --no-sync ...
```

Do not create a new Python 3.14 environment, run `uv sync`, upgrade dependency
groups, or build heavy packages such as `grpcio` from source during review-fix
unless dependency installation is the named blocker. If the reusable environment
is unavailable, report the check as blocked/skipped.
