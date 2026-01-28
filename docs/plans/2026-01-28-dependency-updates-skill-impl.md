# dependency-updates Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Claude Code skill that analyzes Renovate PRs, categorizes by risk, and helps merge with test verification.

**Architecture:** Single SKILL.md file in `~/.claude/skills/dependency-updates/` with inline instructions for fetching PRs, categorizing, and executing merges.

**Tech Stack:** Claude Code Skills, GitHub CLI (gh), pytest

---

### Task 1: Create skill directory structure

**Files:**
- Create: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Create directory**

```bash
mkdir -p ~/.claude/skills/dependency-updates
```

**Step 2: Verify directory exists**

Run: `ls -la ~/.claude/skills/`
Expected: `dependency-updates/` directory listed

**Step 3: Commit** (skip - personal skills not in repo)

---

### Task 2: Write SKILL.md frontmatter

**Files:**
- Create: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Create SKILL.md with frontmatter**

```markdown
---
name: dependency-updates
description: Use when managing Renovate dependency PRs, reviewing updates, or merging safe dependency changes. Invoke with /deps command.
---
```

**Step 2: Verify frontmatter is valid YAML**

Run: `head -5 ~/.claude/skills/dependency-updates/SKILL.md`
Expected: Valid YAML frontmatter with name and description

---

### Task 3: Write Overview section

**Files:**
- Modify: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Add Overview section**

```markdown
# Dependency Updates

Interactive assistant for Renovate dependency management.

## Overview

Analyzes Renovate PRs, categorizes by risk level, recommends safe updates, executes merges with test verification.

**Trigger:** `/deps` command

**Workflow:**
1. Fetch Renovate PRs
2. Categorize: Safe → Medium → Risky
3. Show recommendations
4. Wait for user choice
5. Merge approved PRs
6. Run tests
7. Report results
```

---

### Task 4: Write Risk Categories section

**Files:**
- Modify: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Add Risk Categories**

```markdown
## Risk Categories

### ✅ SAFE (auto-recommend)
- Patch versions: `1.2.3 → 1.2.4`
- GitHub Actions patch/minor
- Stable libs: pydantic, httpx, uvicorn, python-dotenv, prometheus-client

### ⚠️ MEDIUM (ask user)
- Minor versions: `1.2.0 → 1.3.0`
- Docker images minor
- ML libs: torch, transformers, sentence-transformers

### ❌ RISKY (warn)
- Major versions: `1.x → 2.x`
- Python base: `3.12 → 3.14`
- Known breaking: numpy v2, langfuse v3
```

---

### Task 5: Write Commands section

**Files:**
- Modify: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Add Commands section**

```markdown
## Commands

### Fetch PRs
```bash
gh pr list --author "renovate[bot]" --json number,title,state --jq '.[] | select(.state == "OPEN")'
```

### Merge PR
```bash
gh pr merge {number} --squash
```

### Request Rebase
```bash
gh pr comment {number} --body "@renovate rebase"
```

### Run Tests
```bash
pytest tests/unit/ -q
```
```

---

### Task 6: Write User Input section

**Files:**
- Modify: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Add User Input handling**

```markdown
## User Input

| Input | Action |
|-------|--------|
| `y` | Merge all SAFE PRs |
| `n` | Cancel |
| `18,19,21` | Merge specific PR numbers |
| `all` | Merge SAFE + MEDIUM |
| `rebase` | Request rebase for conflicting PRs |
| `skip` | Show list without merging |
```

---

### Task 7: Write Output Format section

**Files:**
- Modify: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Add Output Format**

```markdown
## Output Format

```
📦 Dependency Updates

✅ SAFE (3 PRs) — recommend merge:
   #18 httpx 0.28.1
   #19 prometheus-client 0.24.1
   #21 pydantic-settings 2.12.0

⚠️ MEDIUM (2 PRs) — check changelog:
   #13 mlflow v2.22.4
   #24 qdrant-client 1.16.2

❌ RISKY (2 PRs) — skip unless needed:
   #22 python 3.14 (major)
   #35 numpy v2 (breaking)

⚠️ CONFLICTS (1 PR):
   #20 pydantic 2.12.5

Merge? [y/n/numbers/rebase]
```
```

---

### Task 8: Write Post-Merge section

**Files:**
- Modify: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Add Post-Merge workflow**

```markdown
## Post-Merge

1. Run tests: `pytest tests/unit/ -q`
2. If tests fail:
   - Show failed test names
   - Offer: "Revert last merge? [y/n]"
3. Show summary:
   ```
   ✅ Done: 3 merged, 0 failed tests
   ⏭️ Skipped: 2 risky, 1 conflict
   ```
```

---

### Task 9: Assemble complete SKILL.md

**Files:**
- Write: `~/.claude/skills/dependency-updates/SKILL.md`

**Step 1: Write complete file**

Combine all sections from Tasks 2-8 into single file.

**Step 2: Verify file**

Run: `wc -l ~/.claude/skills/dependency-updates/SKILL.md`
Expected: ~80-120 lines

**Step 3: Test skill discovery**

Run: `ls ~/.claude/skills/dependency-updates/`
Expected: `SKILL.md`

---

### Task 10: Test skill manually

**Step 1: Start new Claude session**

```bash
claude
```

**Step 2: Invoke skill**

```
/deps
```

**Step 3: Verify output**

Expected: Skill fetches Renovate PRs and shows categorized list.

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create directory | `~/.claude/skills/dependency-updates/` |
| 2 | Frontmatter | SKILL.md |
| 3 | Overview | SKILL.md |
| 4 | Risk Categories | SKILL.md |
| 5 | Commands | SKILL.md |
| 6 | User Input | SKILL.md |
| 7 | Output Format | SKILL.md |
| 8 | Post-Merge | SKILL.md |
| 9 | Assemble | SKILL.md |
| 10 | Test | Manual |

**Total tasks:** 10
**Estimated complexity:** Low (single file skill)
