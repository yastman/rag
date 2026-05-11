# Engineering Docs

Concise index for engineering process docs. These pages describe workflow, validation, triage, and process guidance; runtime and Docker facts stay in [`../../DOCKER.md`](../../DOCKER.md), local commands stay in [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md), and operational investigations start at [`../runbooks/README.md`](../runbooks/README.md).

## Active Workflow Docs

| Doc | Use When |
|---|---|
| [`test-writing-guide.md`](test-writing-guide.md) | Writing or changing tests, choosing markers, and selecting focused validation. |
| [`issue-triage.md`](issue-triage.md) | Classifying issue scope, risk, SDK coverage, and execution lane. |
| [`sdk-registry.md`](sdk-registry.md) | Checking SDK/framework ownership and preferred project patterns before code changes. |
| [`docs-maintenance.md`](docs-maintenance.md) | Updating docs, choosing canonical owners, and running docs verification. |
| [`swarm-context-budget.md`](swarm-context-budget.md) | Improving or reviewing swarm orchestration context budget and artifact-first evidence rules. |

## Historical Or Resolved Notes

| Doc | Status |
|---|---|
| [`dependency-upgrade-blockers-2026-04.md`](dependency-upgrade-blockers-2026-04.md) | Historical/resolved Langfuse v4 blocker note; do not use as the current dependency backlog. |
| [`swarm-process-improvements.md`](swarm-process-improvements.md) | Historical deploy-process improvement summary for issue #1244; use current workflows and scripts as source of truth. |

## Fast Search

```bash
rg -n "validation|test|triage|SDK|dependency|docs maintenance|swarm" docs/engineering/ docs/indexes/engineering-workflows.md
```
