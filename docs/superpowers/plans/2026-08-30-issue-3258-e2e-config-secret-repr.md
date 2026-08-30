# Issue #3258 E2E Config Secret Representation Implementation Plan

**Goal:** Prevent E2E credentials from appearing in Pydantic and assertion representations.

**Architecture:** Use Pydantic's existing `Field(repr=False)` metadata on the three credential
fields and one focused sentinel regression in the existing E2E config test module.

**Spec:** `docs/specs/2026-08-30-issue-3258-e2e-config-secret-repr.md`

## Constraints

- Work only in `.worktrees/issue-3258` on `codex/issue-3258-redact-e2e-credentials`.
- Use fabricated sentinels; never inspect or print real credentials.
- Do not add abstractions, dependencies, or provider behavior.
- Main implements; Sol/max subagent performs final review.

## Tasks

- [x] Add the sentinel representation regression and capture RED.
- [x] Mark exactly the three credential fields `repr=False`.
- [x] Run focused and repository-required local gates.
- [ ] Commit, obtain Sol/max approval, open the dedicated PR, and merge after green static CI.
