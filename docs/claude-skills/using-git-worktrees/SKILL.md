---
name: using-git-worktrees
description: Use when starting feature work that needs isolation from current workspace or before executing implementation plans - creates isolated git worktrees with smart directory selection and safety verification
---

***REMOVED*** Using Git Worktrees

***REMOVED******REMOVED*** Overview

Git worktrees create isolated workspaces sharing the same repository, allowing work on multiple branches simultaneously without switching.

**Core principle:** Systematic directory selection + safety verification = reliable isolation.

**Announce at start:** "I'm using the using-git-worktrees skill to set up an isolated workspace."

***REMOVED******REMOVED*** Directory Selection Process

Follow this priority order:

***REMOVED******REMOVED******REMOVED*** 1. Check Existing Directories

```bash
***REMOVED*** Check in priority order
ls -d .worktrees 2>/dev/null     ***REMOVED*** Preferred (hidden)
ls -d worktrees 2>/dev/null      ***REMOVED*** Alternative
```

**If found:** Use that directory. If both exist, `.worktrees` wins.

***REMOVED******REMOVED******REMOVED*** 2. Check CLAUDE.md

```bash
grep -i "worktree.*director" CLAUDE.md 2>/dev/null
```

**If preference specified:** Use it without asking.

***REMOVED******REMOVED******REMOVED*** 3. Ask User

If no directory exists and no CLAUDE.md preference:

```
No worktree directory found. Where should I create worktrees?

1. .worktrees/ (project-local, hidden)
2. ~/.config/superpowers/worktrees/<project-name>/ (global location)

Which would you prefer?
```

***REMOVED******REMOVED*** Safety Verification

***REMOVED******REMOVED******REMOVED*** For Project-Local Directories (.worktrees or worktrees)

**MUST verify directory is ignored before creating worktree:**

```bash
***REMOVED*** Check if directory is ignored (respects local, global, and system gitignore)
git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

**If NOT ignored:**

Per Jesse's rule "Fix broken things immediately":
1. Add appropriate line to .gitignore
2. Commit the change
3. Proceed with worktree creation

**Why critical:** Prevents accidentally committing worktree contents to repository.

***REMOVED******REMOVED******REMOVED*** For Global Directory (~/.config/superpowers/worktrees)

No .gitignore verification needed - outside project entirely.

***REMOVED******REMOVED*** Creation Steps

***REMOVED******REMOVED******REMOVED*** 1. Detect Project Name

```bash
project=$(basename "$(git rev-parse --show-toplevel)")
```

***REMOVED******REMOVED******REMOVED*** 2. Create Worktree

```bash
***REMOVED*** Determine full path
case $LOCATION in
  .worktrees|worktrees)
    path="$LOCATION/$BRANCH_NAME"
    ;;
  ~/.config/superpowers/worktrees/*)
    path="~/.config/superpowers/worktrees/$project/$BRANCH_NAME"
    ;;
esac

***REMOVED*** Create worktree with new branch
git worktree add "$path" -b "$BRANCH_NAME"
cd "$path"
```

***REMOVED******REMOVED******REMOVED*** 3. Run Project Setup

Auto-detect and run appropriate setup:

```bash
***REMOVED*** Node.js
if [ -f package.json ]; then npm install; fi

***REMOVED*** Rust
if [ -f Cargo.toml ]; then cargo build; fi

***REMOVED*** Python
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
if [ -f pyproject.toml ]; then poetry install; fi

***REMOVED*** Go
if [ -f go.mod ]; then go mod download; fi
```

***REMOVED******REMOVED******REMOVED*** 4. Verify Clean Baseline

Run tests to ensure worktree starts clean:

```bash
***REMOVED*** Examples - use project-appropriate command
npm test
cargo test
pytest
go test ./...
```

**If tests fail:** Report failures, ask whether to proceed or investigate.

**If tests pass:** Report ready.

***REMOVED******REMOVED******REMOVED*** 5. Report Location

```
Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

***REMOVED******REMOVED*** Quick Reference

| Situation | Action |
|-----------|--------|
| `.worktrees/` exists | Use it (verify ignored) |
| `worktrees/` exists | Use it (verify ignored) |
| Both exist | Use `.worktrees/` |
| Neither exists | Check CLAUDE.md → Ask user |
| Directory not ignored | Add to .gitignore + commit |
| Tests fail during baseline | Report failures + ask |
| No package.json/Cargo.toml | Skip dependency install |

***REMOVED******REMOVED*** Common Mistakes

***REMOVED******REMOVED******REMOVED*** Skipping ignore verification

- **Problem:** Worktree contents get tracked, pollute git status
- **Fix:** Always use `git check-ignore` before creating project-local worktree

***REMOVED******REMOVED******REMOVED*** Assuming directory location

- **Problem:** Creates inconsistency, violates project conventions
- **Fix:** Follow priority: existing > CLAUDE.md > ask

***REMOVED******REMOVED******REMOVED*** Proceeding with failing tests

- **Problem:** Can't distinguish new bugs from pre-existing issues
- **Fix:** Report failures, get explicit permission to proceed

***REMOVED******REMOVED******REMOVED*** Hardcoding setup commands

- **Problem:** Breaks on projects using different tools
- **Fix:** Auto-detect from project files (package.json, etc.)

***REMOVED******REMOVED*** Example Workflow

```
You: I'm using the using-git-worktrees skill to set up an isolated workspace.

[Check .worktrees/ - exists]
[Verify ignored - git check-ignore confirms .worktrees/ is ignored]
[Create worktree: git worktree add .worktrees/auth -b feature/auth]
[Run npm install]
[Run npm test - 47 passing]

Worktree ready at /Users/jesse/myproject/.worktrees/auth
Tests passing (47 tests, 0 failures)
Ready to implement auth feature
```

***REMOVED******REMOVED*** Red Flags

**Never:**
- Create worktree without verifying it's ignored (project-local)
- Skip baseline test verification
- Proceed with failing tests without asking
- Assume directory location when ambiguous
- Skip CLAUDE.md check

**Always:**
- Follow directory priority: existing > CLAUDE.md > ask
- Verify directory is ignored for project-local
- Auto-detect and run project setup
- Verify clean test baseline

***REMOVED******REMOVED*** Integration

**Called by:**
- **brainstorming** (Phase 4) - REQUIRED when design is approved and implementation follows
- Any skill needing isolated workspace

**Pairs with:**
- **finishing-a-development-branch** - REQUIRED for cleanup after work complete
- **executing-plans** or **subagent-driven-development** - Work happens in this worktree
