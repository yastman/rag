# Issue #3255 Archived `mini_app` Ruff Path Specification

## Outcome

The Ubuntu `Lint` job runs Ruff only against directories that still exist and matches the
authoritative `Makefile` `LINT_PATHS` set.

## Evidence

The repository no longer contains a top-level `mini_app/` directory. The local lint path list
already excludes it, but both Ruff commands in `.github/workflows/ci.yml` still include it. Ruff
therefore exits with `E902 No such file or directory` before evaluating a candidate change.

## Contract

- Remove `mini_app/` from both CI Ruff commands.
- Keep the command flags and the remaining path order unchanged.
- Add a focused contract that derives the expected path list from `Makefile` and checks both CI
  Ruff commands against it.
- Do not add a GitHub pytest job or change any other workflow behavior.

## Acceptance

The focused contract fails on the current `dev` workflow and passes after the two-line repair.
The exact Ruff check command exits successfully; the format command reaches the live path set
instead of failing on a missing directory. Deterministic Ruff versioning and the resulting
format-only drift are owned by follow-up #3256.

## Rollback

Revert the issue commit; no runtime, schema, or data state is involved.
