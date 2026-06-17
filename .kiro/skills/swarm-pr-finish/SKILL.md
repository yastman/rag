---
name: swarm-pr-finish
description: Use when finishing assigned implementation work as a subagent worker. Runs pre-finish checks, writes a Markdown finish report. Allow commits, pushes, and PR updates only when explicitly assigned in the prompt.
---

# Swarm PR Finish

Finish with artifacts the orchestrator can read and verify directly.

## Pre-Finish Gates

Run and inspect:

```bash
git diff --stat
git diff --check
git diff --name-only
git status --porcelain --ignored
```

Confirm:
- Changed files are reserved/approved.
- Checks cover the changed behavior.
- No unrelated cleanup is included.
- Docs impact was handled or explicitly skipped.
- New bugs have disposition recommendations.

## Finish Report

Write one compact report to `logs/ISSUE_DONE.{WORKER_NAME}.md`.

Use `logs/BLOCKED.{WORKER_NAME}.md` for blocked work and `logs/FAILED.{WORKER_NAME}.md` for failed work.

Required shape:

```markdown
# WORKER_REPORT
status: done|failed|blocked
worker:
task:
issue:
worktree:
branch:
pr:
base:
head_sha:
pushed_sha:
summary:
reserved_files:
changed_files:
superpowers_used:
skipped_superpowers:
tests_run:
verification_evidence:
evidence_commands:
docs_impact:
blockers:
new_bugs:
risks:
next:
```

Command evidence is concise prose or short bullets. Do not paste raw logs.

## Discovery Contract

Use codeindexer MCP first for broad/semantic discovery and symbol tracing, `codegraph_explore` / `codegraph_node` for exact source-backed symbols, and `grep`/`glob` only for exact bytes, unindexed files, or outside-index paths.

## Safety

- Do not include secrets, production `.env`, tokens, DSNs with credentials, phone numbers, private URLs, or cloud credentials.
- If evidence contains secrets, summarize and cite the local artifact path.
- Do not switch branches, rebase, merge, push, stash, clean, delete branches, remove worktrees, or edit outside reserved files unless the prompt explicitly assigns that operation.
- Do not push.
- Do not create or update PRs unless the prompt explicitly assigns that operation.

## Completion Signal

After writing the report, output the completion line as the final message:

```
[{STATUS_TAG}] {WORKER_NAME} {REPORT_FILE}
```

Use `[DONE]`, `[FAILED]`, or `[BLOCKED]` to match report status.
