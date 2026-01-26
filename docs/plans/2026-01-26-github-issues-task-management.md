# GitHub Issues Task Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up GitHub Issues as backlog storage with labels, integrating with existing TODO.md workflow.

**Architecture:** GitHub Issues stores backlog/ideas with labels (backlog, next, idea). Active work stays in TODO.md for Claude Code visibility. Commits with "Closes #N" auto-close issues. Release Please continues to generate CHANGELOG.

**Tech Stack:** GitHub CLI (gh), GitHub Issues, GitHub Labels

---

## Task 1: Create Labels

**Step 1: Create backlog label**

Run:
```bash
gh label create "backlog" --color "5319E7" --description "Tasks for future work"
```
Expected: Label created

**Step 2: Create next label**

Run:
```bash
gh label create "next" --color "0E8A16" --description "Next tasks to work on"
```
Expected: Label created

**Step 3: Create idea label**

Run:
```bash
gh label create "idea" --color "FBCA04" --description "Ideas without commitment"
```
Expected: Label created

**Step 4: Verify labels**

Run:
```bash
gh label list
```
Expected: Shows backlog, next, idea (plus existing labels)

**Step 5: Commit docs**

```bash
git add docs/plans/2026-01-26-github-issues-task-management.md
git commit -m "docs: add GitHub Issues task management plan"
```

---

## Task 2: Create Initial Issues from Backlog

**Step 1: Create voice message issue**

Run:
```bash
gh issue create --title "feat(bot): voice message support" --body "Add voice message transcription and processing to Telegram bot.

## Acceptance Criteria
- [ ] Receive voice messages
- [ ] Transcribe to text (Whisper API or similar)
- [ ] Process as regular query" --label "next"
```
Expected: Issue created (note the number)

**Step 2: Create Redis pooling issue**

Run:
```bash
gh issue create --title "fix(cache): Redis connection pooling" --body "Implement connection pooling for Redis to improve stability.

## Acceptance Criteria
- [ ] Use redis connection pool
- [ ] Configure max connections
- [ ] Handle connection failures gracefully" --label "next"
```
Expected: Issue created

**Step 3: Create admin panel issue**

Run:
```bash
gh issue create --title "feat: admin panel for property management" --body "Web admin panel for managing property listings.

## Ideas
- CRUD for properties
- Image upload
- Price updates" --label "idea"
```
Expected: Issue created

**Step 4: Create Prometheus issue**

Run:
```bash
gh issue create --title "feat: Prometheus metrics endpoint" --body "Add /metrics endpoint for monitoring.

## Metrics to track
- Request latency
- Cache hit rate
- Qdrant query time
- LLM response time" --label "idea"
```
Expected: Issue created

**Step 5: Create multi-language issue**

Run:
```bash
gh issue create --title "feat: multi-language support (EN/BG/UA)" --body "Support multiple languages in bot responses.

## Languages
- English
- Bulgarian
- Ukrainian" --label "idea"
```
Expected: Issue created

**Step 6: Verify issues**

Run:
```bash
gh issue list
```
Expected: Shows 5 new issues with correct labels

---

## Task 3: Update CLAUDE.md with gh Commands

**Files:**
- Modify: `CLAUDE.md` (add section before Troubleshooting)

**Step 1: Add GitHub Issues section to CLAUDE.md**

Add after "Qdrant Collections" section, before "Deployment":

```markdown
## Task Management

**Active tasks:** `TODO.md` (Claude reads automatically)

**Backlog:** GitHub Issues with labels:
- `next` — следующие к работе
- `backlog` — на будущее
- `idea` — идеи

**Useful commands:**
```bash
gh issue list                      # All open issues
gh issue list --label "next"       # Next to work on
gh issue create --title "..." --label "idea"  # New idea
gh issue close N                   # Close issue
```

**Auto-close:** Use `Closes #N` in commit message.
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): add GitHub Issues task management section"
```

---

## Task 4: Update TODO.md with Issue References

**Files:**
- Modify: `TODO.md`

**Step 1: Update TODO.md to reference issues**

Update In Progress and Next Up to include issue numbers (replace N with actual numbers from Task 2):

```markdown
# TODO

## In Progress
- [ ] feat(search): binary quantization A/B testing

## Next Up
- [ ] feat(bot): voice message support (#N)
- [ ] fix(cache): Redis connection pooling (#N)

## Ideas (Backlog)
See: `gh issue list --label "idea"`

---
*Completed tasks? Delete them. History: `git log --oneline --grep="feat\|fix"`*
*Backlog: `gh issue list`*
```

**Step 2: Commit**

```bash
git add TODO.md
git commit -m "docs(todo): add issue references and backlog pointer"
```

---

## Task 5: Push and Verify

**Step 1: Push all changes**

Run:
```bash
git push origin main
```

**Step 2: Verify issues on GitHub**

Run:
```bash
gh issue list --state all
```
Expected: 5 issues visible

**Step 3: Test auto-close workflow (dry run)**

Run:
```bash
echo "Test commit message format:"
echo 'git commit -m "feat(bot): add feature X

Closes #N"'
```

---

## Verification Checklist

After all tasks complete:

- [ ] Labels exist: backlog, next, idea
- [ ] 5 issues created with correct labels
- [ ] CLAUDE.md has gh commands section
- [ ] TODO.md references issue numbers
- [ ] `gh issue list` works
- [ ] Future: commits with `Closes #N` will auto-close issues

---

## Rollback Plan

If something goes wrong:

```bash
# Delete labels
gh label delete "backlog" --yes
gh label delete "next" --yes
gh label delete "idea" --yes

# Close issues (replace numbers)
gh issue close N --reason "not planned"
```
