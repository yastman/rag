# Issue #3246 Pytest Environment Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent pytest in an internal worktree from loading the primary checkout's `.env` while preserving explicit current-checkout dotenv behavior.

**Architecture:** Keep environment loading in the existing shared pytest bootstrap, but replace upward discovery with one explicit path derived from `tests/conftest.py`. A static contract freezes that security boundary.

**Tech Stack:** Python 3.12, pytest, python-dotenv, AST/static contract tests.

**Spec:** `docs/specs/2026-08-29-issue-3246-pytest-env-isolation.md`

## Global Constraints

- Work only in `.worktrees/issue-3246` on `codex/issue-3246-pytest-env-isolation`.
- Never read or print `.env` contents.
- Do not clear existing process environment variables or change dotenv override semantics.
- No product/runtime/dependency changes.
- Commit only this issue's spec, plan, shared pytest bootstrap, and focused contract.

---

## Task 1: Add the Failing Scope Contract

**Files:**

- Create: `tests/contract/test_pytest_dotenv_scope_contract.py`
- Read: `tests/conftest.py`

- [x] Add a focused contract that parses/inspects the shared bootstrap and rejects unbounded `load_dotenv()` discovery.
- [x] Require one explicit current-checkout-root `.env` path while preserving the opt-out.
- [x] Run the focused contract and capture the expected RED failure against the old call.

```powershell
uv run --no-sync pytest tests/contract/test_pytest_dotenv_scope_contract.py -q
```

## Task 2: Scope Dotenv to the Current Worktree

**Files:**

- Modify: `tests/conftest.py`

- [x] Derive the current checkout root from the resolved `tests/conftest.py` path.
- [x] Pass `<current-checkout>/.env` explicitly to `load_dotenv`.
- [x] Keep `PYTHON_DOTENV_DISABLED` behavior and default non-overriding semantics unchanged.
- [x] Run the new contract and E2E configuration tests GREEN.

```powershell
uv run --no-sync pytest tests/contract/test_pytest_dotenv_scope_contract.py tests/unit/e2e_adapters/test_config.py -q
```

## Task 3: Verify and Commit

- [x] Prove only the four issue-owned documentation/test paths changed.
- [x] Run `git diff --check` and inspect the complete diff.
- [x] Confirm no environment file is tracked or changed.
- [x] Commit with the issue number; do not push or mutate GitHub.
