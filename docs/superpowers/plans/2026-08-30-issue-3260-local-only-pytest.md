# Issue #3260 Local-Only Pytest CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Remove hosted pytest execution while preserving the repository's complete local test
ladder and fast hosted static/security checks.

**Architecture:** Extend the existing local-gate policy contract. Parse active workflow YAML with
the already-declared PyYAML dependency and compare every `run` step and action reference to an
explicit approved static/security allowlist. This avoids reimplementing Bash, PowerShell, Make, or
runner semantics. Delete only the obsolete hosted Windows job.

**Tech Stack:** GitHub Actions YAML, Python 3.12, PyYAML, pytest.

**Spec:** `docs/specs/2026-08-30-issue-3260-local-only-pytest.md`

## Global Constraints

- Work only in `.worktrees/issue-3260` on `codex/issue-3260-local-only-ci`.
- Modify only `.github/workflows/ci.yml`, the existing local-gate contract, and this issue's docs.
- Do not edit local test runners, dependencies, lockfiles, or unrelated workflow jobs.
- Main implements; only Sol/max subagents review.

---

## Task 1: Add the Executable Workflow Contract

**File:** `tests/contract/test_local_gate_policy_contract.py`

- [x] Enumerate `run` commands from every active `.github/workflows/*.yml` and `*.yaml` file.
- [x] Reject every unknown or changed hosted run step through the exact allowlist.
- [x] Reject custom shell overrides and require every approved pinned action, including gitleaks.
- [x] Add mutations covering each prohibited route and a harmless static command.
- [x] Run the focused node and capture RED against the existing hosted Windows test step.

## Task 2: Remove Hosted Pytest

**File:** `.github/workflows/ci.yml`

- [x] Delete the complete `windows-smoke` job.
- [x] Preserve all fast static/security jobs and exact commands outside that job.
- [x] Keep `scripts/windows_preflight.ps1 -Mode Tests` unchanged for local use.
- [x] Run the focused contract GREEN.

## Task 3: Verify and Deliver

- [x] Run the complete local contract payload and local pre-push gate.
- [x] Run actionlint locally, verify the pinned gitleaks job remains unchanged, and inspect the
  exact four-file and dependency diffs.
- [ ] Commit, obtain independent Sol/max review, push, create the dedicated PR, and require hosted
  fast checks to pass before merging into `dev`.
