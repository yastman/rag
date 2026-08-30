# Issue #3256 Hosted Ruff Version Authority Specification

## Outcome

The hosted lint job executes the exact Ruff version recorded in `uv.lock`, so a fresh CI runner and
the repository's local quality environment apply the same formatting semantics.

## Evidence

After #3255 removed the nonexistent `mini_app/` path, floating `uvx ruff` resolved Ruff 0.16.5 and
reported new Markdown formatting drift. `uv.lock` records Ruff 0.15.20, which reports the complete
live path set formatted. The hosted command currently ignores that lockfile authority.

## Contract

- Invoke both hosted Ruff steps through `uvx --from ruff==<locked-version> ruff`.
- Derive `<locked-version>` from the unique `ruff` package entry in `uv.lock` in the existing
  local-gate contract.
- Preserve both step names, flags, and the ordered `Makefile` `LINT_PATHS` set.
- Do not reformat files, add dependencies, or modify other workflow jobs.

## Acceptance

The extended contract is RED against floating `uvx ruff`, GREEN after the two-line pin, and rejects
any version differing from `uv.lock`. Both exact pinned commands pass, and the hosted Ubuntu Lint
job is green.

## Rollback

Revert the issue commit. No runtime, dependency graph, or data state changes.
