***REMOVED*** Native Git/GitHub Hygiene

Native Git and GitHub CLI workflow for issue, PR, branch, worktree, and stash
hygiene. This replaces the archived legacy helpers under `scripts/archive/`.

***REMOVED******REMOVED*** Safety Rules

- Default base branch is `dev`; override with `REPO_BASE_BRANCH` or
  `MAIN_BRANCH` only when the target branch is explicit.
- Do not delete the current branch.
- Do not delete branches checked out in any worktree.
- Do not remove dirty worktrees with normal cleanup commands.
- Check open PRs before deleting remote branches.
- Use report/dry-run commands before destructive commands.
- For local branch deletion, select candidates from `origin/<base>`, re-check
  `git merge-base --is-ancestor <branch> origin/<base>`, then delete with
  `git branch -D`. Do not rely on `git branch -d`, because it checks merge
  safety against the current `HEAD`.

***REMOVED******REMOVED*** Weekly Report

```bash
BASE_BRANCH="${REPO_BASE_BRANCH:-dev}"

git fetch --all --prune --prune-tags

git for-each-ref \
  --format='%(refname:short)|%(upstream:short)|%(upstream:track)' \
  refs/heads

git branch --merged "origin/$BASE_BRANCH" --format='%(refname:short)'

git worktree list --porcelain

git ls-files --others --exclude-standard -- \
  coverage.json 'test_output*' '*.log'
```

***REMOVED******REMOVED*** PR And Issue Queue

```bash
gh pr list \
  --state open \
  --limit 200 \
  --json number,baseRefName,headRefName,mergeStateStatus,reviewDecision,isDraft,updatedAt

gh issue list \
  --state open \
  --limit 200 \
  --json number,title,labels,assignees,updatedAt
```

Triage order:

1. `CLEAN` and approved.
2. `CLEAN` and `REVIEW_REQUIRED` older than 48h.
3. Blocked checks or conflicts.
4. Drafts.

***REMOVED******REMOVED*** Cleanup Preview

```bash
MAIN_BRANCH="${MAIN_BRANCH:-dev}"
BASE_REF="origin/$MAIN_BRANCH"
CURRENT_BRANCH="$(git branch --show-current)"
WORKTREE_BRANCHES="$(git worktree list --porcelain | sed -n 's/^branch refs\/heads\///p')"

git fetch --prune origin
git rev-parse --verify --quiet "$BASE_REF" >/dev/null

git branch --merged "$BASE_REF" --format='%(refname:short)' |
while read -r branch; do
  [ -z "$branch" ] && continue
  [ "$branch" = "$MAIN_BRANCH" ] && continue
  [ "$branch" = "main" ] && continue
  [ "$branch" = "master" ] && continue
  [ "$branch" = "develop" ] && continue
  [ "$branch" = "$CURRENT_BRANCH" ] && continue
  printf '%s\n' "$WORKTREE_BRANCHES" | grep -Fxq "$branch" && continue
  printf 'local merged branch: %s\n' "$branch"
done

git branch -r --merged "origin/$MAIN_BRANCH" --format='%(refname:short)' |
sed 's|^origin/||' |
while read -r branch; do
  [ -z "$branch" ] && continue
  [ "$branch" = "$MAIN_BRANCH" ] && continue
  [ "$branch" = "main" ] && continue
  [ "$branch" = "master" ] && continue
  [ "$branch" = "develop" ] && continue
  open_prs="$(gh pr list --head "$branch" --state open --json number --jq length 2>/dev/null || echo unknown)"
  printf 'remote merged branch: %s open_prs=%s\n' "$branch" "$open_prs"
done

git worktree prune --dry-run
git stash list
```

***REMOVED******REMOVED*** Destructive Cleanup

Prefer `make repo-cleanup-force`, which keeps the safety filters in one place.
For manual native cleanup:

```bash
MAIN_BRANCH="${MAIN_BRANCH:-dev}"
BASE_REF="origin/$MAIN_BRANCH"
CURRENT_BRANCH="$(git branch --show-current)"
WORKTREE_BRANCHES="$(git worktree list --porcelain | sed -n 's/^branch refs\/heads\///p')"

git fetch --prune origin
git rev-parse --verify --quiet "$BASE_REF" >/dev/null

git branch --merged "$BASE_REF" --format='%(refname:short)' |
while read -r branch; do
  [ -z "$branch" ] && continue
  [ "$branch" = "$MAIN_BRANCH" ] && continue
  [ "$branch" = "main" ] && continue
  [ "$branch" = "master" ] && continue
  [ "$branch" = "develop" ] && continue
  [ "$branch" = "$CURRENT_BRANCH" ] && continue
  printf '%s\n' "$WORKTREE_BRANCHES" | grep -Fxq "$branch" && continue
  git merge-base --is-ancestor "$branch" "$BASE_REF" && git branch -D "$branch"
done

git worktree prune
```

Remote branch deletion must be branch-by-branch after confirming there is no
open PR:

```bash
branch="feature/example"
gh pr list --head "$branch" --state open --json number --jq length
git push origin --delete "$branch"
```
