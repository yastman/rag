# Documentation System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement persistent context system with auto-generated changelog via Release Please.

**Architecture:** CLAUDE.md serves as master index with Current Sprint section. TODO.md stays under 20 lines. Release Please auto-generates CHANGELOG from conventional commits on push to main.

**Tech Stack:** GitHub Actions, Release Please v4, Markdown, Conventional Commits

---

## Task 1: Create New TODO.md

**Files:**
- Create: `TODO.md` (overwrite existing)

**Step 1: Write the new TODO.md**

```markdown
# TODO

## In Progress
- [ ] docs: implement documentation system v2

## Next Up
- [ ] feat(search): binary quantization A/B testing
- [ ] feat(bot): voice message support
- [ ] fix(cache): Redis connection pooling

## Ideas (Backlog)
- Admin panel for property management
- Prometheus metrics endpoint
- Multi-language support (EN/BG/UA)

---
*Completed tasks? Delete them. History: `git log --oneline --grep="feat\|fix"`*
```

**Step 2: Verify file is under 20 lines**

Run: `wc -l TODO.md`
Expected: 15-18 lines

**Step 3: Commit**

```bash
git add TODO.md
git commit -m "docs(todo): reset TODO.md to short format (15 lines)"
```

---

## Task 2: Add Current Sprint Section to CLAUDE.md

**Files:**
- Modify: `CLAUDE.md:12` (after Project Overview section)

**Step 1: Identify insertion point**

The new section goes after line 12 (after "Primary use cases" line), before "## Build & Development Commands".

**Step 2: Insert Current Sprint section**

Add this content after line 12:

```markdown

## Current Sprint

**Focus:** Documentation System + Binary Quantization
**Version:** 2.12.0
**Started:** 2026-01-26

### Active Work
- Documentation system v2 (Release Please, TODO reset)
- Binary quantization A/B testing (`scripts/test_quantization_ab.py`)

### Recently Completed
- SDK migration for search engines (2026-01-26)
- DBSF fusion implementation
- Query routing (CHITCHAT/SIMPLE/COMPLEX)

### Blockers
None

---
*Updated: 2026-01-26 | Next review: 2026-02-02*

```

**Step 3: Verify CLAUDE.md structure**

Run: `grep -n "## " CLAUDE.md | head -10`
Expected: Shows "Current Sprint" as second h2 section

**Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): add Current Sprint section for persistent context"
```

---

## Task 3: Create Release Please Config

**Files:**
- Create: `release-please-config.json`

**Step 1: Write configuration file**

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "release-type": "python",
  "packages": {
    ".": {
      "changelog-path": "CHANGELOG.md",
      "release-type": "python",
      "bump-minor-pre-major": true,
      "bump-patch-for-minor-pre-major": true,
      "changelog-sections": [
        {"type": "feat", "section": "Features", "hidden": false},
        {"type": "fix", "section": "Bug Fixes", "hidden": false},
        {"type": "perf", "section": "Performance", "hidden": false},
        {"type": "docs", "section": "Documentation", "hidden": true},
        {"type": "chore", "section": "Miscellaneous", "hidden": true},
        {"type": "refactor", "section": "Code Refactoring", "hidden": true},
        {"type": "test", "section": "Tests", "hidden": true}
      ]
    }
  }
}
```

**Step 2: Validate JSON syntax**

Run: `python -c "import json; json.load(open('release-please-config.json'))"`
Expected: No output (valid JSON)

**Step 3: Commit**

```bash
git add release-please-config.json
git commit -m "chore: add Release Please configuration"
```

---

## Task 4: Create Release Please Manifest

**Files:**
- Create: `.release-please-manifest.json`

**Step 1: Write manifest file**

```json
{
  ".": "2.12.0"
}
```

**Step 2: Validate JSON syntax**

Run: `python -c "import json; json.load(open('.release-please-manifest.json'))"`
Expected: No output (valid JSON)

**Step 3: Commit**

```bash
git add .release-please-manifest.json
git commit -m "chore: add Release Please manifest (v2.12.0)"
```

---

## Task 5: Create Release Please GitHub Action

**Files:**
- Create: `.github/workflows/release-please.yml`

**Step 1: Write workflow file**

```yaml
name: Release Please

on:
  push:
    branches:
      - main

permissions:
  contents: write
  pull-requests: write

jobs:
  release-please:
    runs-on: ubuntu-latest
    outputs:
      release_created: ${{ steps.release.outputs.release_created }}
      tag_name: ${{ steps.release.outputs.tag_name }}
      version: ${{ steps.release.outputs.version }}
    steps:
      - uses: googleapis/release-please-action@v4
        id: release
        with:
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json

      - name: Output release info
        if: ${{ steps.release.outputs.release_created }}
        run: |
          echo "::notice::Release created: ${{ steps.release.outputs.tag_name }}"
          echo "::notice::Version: ${{ steps.release.outputs.version }}"
```

**Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release-please.yml'))"`
Expected: No output (valid YAML)

**Step 3: Commit**

```bash
git add .github/workflows/release-please.yml
git commit -m "ci: add Release Please workflow for automatic changelog"
```

---

## Task 6: Clean Up CHANGELOG.md for Release Please

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Remove [Unreleased] section**

Remove lines 10-22 (the [Unreleased] section with checkboxes). Release Please will manage unreleased changes.

**Step 2: Verify CHANGELOG structure**

Run: `head -30 CHANGELOG.md`
Expected: Starts with header, then [2.9.0] section

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): prepare for Release Please (remove Unreleased section)"
```

---

## Task 7: Update Task Management Section in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md:269-274` (Task Management section)

**Step 1: Update Task Management section**

Replace current content with:

```markdown
## Task Management

**Active tasks:** `TODO.md` (max 20 lines, delete when done)

**History:**
- `git log --oneline --grep="feat\|fix"` - Completed tasks
- `CHANGELOG.md` - Auto-generated by Release Please

**Planning:** `docs/plans/*.md` - Design documents
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): update Task Management section for new workflow"
```

---

## Task 8: Final Verification & Squash Commit

**Step 1: Verify all files exist**

Run: `ls -la TODO.md CLAUDE.md release-please-config.json .release-please-manifest.json .github/workflows/release-please.yml`
Expected: All 5 files listed

**Step 2: Run linter on markdown**

Run: `make lint` (or skip if no markdown linter)
Expected: PASS

**Step 3: Create final squashed commit (optional)**

If you want single commit instead of multiple:

```bash
git reset --soft HEAD~7
git commit -m "docs: implement documentation system v2

- Reset TODO.md to short format (15 lines)
- Add Current Sprint section to CLAUDE.md
- Add Release Please configuration
- Add Release Please GitHub Action
- Prepare CHANGELOG.md for automation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

**Step 4: Push to main**

```bash
git push origin main
```

Expected: Release Please creates PR within 1-2 minutes

---

## Verification Checklist

After push to main:

- [ ] GitHub shows Release Please PR (check Actions tab)
- [ ] PR contains updated CHANGELOG.md
- [ ] New Claude Code session reads Current Sprint from CLAUDE.md
- [ ] TODO.md is under 20 lines
- [ ] `git log --oneline --grep="feat\|fix"` shows task history

---

## Rollback Plan

If Release Please doesn't work:

```bash
# Disable workflow
mv .github/workflows/release-please.yml .github/workflows/release-please.yml.disabled

# Continue using manual CHANGELOG
git commit -m "ci: disable Release Please (manual changelog for now)"
```
