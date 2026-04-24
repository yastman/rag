# Env Contract Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `.env` the explicit canonical local environment file and remove stale `.env.local`/symlink drift from docs and tooling.

**Architecture:** Keep runtime behavior unchanged by preserving `.env` as the file loaded by local commands and `BotConfig`. Add a focused regression test for the documented contract, then update the small set of docs/comments that currently imply a different local setup.

**Tech Stack:** Python, pytest, Makefile, Markdown docs

---

### Task 1: Guard the local env contract

**Files:**
- Modify: `tests/unit/test_env_example.py`
- Test: `tests/unit/test_env_example.py`

- [ ] **Step 1: Write the failing test**

Add a focused test that asserts the local workflow documentation/tooling references `.env` as the canonical file and does not mention `.env.local` symlink loading.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_env_example.py -q`
Expected: FAIL because current repo text still contains the stale `.env -> .env.local symlink` comment.

- [ ] **Step 3: Write minimal implementation**

Update the smallest set of repo files to remove the stale `.env.local` symlink guidance and document `.env` as the canonical local env file.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_env_example.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Makefile README.md DOCKER.md docs/LOCAL-DEVELOPMENT.md tests/unit/test_env_example.py docs/superpowers/plans/2026-04-21-env-contract-cleanup-plan.md
git commit -m "docs: align local env contract"
```

### Task 2: Verify the touched contract end-to-end

**Files:**
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `DOCKER.md`
- Modify: `docs/LOCAL-DEVELOPMENT.md`
- Test: `tests/unit/test_env_example.py`
- Test: `tests/unit/test_k8s_secret_templates.py`

- [ ] **Step 1: Run focused regression suite**

Run: `uv run pytest tests/unit/test_env_example.py tests/unit/test_k8s_secret_templates.py -q`
Expected: PASS

- [ ] **Step 2: Run repo checks relevant to touched files**

Run: `uv run pytest tests/unit/test_env_example.py -q`
Expected: PASS

- [ ] **Step 3: Review diff for accidental runtime changes**

Run: `git diff -- Makefile README.md DOCKER.md docs/LOCAL-DEVELOPMENT.md tests/unit/test_env_example.py`
Expected: documentation/comment/test-only cleanup; no unrelated behavior changes

- [ ] **Step 4: Commit**

```bash
git add Makefile README.md DOCKER.md docs/LOCAL-DEVELOPMENT.md tests/unit/test_env_example.py
git commit -m "docs: align local env contract"
```
