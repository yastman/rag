# Issue #3257 E2E Config Hermeticity Implementation Plan

**Goal:** Remove host provider keys and implicit ancestor dotenv discovery from E2E config tests.

**Architecture:** Keep the existing pytest bootstrap and `patch.dict` boundary. Disable later
python-dotenv discovery after bootstrap, and keep validation inside the cleared boundary.

**Spec:** `docs/specs/2026-08-30-issue-3257-e2e-config-hermeticity.md`

## Constraints

- Work only in `.worktrees/issue-3257` on `codex/issue-3257-hermetic-e2e-config`.
- Do not add/sync dependencies or change production provider routing.
- Do not read, print, or assert real credential values.
- Main implements; Sol/max subagent performs final review.

## Tasks

- [x] Capture RED with a fabricated parent provider key.
- [x] Add the downstream dotenv-discovery regression and capture RED.
- [x] Keep construction and validation inside the cleared environment.
- [x] Disable subsequent dotenv discovery after pytest bootstrap.
- [x] Run focused and repository-required local gates.
- [ ] Commit, obtain Sol/max approval, open the dedicated PR, and merge only after green static CI.
