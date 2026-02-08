---
name: gh-issues
description: >-
  Use when creating, searching, updating, or managing GitHub issues via CLI.
  Triggers: "issue", "create issue", "gh issue", "task tracking",
  "context", "handoff", "resume task", "session context", "save progress",
  "active tasks", "in-progress", "my tasks", "open issues".
  Covers: gh commands, bulk operations, JSON/jq, search filters, issue-to-PR workflow,
  AI session context storage, task workflow with labels.
---

***REMOVED*** GitHub Issues CLI

Efficient GitHub Issues management via `gh` CLI with AI session context storage.

***REMOVED******REMOVED*** Table of Contents

1. [Quick Reference](***REMOVED***quick-reference)
2. [JSON Output](***REMOVED***json-output-patterns)
3. [Search Filters](***REMOVED***advanced-search-filters)
4. [Bulk Operations](***REMOVED***bulk-operations)
5. [Issue to PR Workflow](***REMOVED***issue-to-pr-workflow)
6. [Milestones](***REMOVED***milestones-via-api)
7. [AI Session Context](***REMOVED***ai-session-context)
8. [Task Workflow](***REMOVED***task-workflow)
9. [Examples](***REMOVED***examples)
10. [Common Mistakes](***REMOVED***common-mistakes)

***REMOVED******REMOVED*** Quick Reference

| Task | Command |
|------|---------|
| Create issue | `gh issue create -t "Title" -b "Body" -l bug -a @me` |
| **Active tasks** | `gh issue list -l in-progress -s open` |
| List open bugs | `gh issue list -l bug -s open` |
| View as JSON | `gh issue view 123 --json number,title,body,labels,state` |
| Close with comment | `gh issue close 123 -c "Fixed in ***REMOVED***456"` |
| Edit labels | `gh issue edit 123 --add-label priority:high` |
| Start work | `gh issue edit 45 --add-label in-progress` |
| Create branch | `gh issue develop 123 --checkout` |
| Load context | `gh issue view 45 --json comments --jq '.comments[] \| select(.body \| contains("AI-CONTEXT"))' ` |

***REMOVED******REMOVED*** JSON Output Patterns

Always use `--json` for parsing. Fields: `number`, `title`, `body`, `state`, `labels`, `assignees`, `milestone`, `author`, `createdAt`, `updatedAt`, `comments`, `url`.

```bash
gh issue view 123 --json number,title,labels,state
gh issue list --json number,title,labels --jq '.[] | select(.labels[].name == "bug")'
gh issue list -l bug --json number --jq '.[].number'
```

***REMOVED******REMOVED*** Advanced Search Filters

```bash
gh issue list --search "is:open author:username"
gh issue list --search "created:>=2026-01-01 created:<=2026-01-07"
gh issue list --search "label:bug label:priority:high"
gh issue list --search "is:open -label:wontfix"
gh issue list --search "milestone:v2.0"
```

***REMOVED******REMOVED*** Bulk Operations

```bash
gh issue edit 10 15 20 --add-label "priority:high"
gh issue close 10 15 20 -c "Duplicate of ***REMOVED***5"
gh issue list -l needs-triage --json number --jq '.[].number' | \
  xargs -I{} gh issue edit {} --add-label reviewed
```

***REMOVED******REMOVED*** Issue to PR Workflow

```bash
gh issue develop 123 --checkout          ***REMOVED*** Create branch from issue
git add . && git commit -m "fix: ***REMOVED***123"   ***REMOVED*** Commit with reference
gh pr create --fill                       ***REMOVED*** Create PR (auto-links)
gh issue close 123 -c "Fixed in PR ***REMOVED***456" ***REMOVED*** Close when merged
```

***REMOVED******REMOVED*** Milestones via API

```bash
gh api repos/:owner/:repo/milestones --jq '.[].title'
gh issue edit 123 -m "v2.0"
```

***REMOVED******REMOVED*** AI Session Context

Store session context in GitHub issues for seamless task handoff.

***REMOVED******REMOVED******REMOVED*** Read Context

```bash
***REMOVED*** Get AI context from issue comments
gh issue view 45 --json comments --jq '
  .comments[] | select(.body | contains("AI-CONTEXT:START")) | .body
'

***REMOVED*** Get comment ID for updates
gh issue view 45 --json comments --jq '
  .comments[] | select(.body | contains("AI-CONTEXT:START")) | .id
'
```

***REMOVED******REMOVED******REMOVED*** Save Context

```bash
***REMOVED*** Create new context comment
gh issue comment 45 --body-file .ai-context.md

***REMOVED*** Update existing (replace COMMENT_ID)
gh api repos/:owner/:repo/issues/comments/COMMENT_ID \
  --method PATCH -f body="$(cat .ai-context.md)"
```

***REMOVED******REMOVED******REMOVED*** Context Template

See `references/context-template.md` for full template. Minimal version:

```markdown
<!-- AI-CONTEXT:START -->
***REMOVED******REMOVED*** Context | IN_PROGRESS
**Files:** `file.py:45`, `other.py:120`
**Done:** task1, task2
**Next:** next task
**Resume:** One-line summary for cold start
<!-- AI-CONTEXT:END -->
```

***REMOVED******REMOVED******REMOVED*** Workflow

1. **Start work** — load context from issue
2. **Work on task** — track progress mentally
3. **Pause/Stop** — save context to issue comment
4. **Resume later** — load context, continue

***REMOVED******REMOVED*** Task Workflow

Manage issue lifecycle with labels.

***REMOVED******REMOVED******REMOVED*** Labels

| Label | Meaning |
|-------|---------|
| `backlog` | In queue |
| `in-progress` | Active work |
| `blocked` | Blocked |
| `review` | Needs review |

***REMOVED******REMOVED******REMOVED*** View Active Tasks

```bash
***REMOVED*** My active issues
gh issue list -l in-progress -s open

***REMOVED*** All my assigned issues
gh issue list --assignee @me -s open

***REMOVED*** Issues with context
gh issue list -s open --json number,title,labels --jq '
  .[] | select(.labels[].name == "in-progress") | "***REMOVED***\(.number): \(.title)"
'
```

***REMOVED******REMOVED******REMOVED*** Start Working

```bash
***REMOVED*** Mark as in-progress
gh issue edit 45 --add-label in-progress --remove-label backlog

***REMOVED*** View issue + load context
gh issue view 45 --json number,title,body,comments --jq '{
  number, title, body,
  context: (.comments[] | select(.body | contains("AI-CONTEXT")) | .body) // "No context"
}'
```

***REMOVED******REMOVED******REMOVED*** Pause/Block

```bash
***REMOVED*** Mark as blocked
gh issue edit 45 --add-label blocked --remove-label in-progress

***REMOVED*** Add blocking comment
gh issue comment 45 --body "Blocked: waiting for API access"
```

***REMOVED******REMOVED******REMOVED*** Complete

```bash
***REMOVED*** Close with comment
gh issue close 45 -c "Done in commit abc123"

***REMOVED*** Or close via PR (auto-closes if PR body contains "Fixes ***REMOVED***45")
```

***REMOVED******REMOVED*** Examples

***REMOVED******REMOVED******REMOVED*** Create Issue for Task

```bash
gh issue create -t "Simplify bot flow" -b "***REMOVED******REMOVED*** Problem
Bot stopped converting. Current flow is complex.

***REMOVED******REMOVED*** Reference
Simple flow example from competitor.

***REMOVED******REMOVED*** Tasks
- [ ] Analyze current flow
- [ ] Create new diagram
- [ ] Implement"
```

***REMOVED******REMOVED******REMOVED*** Start Working on Issue

```bash
***REMOVED*** 1. View issue with context
gh issue view 45 --json number,title,body,comments --jq '{
  number, title, body,
  context: (.comments[] | select(.body | contains("AI-CONTEXT")) | .body) // "No context"
}'

***REMOVED*** 2. Create branch
gh issue develop 45 --checkout

***REMOVED*** 3. Work...
```

***REMOVED******REMOVED******REMOVED*** Save Progress Before Stopping

```bash
***REMOVED*** Create context file
cat > .ai-context.md << 'EOF'
<!-- AI-CONTEXT:START -->
***REMOVED******REMOVED*** AI Session Context
_Last updated: 2026-01-07 16:00_

***REMOVED******REMOVED******REMOVED*** Status
**IN_PROGRESS**

***REMOVED******REMOVED******REMOVED*** Progress
- [x] Analyzed current flow
- [ ] Create new diagram

***REMOVED******REMOVED******REMOVED*** Key Files
- `handlers/start.py:45-78` — start handler
- `data/courses.yaml` — config

***REMOVED******REMOVED******REMOVED*** Next Steps
1. Draw simplified flow
2. Implement changes

***REMOVED******REMOVED******REMOVED*** Resume Context
Simplifying bot flow. Analyzed current state. Next: create diagram.
<!-- AI-CONTEXT:END -->
EOF

***REMOVED*** Save to issue
gh issue comment 45 --body-file .ai-context.md
```

***REMOVED******REMOVED******REMOVED*** Resume Work

```bash
***REMOVED*** Load context
CONTEXT=$(gh issue view 45 --json comments --jq '
  .comments[] | select(.body | contains("AI-CONTEXT")) | .body
' 2>/dev/null)

echo "$CONTEXT"
***REMOVED*** Continue from where you left off...
```

***REMOVED******REMOVED*** Common Mistakes

| Mistake | Fix |
|---------|-----|
| Missing `--json` | Always `--json field1,field2` |
| Loop instead of multi-arg | `gh issue edit 1 2 3` |
| Using `grep` on output | Use `--jq` |
| Forgot `-s all` for closed | Default is open only |
| `{owner}/{repo}` in API | Use `:owner/:repo` |
| Duplicate context comments | Update existing, don't create new |
