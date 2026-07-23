# Worktree recovery evidence — 2026-07-23

Scope: recovery evidence at `C:/Dev/projects-wsl-migrated-2026-07-13/rag-fresh-recovery-20260723` and read-only Git inspection. This record does **not** reconcile, delete, reset, stash, or otherwise mutate preserved user worktrees.

## Baseline and candidate

- R0 phase worktree: `C:/Dev/projects-wsl-migrated-2026-07-13/rag-fresh-phase-f046fa9ed53f`; branch `phase/phase_f046fa9ed53f`; baseline `3c55aed272d8888df1e5c0a60f0010243eb80984` (`origin/dev`); clean before this manifest.
- Candidate: the `phase/phase_f046fa9ed53f` commit containing this manifest. It is intentionally not self-referenced by SHA here.

## Worktree dispositions

| Worktree | Branch / HEAD | Observed status | Disposition |
| --- | --- | --- | --- |
| Canonical `C:/Dev/projects-wsl-migrated-2026-07-13/rag-fresh` | `scoring-noop-contract-3190` / `9a9c2f8ce6ccfe364715260f824fb5234dc9d9f4` | Equal to repaired upstream `origin/scoring-noop-contract-3190`; 48 tracked dirty entries; nested Genesis excluded from untracked backup | **Decision: KEEP.** Restore pointer: `canonical/RESTORE.txt`; tracked delta: `canonical/unstaged.diff`; stash view: `canonical/stash_0.patch`. |
| Genesis `C:/Dev/projects-wsl-migrated-2026-07-13/rag-fresh/..rag-fresh-genesis-agents` | `chore/genesis-agents` / `ba00dda12fe4d006130399712c65f56e880abe5d` | Clean; no unique commits versus `origin/dev` (which is one commit ahead) | **Inference: SUPERSEDED; retain pending owner decision.** |
| Hosted-CI `C:/Dev/projects-wsl-migrated-2026-07-13/rag-fresh-ci-baseline-fix` | `fix/hosted-ci-baseline-20260722` / `b78be3b36ea48bd67704544ff948d401af179d7e` | Clean; exact remote twin; five genuinely unique patch-ids versus `origin/dev` | **Decision: KEEP.** Upstream repaired to `origin/fix/hosted-ci-baseline-20260722`. |
| p30-clean `C:/Dev/projects-wsl-migrated-2026-07-13/rag-fresh-p30-clean` | `fix/windows-native-development-clean-20260722` / `e1c8cc533533f748eb5912c0c96f147fdde5bf70` | `+3/-87` versus `origin/dev`; 21 staged, 7 unstaged, 2 untracked | **Decision: KEEP.** Restore pointer: `p30-clean/RESTORE-NOTE.txt`; bundle: `p30-clean/branch.bundle`. |
| p30-final `C:/Dev/projects-wsl-migrated-2026-07-13/rag-fresh-p30-final` | `fix/windows-p30-final-20260723` / `ba00dda12fe4d006130399712c65f56e880abe5d` | Four unstaged, two untracked; no unique commits versus `origin/dev` | **Inference: SUPERSEDED after recovery; retain pending owner decision.** Restore pointer: `p30-final/RESTORE-NOTE.txt`. |
| R0 phase | See baseline above | Clean before this manifest | **Decision: retain as recovery record.** |

## Recovery artifacts and integrity

- Canonical: `canonical/SHA256SUMS.txt`, `canonical/FILE-INVENTORY.txt`, `canonical/RESTORE.txt`, and `canonical/HEAD-METADATA.txt` identify the restore base and artifacts. `sha256sum -c SHA256SUMS.txt` verified all seven entries, including both recovery-root status snapshots.
- p30-clean: `p30-clean/SHA256SUMS.txt`, `p30-clean/INVENTORY.txt`, and `p30-clean/RESTORE-NOTE.txt`; Git for Windows `sha256sum -c SHA256SUMS.txt` verified all eight listed artifacts, including `branch.bundle`. `git bundle verify p30-clean/branch.bundle` reported a complete SHA-1 history containing `e1c8cc533533f748eb5912c0c96f147fdde5bf70`.
- p30-final: `p30-final/SHA256SUMS.txt`, `p30-final/METADATA.md`, and `p30-final/RESTORE-NOTE.txt`; `sha256sum -c SHA256SUMS.txt` verified all seven listed artifacts.
- Stash backup: `stash-0/RESTORE_NOTE.md`, `stash-0/sha256sums.txt`, and `stash-0/stash-metadata.json`; `sha256sum -c sha256sums.txt` verified all seven listed artifacts. Stash `stash@{0}` is commit `53dde6deedc8af20b8c63f8c5f8fd1ba89a92dc8`, based on `466ec7398037ddf2094395b9c2e221062c622bc9`.

## Checks and boundaries

- `git fsck --full --no-reflogs` exited 0. It reported many dangling objects, but no corruption; dangling-object retention or pruning is outside this recovery action.
- Canonical `git diff --check` exited 0 with only an LF/CRLF warning.
- Restore notes use disposable clean worktrees and saved `git apply --binary` patches; destructive cleanup remains deferred.

## Deferred destructive actions — owner confirmation required

1. Remove the Genesis worktree.
2. Remove the p30-final worktree.
3. Delete `stash@{0}`.
4. Clean recovery/scratch files.
5. Prune Git refs or worktrees.
