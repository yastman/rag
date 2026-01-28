# Renovate Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Configure Renovate Bot to automatically create PRs for Docker image updates.

**Architecture:** Renovate GitHub App scans docker-compose files and Dockerfiles, queries Docker registries for new versions, creates PRs with grouped updates and auto-merge for patches.

**Tech Stack:** Renovate Bot (GitHub App), JSON config, Docker registries (Docker Hub, GHCR, Quay.io)

---

## Task 1: Create renovate.json configuration

**Files:**
- Create: `renovate.json`

**Step 1: Create the configuration file**

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", "docker:enableMajor"],

  "schedule": ["before 9am on monday"],
  "timezone": "Europe/Kiev",

  "dependencyDashboard": true,
  "platformAutomerge": true,
  "prHourlyLimit": 5,
  "labels": ["dependencies", "docker"],

  "packageRules": [
    {
      "description": "Auto-merge patch updates",
      "matchUpdateTypes": ["patch"],
      "automerge": true
    },
    {
      "description": "Databases - stable, auto-merge minor",
      "matchPackageNames": ["pgvector/pgvector", "redis/redis-stack", "qdrant/qdrant"],
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": true,
      "groupName": "databases"
    },
    {
      "description": "ML Platform - group together",
      "matchPackageNames": ["ghcr.io/berriai/litellm", "langfuse/langfuse", "ghcr.io/mlflow/mlflow"],
      "groupName": "ml-platform"
    },
    {
      "description": "LiteLLM - allow unstable versions (they use rc tags)",
      "matchPackageNames": ["ghcr.io/berriai/litellm"],
      "ignoreUnstable": false
    },
    {
      "description": "AI Services - group docling and lightrag",
      "matchPackageNames": [
        "ghcr.io/docling-project/docling-serve-cpu",
        "quay.io/docling-project/docling-serve",
        "ghcr.io/hkuds/lightrag"
      ],
      "groupName": "ai-services"
    },
    {
      "description": "Base images - Python",
      "matchPackageNames": ["python"],
      "groupName": "python-base"
    },
    {
      "description": "Skip release candidates except for litellm",
      "matchPackagePatterns": ["^(?!ghcr\\.io/berriai/litellm).*$"],
      "allowedVersions": "!/^.*(-rc|-alpha|-beta).*$/"
    },
    {
      "description": "Pin floating tags to digest",
      "matchCurrentVersion": "/^latest$/",
      "pinDigests": true
    }
  ]
}
```

**Step 2: Validate JSON syntax**

Run: `python -c "import json; json.load(open('renovate.json'))"`
Expected: No output (valid JSON)

**Step 3: Commit the configuration**

```bash
git add renovate.json
git commit -m "feat(renovate): add Renovate Bot configuration for Docker updates"
```

---

## Task 2: Fix version inconsistencies in docker-compose files

**Files:**
- Modify: `docker-compose.dev.yml`
- Modify: `docker-compose.local.yml`

**Context:** `docker-compose.local.yml` has older qdrant version (v1.15.4 vs v1.16 in dev). Standardize before Renovate takes over.

**Step 1: Update qdrant version in local compose**

In `docker-compose.local.yml`, change line 3:
```yaml
# Before:
    image: qdrant/qdrant:v1.15.4
# After:
    image: qdrant/qdrant:v1.16
```

**Step 2: Verify compose files are valid**

Run: `docker compose -f docker-compose.dev.yml config --quiet && docker compose -f docker-compose.local.yml config --quiet && echo "OK"`
Expected: `OK`

**Step 3: Commit the change**

```bash
git add docker-compose.local.yml
git commit -m "chore(docker): sync qdrant version to v1.16 in local compose"
```

---

## Task 3: Add .github/renovate.json alternative location (optional)

**Files:**
- Create: `.github/renovate.json5` (symlink or move)

**Context:** Some teams prefer config in .github folder. Skip this task if root location is preferred.

**Step 1: Decide on location**

Options:
- `renovate.json` (root) — simpler, already created
- `.github/renovate.json5` — grouped with other GitHub configs

**Recommendation:** Keep in root (`renovate.json`). Skip this task.

---

## Task 4: Document Renovate setup in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add Renovate section to CLAUDE.md**

Add after "## Troubleshooting" section:

```markdown
## Dependency Updates (Renovate)

Renovate Bot automatically creates PRs for Docker image updates.

**Configuration:** `renovate.json`

**Schedule:** Monday before 9:00 AM (Europe/Kiev)

**Auto-merge:** Patch versions merge automatically after CI passes.

**Manual actions:**
- Check "Dependency Dashboard" issue for pending updates
- Tick checkbox to trigger immediate PR creation
- Review and merge minor/major version PRs manually

**Groups:**
- `databases`: postgres, redis, qdrant
- `ml-platform`: litellm, langfuse, mlflow
- `ai-services`: docling, lightrag
- `python-base`: Python base images in Dockerfiles

**Disable temporarily:** Delete `renovate.json` or add `"enabled": false`.
```

**Step 2: Commit the documentation**

```bash
git add CLAUDE.md
git commit -m "docs: add Renovate Bot section to CLAUDE.md"
```

---

## Task 5: Install Renovate GitHub App (manual step)

**Files:** None (GitHub UI action)

**Step 1: Open Renovate App page**

URL: https://github.com/apps/renovate

**Step 2: Click "Install"**

**Step 3: Select repository**

Choose: `rag-fresh` (or the actual repo name)

**Step 4: Confirm permissions**

Renovate needs:
- Read access to code
- Write access to PRs and Issues

**Step 5: Wait for onboarding PR**

Renovate will create PR "Configure Renovate" within minutes.
Since we already have `renovate.json`, it will use our config.

---

## Task 6: Verify Renovate is working

**Files:** None (GitHub verification)

**Step 1: Check for Dependency Dashboard issue**

Go to: `https://github.com/<owner>/rag-fresh/issues`
Look for: Issue titled "Dependency Dashboard"

**Step 2: Verify detected dependencies**

Dashboard should list all Docker images from:
- `docker-compose.dev.yml` (12 images)
- `docker-compose.local.yml` (4 images)
- `telegram_bot/Dockerfile` (python:3.12-slim)
- `docker/mlflow/Dockerfile` (ghcr.io/mlflow/mlflow:v2.22.1)

**Step 3: Trigger a test update (optional)**

In Dependency Dashboard, tick checkbox next to any available update.
Verify PR is created with correct changes.

---

## Task 7: Push changes and create PR

**Files:** None (git operations)

**Step 1: Push feature branch**

```bash
git push -u origin feature/renovate-setup
```

**Step 2: Create PR**

```bash
gh pr create \
  --title "feat(renovate): add Renovate Bot for Docker image updates" \
  --body "## Summary
- Add \`renovate.json\` configuration
- Sync qdrant version in docker-compose.local.yml
- Document Renovate in CLAUDE.md

## What Renovate does
- Creates PRs for Docker image updates
- Auto-merges patch versions
- Groups related services (databases, ml-platform, ai-services)
- Runs weekly on Monday mornings

## After merge
1. Install Renovate GitHub App: https://github.com/apps/renovate
2. Renovate creates 'Dependency Dashboard' issue
3. First update PRs appear on next Monday (or trigger manually)

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

**Step 3: Merge after review**

---

## Summary

| Task | Description | Type |
|------|-------------|------|
| 1 | Create renovate.json | Code |
| 2 | Fix version inconsistencies | Code |
| 3 | Alternative config location | Skip |
| 4 | Document in CLAUDE.md | Docs |
| 5 | Install GitHub App | Manual |
| 6 | Verify Renovate works | Manual |
| 7 | Push and create PR | Git |

**Total code tasks:** 3 (Tasks 1, 2, 4)
**Manual tasks:** 3 (Tasks 5, 6, 7)
