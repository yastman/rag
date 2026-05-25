# Secret Scanning Runbook

Use this runbook when CI, GitHub Secret Scanning, gitleaks, or a local audit
reports a possible secret.

## Gates

1. **Scan**
   - CI runs the `Secret Scan` job with full Git history checkout.
   - Local quick check: `uv run pre-commit run gitleaks --all-files`.
   - History check: run gitleaks against a fresh clone when investigating old
     commits.

2. **Inventory**
   - Record the provider, secret type, path, commit, current status, and owner.
   - Do not paste secret values into issues, PRs, logs, or docs.
   - Classify each finding as `true_positive`, `false_positive`, or
     `test_fixture`.

3. **Rotate Or Revoke**
   - Rotate or revoke true positives at the provider before any history rewrite.
   - Treat unknown validity as active until the provider confirms otherwise.

4. **Decide On History Rewrite**
   - Use `git-filter-repo --sensitive-data-removal` only after explicit human
     approval.
   - Run history rewrite in a fresh clone.
   - Coordinate force-push timing with collaborators.

5. **Verify**
   - Re-scan the rewritten repository before force-push.
   - After force-push, verify a fresh clone and the GitHub security alerts.
   - Request GitHub cache or pull-request ref cleanup if sensitive data remains
     reachable through GitHub-hosted refs or cached views.

## Tooling

- **GitHub Secret Scanning + Push Protection**: central alerting and push-time
  blocking. Enable it in repository settings when available.
- **Gitleaks**: local pre-commit and CI scanner.
- **TruffleHog**: optional second scanner for verified-secret checks.
- **detect-secrets**: optional baseline/audit helper for large triage efforts.
- **git-filter-repo**: manual-only history rewrite tool.

## Do Not Automate

- Force-push rewritten history.
- Rotate provider credentials.
- Move or inspect real local `.env` / `.mcp.json` files without explicit human
  approval.
- Paste raw secret values into GitHub, logs, reports, or chat.
