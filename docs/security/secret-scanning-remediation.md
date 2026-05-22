# Secret scanning remediation runbook

**Last reviewed:** 2026-05-22
**Source artifacts:** `logs/SECRET-SCANNING-ADMIN-PACKET.audit.md`
**Alert count:** 7 open secret scanning alerts (all `publicly_leaked: true`)
**Providers affected:** OpenAI, Anthropic, Groq, Telegram

## Purpose and scope

This runbook documents the manual remediation procedure for GitHub secret
scanning alerts in this repository. The 7 open alerts block the public-release
security milestone and require admin-only, out-of-band actions before the GitHub
alerts can be dismissed.

This runbook is **read-only guidance** for an admin operator. It does not
automate any destructive actions and must not be interpreted as authorization
to execute provider-console, VPS, SSH, or cloud operations without explicit
admin approval.

See also:
- [public-release-secret-scan.md](public-release-secret-scan.md) — history
  rewrite policy and trufflehog verification for P0 public release.
- [no-patch-dependency-alerts.md](no-patch-dependency-alerts.md) — exposure
  assessment for open Dependabot alerts without upstream patches.

---

## Safe alert triage workflow

Use GitHub secret scanning metadata only. Never inspect, print, or log raw
secret values during triage.

### Step 1: Enumerate open alerts (safe fields only)

```bash
gh api repos/OWNER/REPO/secret-scanning/alerts --jq \
  '.[] | {number, secret_type: .secret_type_display_name, state,
           publicly_leaked, resolution,
           created_at}'
```

The output contains alert numbers, detector types, and timestamps. It does
**not** include raw secret values or token fragments.

### Step 2: Classify by provider category

Group alerts by the detector type (e.g., `openai_api_key`, `telegram_bot_token`,
`anthropic_api_key`, `groq_api_key`). Do not extract, log, or display the
detected value itself.

| Provider    | Detector type          | Rotation action             |
|-------------|------------------------|-----------------------------|
| OpenAI      | `openai_api_key`       | Rotate in OpenAI dashboard  |
| Anthropic   | `anthropic_api_key`    | Rotate in Anthropic console |
| Groq        | `groq_api_key`         | Rotate in Groq console      |
| Telegram    | `telegram_bot_token`   | Revoke via @BotFather       |

### Step 3: Identify affected files (safe metadata only)

```bash
gh api repos/OWNER/REPO/secret-scanning/alerts --jq \
  '.[] | {number, path: .first_location_detected.path,
           line: .first_location_detected.start_line}'
```

Use this metadata to check whether affected files still exist in the working
tree and whether the secret-bearing content has already been removed or
rewritten. Do not open the file to verify the raw secret value.

### Step 4: Check originating commit reachability

For each alert's `first_location_detected.commit_sha`, verify the commit is
unreachable from all current branches and tags:

```bash
for sha in <alert-commit-sha-list>; do
  echo -n "$sha: "
  git branch -a --contains $sha 2>/dev/null || echo "UNREACHABLE"
done
```

If any commit is reachable, the history has not been fully scrubbed (see
History scrub verification below).

---

## Provider rotation order

Rotate and revoke exposed keys **before** dismissing GitHub alerts or rewriting
history. Key rotation is the only action that neutralizes the public exposure;
history cleanup alone does not.

### Rotation sequence

| Order | Provider    | Notes                                                          |
|-------|-------------|----------------------------------------------------------------|
| 1     | Telegram    | Revoke via @BotFather; generates new token immediately.        |
| 2     | OpenAI      | Rotate in API keys dashboard; revoke the exposed key.          |
| 3     | Anthropic   | Rotate in console; revoke the exposed key.                     |
| 4     | Groq        | Rotate in console; revoke the exposed key.                     |

Rotate Telegram first because bot tokens grant the broadest immediate control
(message interception, chat control). Rotate other providers in any order.

### Rotation prerequisites

- Admin access to each provider console is required.
- Do **not** use a shared or CI-accessible machine for provider console access.
- Do **not** log new key values in shell history, chat transcripts, or shared
  files.
- After rotation, update environment variables in the deployment target (VPS,
  CI, local `.env`) with the new keys before dismissing GitHub alerts.

---

## History scrub verification checklist

After key rotation, verify that no secret-bearing commits remain reachable in
repository history.

### Verification checklist

- [ ] All originating commits for secret scanning alerts are unreachable from
      every branch and tag (`git branch -a --contains <sha>` returns empty).
- [ ] `./docs/security/verification-commands.sh post` passes — all post-filter
      pattern counts are zero.
- [ ] `trufflehog git file://"$PWD" --json --no-update --no-verification`
      returns zero findings (or only accepted false positives — see
      [public-release-secret-scan.md](public-release-secret-scan.md)).
- [ ] `trufflehog filesystem "$PWD" --json --no-update --no-verification`
      returns zero findings (or only accepted false positives).
- [ ] `git fsck --full` is clean.
- [ ] Any git stashes that contained pre-cleanup snapshots have been dropped
      (`git stash list` reviewed, `git stash drop` executed if necessary).
- [ ] The destination remote for any force-push is explicit and approved.
- [ ] Raw scanner output (trufflehog JSON, gitleaks reports) has been removed
      from disk after summarization.

### Filter-repo verification

If `git filter-repo` or BFG was used to scrub history, verify completeness with
the verification commands script in the rewritten clone:

```bash
./docs/security/verification-commands.sh post
```

The post-filter verification must pass with zero failures before proceeding to
alert dismissal.

---

## GitHub alert dismissal guidance

Dismiss alerts **only after** all provider keys have been rotated and history
scrub has been verified.

### Dismissal rules

| Rule                                                    | Rationale                                           |
|---------------------------------------------------------|-----------------------------------------------------|
| Dismiss as `revoked`, **not** `false_positive`          | These were real keys, publicly exposed.             |
| Dismiss as `revoked`, **not** `used_in_tests`           | Public exposure invalidates the test-use exemption. |
| Include a resolution comment referencing the audit date | Creates an audit trail for future reviewers.        |
| Dismiss all alerts in a single batch after verification | Prevents partial remediation state.                 |

### Batch dismissal command

```bash
gh api repos/OWNER/REPO/secret-scanning/alerts/ALERT_NUMBER \
  --method PATCH \
  -f state=resolved \
  -f resolution=revoked \
  -f resolution_comment="Key rotated. Commit removed from history. Post-rotation audit: $(date -I). See docs/security/secret-scanning-remediation.md."
```

Repeat for each alert number. Verify dismissal with:

```bash
gh api repos/OWNER/REPO/secret-scanning/alerts --jq '[.[] | select(.state=="open")] | length'
```

Expected result: `0`.

---

## Post-rotation smoke-test checklist

After rotating keys and updating environment variables, verify services still
function with the new keys.

### Smoke tests

- [ ] **Telegram bot**: responds to `/start` and processes a test query.
- [ ] **OpenAI API**: embedding generation and chat completion succeed (check
      Langfuse traces or run `make validate-traces-fast`).
- [ ] **Anthropic API**: any pipeline step using Anthropic models completes
      without authentication errors.
- [ ] **Groq API**: any pipeline step using Groq models completes without
      authentication errors.
- [ ] **CI pipeline**: the standard CI workflow passes with the new keys
      (if CI uses the same provider keys).
- [ ] **Local development**: `make sync` and `make test` pass with updated
      local environment variables.

### Failure response

If any smoke test fails with an authentication or authorization error:
1. Verify the new key value was copied correctly to the environment.
2. Verify the old key was revoked (not just rotated — a rotated key may still
   be valid for a grace period depending on the provider).
3. Check provider console for rate limits or key restrictions.
4. Do **not** revert to the old, exposed key.

---

## Do not rules

These rules are non-negotiable. Violating any of them re-exposes the repository
or its operators to credential compromise.

| # | Rule                                                                 | Rationale                                                                    |
|---|----------------------------------------------------------------------|------------------------------------------------------------------------------|
| 1 | **Do not print raw secret values** in logs, terminals, or reports.   | Re-exposes secrets that were already publicly leaked.                        |
| 2 | **Do not commit provider keys, token fragments, raw scanner JSON, or secret-scanning values** to the repository. | Committing these values creates new secret scanning alerts. |
| 3 | **Do not dismiss an alert as `false_positive` when the secret was real.** | Misclassification hides a real exposure from future reviewers.               |
| 4 | **Do not run destructive history commands in the primary worktree.** | Use an isolated clone for `git filter-repo`, BFG, or force-push operations.  |
| 5 | **Do not access VPS, SSH, cloud, or provider consoles without explicit admin approval.** | Unauthorized access to production infrastructure is outside this runbook's scope. |
| 6 | **Do not run `git push --force` to a shared remote without explicit approval.** | Force-push invalidates all other clones and requires coordinated communication. |
| 7 | **Do not skip the post-rotation smoke tests.**                       | Rotated but untested keys can cause silent production failures.              |

---

## Issue references

The following GitHub issues track manual-control blockers related to secret
scanning remediation. All require admin actions before the public-release
security milestone can be closed.

| Issue   | Description                                                              |
|---------|--------------------------------------------------------------------------|
| #1563   | Предпубликационный аудит: очистка репозитория (pre-publication audit)     |
| #1564   | Security audit: public GitHub release readiness                          |
| #1576   | Remove vulnerability report and VPS infrastructure details               |
| #1578   | Secret scanning alert remediation tracking                               |
| #1580   | Git history contains sensitive data — filter-repo cleanup                |
| #1982   | Security public release history scrub force-push review                  |

These issues should be updated as each step in this runbook is completed:
provider rotation, history scrub verification, alert dismissal, and post-rotation
smoke testing.

---

## Related documentation

- [public-release-secret-scan.md](public-release-secret-scan.md) — History
  rewrite policy, trufflehog scan commands, accepted false positives, and
  publish gates.
- [no-patch-dependency-alerts.md](no-patch-dependency-alerts.md) — Exposure
  assessment for open Dependabot alerts without upstream patches.
- [verification-commands.sh](verification-commands.sh) — Pre/post-filter
  verification script for history scrub operations.
- [../runbooks/README.md](../runbooks/README.md) — Operational runbooks index for
  service health and incident response.
