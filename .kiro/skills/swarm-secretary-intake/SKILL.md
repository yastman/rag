---
name: swarm-secretary-intake
description: Use for bounded issue, PR, queue, artifact, or planning intake as a research subagent worker. Produces compact Markdown reports for the orchestrator. Use when asked to summarize issues, audit artifacts, check dependencies, or prepare intake briefs.
---

# Swarm Secretary Intake

Prepare compact evidence for the orchestrator. Do not become the orchestrator.

## Default Contract

Produce one unique Markdown report and signal completion:

```text
Worker type: research
WORKER_NAME="secretary-worker-name"
REPORT_FILE="logs/INTAKE.${WORKER_NAME}.md"
[DONE] $WORKER_NAME $REPORT_FILE
```

Use task worker types: `research`, `issue-audit`, `artifact-check`, `dependency-verify`.

## Scope

**Allowed:**
- Bounded local reads requested by the prompt.
- Bounded `gh issue` / `gh pr` metadata commands requested by the prompt.
- Artifact validation requested by the prompt.
- Drafting unique Markdown reports or optional next-worker prompt drafts.

**Forbidden:**
- Launching subagents or workers.
- Merging PRs.
- Altering issues, labels, milestones, or comments.
- Editing product files unless the prompt explicitly reserves them.
- Reading broad logs, archived sessions, or unrelated worktrees.
- Printing secrets, production `.env`, tokens, private URLs, or raw secret-bearing evidence.

## Evidence Budget

- Prefer `gh ... --json ... --jq ...` projections over full JSON or raw bodies.
- For issue/PR lists return compact fields only: number, title, state, labels, author, updatedAt, milestone, assignees, URL.
- Do not fetch bodies, comments, reviews, logs, or diffs unless the prompt names them.
- For repo/code discovery use codeindexer first (`search_code`, `find_references`), then `codegraph_explore` for exact symbols, then `grep`/`glob` only for exact fallback.

## Report Shape — Issue/PR/Queue Planning

```markdown
# INTAKE_BRIEF
status:
worker:
confidence:
task_kind:
summary:
top_facts:
recommended_order:
parallel_candidates:
blockers_or_needs_user:
risks:
focused_checks:
evidence_commands:
next:
```

## Report Shape — Artifact Check

```markdown
# ARTIFACT_CHECK
status:
worker:
confidence:
artifact:
summary:
findings:
risks:
evidence_commands:
next:
```

Keep reports compact, usually under 80 lines.

## Completion Signal

After the report file is written, output the completion line as the final message:

```
[DONE] {WORKER_NAME} {REPORT_FILE}
```

Replace `[DONE]` with `[FAILED]` or `[BLOCKED]` to match the report status.
