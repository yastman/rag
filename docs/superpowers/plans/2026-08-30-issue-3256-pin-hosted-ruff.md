# Issue #3256 Hosted Ruff Version Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make hosted Ruff execution deterministic by pinning both CI steps to the unique Ruff
version in `uv.lock`.

**Architecture:** Extend the existing exact CI-command contract instead of adding a duplicate test.
The contract parses `uv.lock` with stdlib `tomllib`, derives one Ruff version, and combines it with
the existing `Makefile` path authority when comparing the complete named-step commands.

**Tech Stack:** GitHub Actions YAML, Python 3.12 stdlib `tomllib`, pytest, uv, Ruff.

**Spec:** `docs/specs/2026-08-30-issue-3256-pin-hosted-ruff.md`

## Global Constraints

- Work only in `.worktrees/issue-3256` on `codex/issue-3256-pin-hosted-ruff`.
- Modify only `.github/workflows/ci.yml`, the existing local-gate contract, and this issue's docs.
- Do not add dependencies, edit `pyproject.toml`/`uv.lock`, format source/docs, or change path order.
- Main implements; only Sol/max subagents review.

---

## Task 1: Extend the Exact Contract

**File:** `tests/contract/test_local_gate_policy_contract.py`

- [x] Parse `uv.lock` with `tomllib` and require exactly one package named `ruff`.
- [x] Build the expected `uvx --from ruff==<version> ruff` prefix from that entry.
- [x] Reuse the current named-step and `LINT_PATHS` checks; do not add a parallel duplicate test.
- [x] Run the focused node and capture RED against floating `uvx ruff`.

## Task 2: Pin the Hosted Commands

**File:** `.github/workflows/ci.yml`

- [x] Add `--from ruff==0.15.20` to both Ruff invocations, using the exact current lock version.
- [x] Preserve step names, all flags, and the four live paths.
- [x] Run the focused contract GREEN.

## Task 3: Verify and Commit

- [x] Run both exact pinned Ruff commands; require zero exits.
- [x] Run the focused contract file and repository contract gate payload.
- [x] Run `git diff --check`, inspect the complete four-file diff, and commit with #3256.
- [ ] Obtain scoped and final Sol/max review before push/PR; Main owns GitHub delivery.
