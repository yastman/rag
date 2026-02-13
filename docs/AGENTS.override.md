# AGENTS.override.md

## Scope
- Applies to `docs/**`.
- Governs documentation structure and maintenance.

## Local Rules
- Keep source-of-truth docs current and avoid contradictory duplicates.
- Prefer updating existing canonical docs over adding new top-level files.
- Put long historical material into `docs/archive/` or dated plan files.
- Use `CLAUDE.md` and the paths it references as the primary source set when reconciling documentation.

## Documentation Strategy
- Canonical operational docs:
  - `docs/PROJECT_STACK.md`
  - `docs/PIPELINE_OVERVIEW.md`
  - `docs/LOCAL-DEVELOPMENT.md`
  - `docs/QDRANT_STACK.md`
  - `docs/INGESTION.md`
  - `docs/ALERTING.md`
- Agent-facing runbooks:
  - `docs/agent-rules/*.md`

## Guardrails
- Do not invent commands; verify against `Makefile` or runnable CLIs.
- Use explicit dates in dated reports/plans.

## References
- `CLAUDE.md`
- `docs/agent-rules/workflow.md`
- `docs/agent-rules/project-analysis.md`
