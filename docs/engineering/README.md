# Engineering Docs

Concise index for engineering process docs. These pages describe workflow, validation, triage, and process guidance; runtime and Docker facts stay in [`../../DOCKER.md`](../../DOCKER.md), local commands stay in [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md), and operational investigations start at [`../runbooks/README.md`](../runbooks/README.md).

## Active Workflow Docs

| Doc | Use When |
|---|---|
| [`test-writing-guide.md`](test-writing-guide.md) | Writing or changing tests, choosing markers, and selecting focused validation. |
| [`issue-triage.md`](issue-triage.md) | Classifying issue scope, risk, SDK coverage, and execution lane. |
| [`sdk-registry.md`](sdk-registry.md) | Checking SDK/framework ownership and preferred project patterns before code changes. |
| [`docs-maintenance.md`](docs-maintenance.md) | Updating docs, choosing canonical owners, and running docs verification. |


## Historical Or Resolved Notes

No active historical notes at this time. See [`../archive/`](../archive/) for older artifacts.

## Fast Search

```bash
rg -n "validation|test|triage|SDK|dependency|docs maintenance" docs/engineering/ docs/indexes/engineering-workflows.md
```
