---
name: dependency-updates
description: Use when managing Renovate dependency PRs, reviewing updates, or merging safe dependency changes. Invoke with /deps command.
---

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

## User Input

| Input | Action |
|-------|--------|
| `y` | Merge all SAFE PRs |
| `n` | Cancel |
| `18,19,21` | Merge specific PR numbers |
| `all` | Merge SAFE + MEDIUM |
| `rebase` | Request rebase for conflicting PRs |
| `skip` | Show list without merging |

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
