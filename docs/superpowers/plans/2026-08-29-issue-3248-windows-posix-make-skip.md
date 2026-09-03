# Issue #3248 Native Windows POSIX Make Test Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip one POSIX-only dynamic Make test on native Windows without weakening its POSIX behavior or the surrounding static contracts.

**Architecture:** Platform capability is decided at the test boundary. The Makefile remains POSIX-only as documented; native Windows validates its static contract and the official PowerShell gate instead.

**Tech Stack:** Python 3.12, pytest, GNU Make.

**Spec:** `docs/specs/2026-08-29-issue-3248-windows-posix-make-skip.md`

## Global Constraints

- Work only in `.worktrees/issue-3248` on `codex/issue-3248-windows-posix-make-skip`.
- Modify only `tests/unit/scripts/test_git_hygiene.py` plus this issue's spec/plan.
- Do not edit Makefile, cleanup behavior, Windows preflight, or unrelated tests.
- Preserve the test body so POSIX coverage remains real.

---

## Task 1: Capture the Native Windows Failure

- [x] Run the exact dynamic node on native Windows and capture the `cmd.exe` POSIX-syntax failure.

```powershell
uv run --no-sync pytest -q --tb=short tests/unit/scripts/test_git_hygiene.py::test_force_cleanup_deletes_branch_merged_into_base_from_other_head
```

## Task 2: Add the Narrow Platform Boundary

**Files:**

- Modify: `tests/unit/scripts/test_git_hygiene.py`

- [x] Import `sys` using the file's existing import style.
- [x] Add `pytest.mark.skipif(sys.platform == "win32", reason="requires a POSIX shell")` to only the dynamic Make test.
- [x] Retain the make-unavailable skip and unchanged test body.

## Task 3: Verify and Commit

- [x] Run the focused file; native Windows must show the intended skip and all static assertions must pass.
- [x] Inspect the full diff and run `git diff --check`.
- [x] Commit only the three owned files; do not push or mutate GitHub.
