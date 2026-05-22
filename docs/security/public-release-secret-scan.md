# Public release secret scan policy

See also: [no-patch-dependency-alerts.md](no-patch-dependency-alerts.md) —
exposure assessment for open Dependabot alerts without upstream patches.

This repository history was rewritten in an isolated clone for P0 public-release
readiness. Do not run destructive history commands in the primary working copy.

## Required pre-publish checks

Run from the rewritten clone before publishing rewritten history:

```bash
./docs/security/verification-commands.sh post
trufflehog git file://"$PWD" --json --no-update --no-verification
trufflehog filesystem "$PWD" --json --no-update --no-verification
git fsck --full
git remote -v
```

The `trufflehog` JSON output may contain detected values. Store it only in a
temporary file, summarize detector/file counts, then remove the raw JSON.

## Accepted false positives

The post-rewrite `trufflehog` findings are expected to be:

- `Postgres`: placeholder connection strings in examples, docs, test fixtures,
  and local-development templates.
- `SentryToken`: SHA256 package hashes for `sentry-sdk` entries in `uv.lock`.

These are unverified scanner hits, not live credentials. Do not suppress these
detectors globally unless the release process has a separate review for
connection strings and lockfile hashes.

## Noise-reduced local scan

`trufflehog` supports `--exclude-paths`, not `.trufflehogignore`, in the
installed version used for this cleanup. The file
`docs/security/trufflehog-exclude-paths.txt` is for local review only. It
excludes known false-positive paths and should not be treated as proof that the
repository is release-ready.

## Publish gates

Before pushing rewritten history:

- provider-side API key rotation has been handled;
- targeted history checks are zero;
- `git fsck --full` is clean;
- raw scanner output has been removed from disk;
- collaborators know that history rewrite invalidates old clones, forks, and
  pull requests;
- the destination remote is explicit and approved.
