# governance/

Model governance and registry utilities.

## Ownership

- Reserved home for future model governance and registry source code.
- Repo-level governance decisions currently live in canonical docs, not this empty package.

## Files

This directory is reserved for governance utilities. Currently no source files are present; governance workflows are documented at the repo level.

## Boundaries

- Do not place architecture decision records here; use [`ADRS.md`](ADRS.md).
- Do not place evaluation runners here; use [`../src/evaluation/`](../src/evaluation/).
- Add source-level checks only when source files are added.

## Focused checks

No dedicated source tests are required while this directory has no source files. For README-only edits:

```bash
make docs-check
git diff --check -- docs/governance.md
```

## Related

- [`ADRS.md`](ADRS.md) — Architecture decision records
- [`../src/evaluation/`](../src/evaluation/) — A/B testing and experiment tracking
