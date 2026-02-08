---
name: git-workflow-manager
description: Use when committing, releasing, or managing changelogs - enforces conventional commits, semantic versioning, and consistent release notes format
---

***REMOVED*** Git Workflow Manager

***REMOVED******REMOVED*** Overview

Enforces consistent git workflows: conventional commits, semantic versioning, changelog updates, and release notes format.

***REMOVED******REMOVED*** Commit Convention

```
<type>: <description>
```

| Type | Description | Version Bump |
|------|-------------|--------------|
| `feat` | New feature | MINOR |
| `fix` | Bug fix | PATCH |
| `docs` | Documentation | — |
| `refactor` | Code change | — |
| `chore` | Maintenance | — |

Breaking change: `feat!:` or `fix!:` → MAJOR

***REMOVED******REMOVED*** Version Bump Rules

```
Current: 1.2.3

feat:     → 1.3.0 (MINOR)
fix:      → 1.2.4 (PATCH)
feat!:    → 2.0.0 (MAJOR)
docs:     → no bump
```

***REMOVED******REMOVED*** Workflow: Commit

```bash
***REMOVED*** 1. Stage changes
git add .

***REMOVED*** 2. Commit with conventional message
git commit -m "feat: add new feature"

***REMOVED*** 3. For multi-line:
git commit -m "$(cat <<'EOF'
feat: add feature

Detailed description here.
EOF
)"
```

***REMOVED******REMOVED*** Workflow: Release

```bash
***REMOVED*** 1. Determine version bump from commits since last tag
git log $(git describe --tags --abbrev=0)..HEAD --oneline

***REMOVED*** 2. Update CHANGELOG.md
***REMOVED*** - Move [Unreleased] items to new version section
***REMOVED*** - Add date: [1.3.0] - YYYY-MM-DD

***REMOVED*** 3. Commit changelog
git add CHANGELOG.md
git commit -m "docs: update changelog for v1.3.0"

***REMOVED*** 4. Create tag
git tag -a v1.3.0 -m "Release v1.3.0"

***REMOVED*** 5. Push
git push && git push --tags

***REMOVED*** 6. Create GitHub release
gh release create v1.3.0 \
  --title "v1.3.0 — Short Description" \
  --notes-file /tmp/release-notes.md
```

***REMOVED******REMOVED*** Release Notes Template

```markdown
***REMOVED******REMOVED*** What's New

***REMOVED******REMOVED******REMOVED*** Feature Name
Brief description.

**Key points:**
- Point 1
- Point 2

***REMOVED******REMOVED******REMOVED*** Installation (if applicable)
\`\`\`bash
command here
\`\`\`

---

**Full Changelog**: https://github.com/USER/REPO/compare/vPREV...vNEW
```

***REMOVED******REMOVED*** CHANGELOG.md Format

```markdown
***REMOVED*** Changelog

***REMOVED******REMOVED*** [Unreleased]

***REMOVED******REMOVED*** [1.3.0] - 2025-12-17
***REMOVED******REMOVED******REMOVED*** Added
- Feature description

***REMOVED******REMOVED******REMOVED*** Changed
- Change description

***REMOVED******REMOVED******REMOVED*** Fixed
- Fix description

[Unreleased]: https://github.com/.../compare/v1.3.0...HEAD
[1.3.0]: https://github.com/.../compare/v1.2.0...v1.3.0
```

Sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`

***REMOVED******REMOVED*** Quick Commands

| Task | Command |
|------|---------|
| Last tag | `git describe --tags --abbrev=0` |
| Commits since tag | `git log $(git describe --tags --abbrev=0)..HEAD --oneline` |
| Create release | `gh release create vX.Y.Z --title "vX.Y.Z — Title"` |
| Edit release | `gh release edit vX.Y.Z --title "New Title" --notes "..."` |
| List releases | `gh release list` |

***REMOVED******REMOVED*** Common Mistakes

| Mistake | Fix |
|---------|-----|
| No conventional prefix | Always use `feat:`, `fix:`, etc. |
| Forgot CHANGELOG | Update before tagging |
| Tag without release | Always `gh release create` after tag |
| Inconsistent title | Format: `vX.Y.Z — Short Description` |
| Missing comparison link | Add `**Full Changelog**: compare/...` |
