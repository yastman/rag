# Issue #3255 Archived `mini_app` Ruff Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a meaningful Ubuntu Ruff gate by removing the archived `mini_app/` path and
preventing the CI/local path lists from drifting again.

**Architecture:** `Makefile` `LINT_PATHS` remains the local source for the supported lint surface.
A focused repository contract requires both CI Ruff invocations to use that exact ordered list.

**Tech Stack:** GitHub Actions YAML, Python 3.12, pytest, Ruff.

**Spec:** `docs/specs/2026-08-29-issue-3255-ci-remove-mini-app.md`

## Global Constraints

- Work only in `.worktrees/issue-3255` on `codex/issue-3255-ci-remove-mini-app`.
- Modify only `.github/workflows/ci.yml`,
  `tests/contract/test_local_gate_policy_contract.py`, and this issue's spec/plan.
- Preserve all existing Ruff flags and the order of the four live paths.
- Do not add pytest to CI, modify Make targets, or expand workflow scope.

---

## Task 1: Add the Failing Drift Contract

**File:** `tests/contract/test_local_gate_policy_contract.py`

- [x] Derive the ordered lint path string from `Makefile` `LINT_PATHS`.
- [x] Assert both CI Ruff commands use that exact path string with their existing flags.
- [x] Run the focused contract and capture RED against the stale `mini_app/` path.

## Task 2: Repair the Ubuntu Ruff Commands

**File:** `.github/workflows/ci.yml`

- [x] Remove only `mini_app/` from `Ruff lint` and `Ruff format check`.
- [x] Keep all remaining flags, paths, jobs, and workflow behavior unchanged.

## Task 3: Verify and Commit

- [x] Run the focused contract; expect GREEN.
- [x] Run the two exact Ruff commands from the workflow; require lint to pass and prove format
  reaches the live path set. Track version-only failure separately in #3256.
- [x] Run `git diff --check`, inspect the complete diff, and commit only the four owned files.
- [x] Do not push, merge, or mutate GitHub; Main owns delivery.

Verification note: `ruff check` exits zero. With floating `uvx` resolving Ruff 0.16.5, the exact
format command reaches the live path set but reports pre-existing Markdown formatting drift in
`src/config/README.md`; deterministic hosted Ruff versioning is isolated as #3256.
