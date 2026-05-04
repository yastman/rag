# Archived Workflows

## Why these workflows were archived

The workflows in `docs/archive/workflows/disabled/` were previously tracked under `.github/workflows.disabled/`. They were disabled because they reference stale branch names (`main`, `development`), outdated Python versions, or workflow patterns that are no longer aligned with the current CI/CD setup. Keeping them in the `.github/` tree created clutter and risked confusion with active GitHub Actions configuration.

## What active workflows remain

Active CI/CD workflows live under `.github/workflows/` and include:

- `ci.yml` — Lint, type check, and unit tests
- `nightly-heavy.yml` — Nightly heavy-weight test suite
- `publish-internal-images.yml` — Build and publish internal container images

## Archived disabled workflows

The following historical workflow files are preserved here for reference:

- `ci.yml.disabled` — Older CI configuration with baseline regression checks
- `deploy.yml` — Legacy deploy workflow (quick deploy + release deploy)
- `release-please.yml` — Release Please automation
- `release.yml` — Full release & deploy pipeline with staging deploy
- `smoke-load.yml` — Smoke routing and load tests
- `update-roadmap.yml` — Automated roadmap progress updater

None of these files are executed by GitHub Actions while they remain in this archive path.
