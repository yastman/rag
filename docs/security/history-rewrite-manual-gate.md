# History Rewrite Manual Gate

**Last reviewed:** 2026-05-25
**Scope:** security issues #1563, #1564, #1576, #1578, #1579, #1580, #1982, #2043
**Status:** manual approval required

This runbook is the operator checklist for the final public-release security
gate. It consolidates the accepted secret inventory, filter-repo pattern draft,
collaborator notification draft, and git history audit.

Do not paste raw secret values into this file, GitHub issues, PRs, logs, or
chat. Use provider consoles and local private notes for exact values.

## Stop Conditions

Stop immediately and do not force-push when any of these conditions is true:

- Any provider key has not been rotated or revoked.
- The replace-text file still contains unresolved placeholders.
- The fresh ref baseline was not captured immediately before rewrite.
- Any post-rewrite scanner reports a real finding.
- A collaborator reports unpreserved work during the rewrite window.
- GitHub branch protection blocks the intended force-push target.

## Accepted Inputs

These inputs were accepted as read-only advisory artifacts:

| Input | Purpose |
|-------|---------|
| `REPORT.secret-inventory-filter-repo.md` | Redacted secret inventory, rotation list, and closure matrix |
| `REPORT.draft-filter-repo-patterns.md` | Draft path deletion list and replace-text pattern package |
| `REPORT.draft-collaborator-notification.md` | Pre/post rewrite collaborator notices and issue templates |
| `REPORT.audit-git-history-secrets.md` | Commit/file/pattern inventory and post-rewrite verification targets |

The worker reports are leads, not authorization. The operator must repeat the
verification commands in a fresh clone before running destructive commands.

## Manual Gate Checklist

### 1. Provider Rotation

- [ ] Rotate or revoke the Telegram bot token in @BotFather.
- [ ] Rotate or revoke every provider API key that GitHub secret scanning
      classified as publicly exposed.
- [ ] Update deployment, CI, and local environments with replacement keys.
- [ ] Smoke-test the services that depend on the rotated keys.
- [ ] Record only provider, date, and owner in GitHub. Do not record values.

### 2. Local Secret Relocation

- [ ] Move real `.env`, `.env.local`, and `.mcp.json` files out of repo working
      directories.
- [ ] Keep replacement local files under a private path outside this repository.
- [ ] Confirm `.gitignore` still blocks these files.
- [ ] Run `uv run pre-commit run gitleaks --all-files` from a clean working
      tree.

### 3. Pattern Approval

- [ ] Copy `docs/security/filter-repo-patterns.txt` to a private, uncommitted
      replace-text file.
- [ ] Substitute all placeholders with exact values in the private file.
- [ ] Add the history-audit pattern classes that are not already covered:
      public VPS IP, private domain variants, deployment user/path patterns,
      Telegram token format, provider key prefixes, and old project codename.
- [ ] Test each pattern with `git log --all -G '<regex>'` or an equivalent
      dry-run search.
- [ ] Confirm each pattern matches only intended content.

### 4. Fresh Clone And Baseline

Run the rewrite only in a fresh clone or mirror, never in the main working
tree.

```bash
git clone --mirror git@github.com:OWNER/REPO.git repo-pre-rewrite-backup.git
git clone git@github.com:OWNER/REPO.git repo-rewrite
cd repo-rewrite
git fetch --all --tags --prune

git branch -a > ../pre-rewrite-branches.txt
git tag > ../pre-rewrite-tags.txt
git rev-parse origin/dev > ../pre-rewrite-origin-dev.txt
git rev-parse origin/main > ../pre-rewrite-origin-main.txt
```

Before continuing, compare this baseline with the latest GitHub branch state.
Branch counts can drift while PRs are active, so do not reuse stale counts from
old audit reports.

### 5. History Rewrite

This command block is a template. Review every path and pattern before use.

```bash
# Prevent accidental push during local rewrite.
git remote remove origin

# Pass 1: delete sensitive historical files.
git filter-repo \
  --path docs/plans/2026-02-02-extended-alerting.md \
  --path deploy/telegram-bot.service \
  --path deploy/sudoers-telegram-bot \
  --path tests/unit/scripts/test_deploy_vps.py \
  --path docs/runbooks/vps-gdrive-ingestion-recovery.md \
  --invert-paths

# Pass 2: replace sensitive strings in remaining text history.
git filter-repo --replace-text ../private-filter-repo-patterns.txt --force

# Drop unreachable objects left by the rewrite.
git reflog expire --expire=now --all
git gc --aggressive --prune=now
```

Do not run this block until provider rotation and pattern approval are complete.

### 6. Post-Rewrite Verification

All checks must pass in the rewritten clone before any force-push:

```bash
./docs/security/verification-commands.sh post

gitleaks detect --source . --verbose
gitleaks detect --source . --verbose --no-git

trufflehog git file://"$PWD" --json --no-update --no-verification
trufflehog filesystem "$PWD" --json --no-update --no-verification

git fsck --full
git fsck --unreachable --no-reflogs
git log --all -- docs/plans/2026-02-02-extended-alerting.md
git log --all -S 'contextual_rag'
```

Expected result:

- zero real scanner findings;
- zero sensitive path deletion targets remaining in history;
- zero old codename matches, unless explicitly accepted as non-sensitive;
- zero known token-bearing unreachable objects after garbage collection;
- branch and tag baselines match expected rewrite targets.

### 7. Force-Push Approval

Force-push is manual-only and requires explicit owner approval after the
post-rewrite verification evidence is captured.

Before force-push:

- [ ] Notify collaborators and freeze merges.
- [ ] Confirm target branches and protected branch settings.
- [ ] Re-add the approved remote explicitly.
- [ ] Paste only verification summaries into GitHub, never raw scanner output.

After approval, the owner executes the chosen push plan. If branch protection
blocks a target, stop and resolve protection settings intentionally.

### 8. GitHub Hosted Cleanup

- [ ] Request GitHub Support cache invalidation for removed sensitive commits.
- [ ] Confirm old pull-request refs and stale remote branches do not expose
      pre-rewrite history.
- [ ] Run secret scans from a fresh clone of the GitHub-hosted repository.
- [ ] Dismiss GitHub secret scanning alerts only as `revoked` after rotation
      and verification.

## GitHub Issue Status Template

Use this template for the eight open security issues after each major gate.
Do not close the issues until the closure criteria below are satisfied.

```markdown
## Manual security gate update - YYYY-MM-DD

Status:
- provider rotation: <pending|complete>
- filter-repo pattern approval: <pending|complete>
- history rewrite: <not started|complete>
- force-push: <not started|complete>
- GitHub cache invalidation: <not requested|requested|complete>
- fresh-clone secret scan: <pending|passed|failed>

Verification summary:
- gitleaks: <pending|passed|failed>
- trufflehog git scan: <pending|passed|failed>
- trufflehog filesystem scan: <pending|passed|failed>
- git fsck: <pending|passed|failed>
- branch/tag baseline: <pending|matched|mismatch>

This issue remains open under manual control until all public-release security
gates are complete. No raw secret values are included in this update.
```

## Closure Criteria

| Issue | Close only after |
|-------|------------------|
| #1563 | Full public-release audit passes and no manual security gate remains |
| #1564 | GitHub-hosted fresh clone passes secret scanning and public-release checks |
| #1576 | Vulnerability report and infrastructure details are absent from reachable history and GitHub caches |
| #1578 | Dev credentials/business data are either public-safe or removed/sanitized |
| #1579 | Internal runbooks and architecture docs are classified public-safe or sanitized |
| #1580 | History rewrite, garbage collection, force-push, cache invalidation, and fresh scans pass |
| #1982 | Force-push review is complete and collaborator migration has been communicated |
| #2043 | No-patch Dependabot alerts have documented risk acceptance or upstream fixes |

Close issues one by one with evidence links. Do not batch-close them based on
the local rewrite alone.

## Related Docs

- [Secret Scanning Runbook](secret-scanning-runbook.md)
- [Secret Scanning Remediation](secret-scanning-remediation.md)
- [Public Release Secret Scan](public-release-secret-scan.md)
- [Filter-Repo Pattern Template](filter-repo-patterns.txt)
- [Verification Commands](verification-commands.sh)
