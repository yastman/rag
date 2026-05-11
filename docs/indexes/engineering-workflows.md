# Engineering Workflows Index

Task-oriented entrypoint for engineering process docs. Use this when the request is about how to work, validate, triage, update dependencies, maintain docs, or coordinate swarm/process work. Route to the owning doc instead of copying its rules here.

## Start Here

- **Engineering folder index**: [`../engineering/README.md`](../engineering/README.md)
- **Local setup and validation ladder**: [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md)
- **Docs maintenance rules**: [`../engineering/docs-maintenance.md`](../engineering/docs-maintenance.md)

## Common Tasks

| Task | Start With | Then Check |
|---|---|---|
| Testing and validation | [`../engineering/test-writing-guide.md`](../engineering/test-writing-guide.md) | [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md), `Makefile`, `pyproject.toml` |
| Issue triage | [`../engineering/issue-triage.md`](../engineering/issue-triage.md) | Current issue, nearest folder `README.md`, nearest `AGENTS.override.md` |
| SDK/framework lookup | [`../engineering/sdk-registry.md`](../engineering/sdk-registry.md) | Current code usage, Context7 or official docs for version-sensitive behavior |
| Dependency updates | Dependency update skill when available; otherwise `Makefile` uv targets and package manifests | [`../engineering/dependency-upgrade-blockers-2026-04.md`](../engineering/dependency-upgrade-blockers-2026-04.md) for historical Langfuse blocker context only |
| Docs maintenance | [`../engineering/docs-maintenance.md`](../engineering/docs-maintenance.md) | [`../README.md`](../README.md), [`README.md`](README.md), nearest folder `README.md` |
| Swarm process docs | [`../engineering/swarm-context-budget.md`](../engineering/swarm-context-budget.md) | [`../engineering/swarm-process-improvements.md`](../engineering/swarm-process-improvements.md), active swarm plans under [`../superpowers/plans/`](../superpowers/plans/) |

## Fast Search

```bash
# Active engineering workflow docs
rg -n "validation|test-writing|issue triage|SDK|dependency|docs maintenance|swarm|process" docs/engineering/ docs/indexes/

# Current command and dependency surfaces
rg -n "uv sync|uv lock|pytest|make check|make test|dependency|renovate" Makefile pyproject.toml .github docs/engineering/

# SDK lookup starts with the registry, then current code
rg -n "context7_id|triggers|gotchas|patterns" docs/engineering/sdk-registry.md
```

## Ownership Notes

- Keep command ladders in [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).
- Keep test-writing rules in [`../engineering/test-writing-guide.md`](../engineering/test-writing-guide.md).
- Keep SDK/framework lookup rules in [`../engineering/sdk-registry.md`](../engineering/sdk-registry.md).
- Keep docs maintenance policy in [`../engineering/docs-maintenance.md`](../engineering/docs-maintenance.md).
- Keep Docker/runtime service truth in [`../../DOCKER.md`](../../DOCKER.md).
