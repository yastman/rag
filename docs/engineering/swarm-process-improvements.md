# Historical Swarm Deploy Process Improvements

## Issue

CI/CD deploy reliability suffered from several brittle defaults that made
production pushes risky and slow to debug.

This note is historical. Public repository hardening removed VPS deploy scripts
and internal deploy workflow wiring from the public tree. Keep future public
docs focused on local/test validation contracts.

## Changes

### CI deploy job (`ci.yml`)

- **Timeout increased** from 10 to 15 minutes to accommodate slower VPS builds.
- **BuildKit enabled** with `DOCKER_BUILDKIT=1` and `BUILDKIT_INLINE_CACHE=1` for faster incremental builds.
- **Health-driven wait** replaces fixed `sleep 20`; `docker compose up -d --wait` blocks until services report healthy.
- **Dirty-tree guard** stashes local VPS changes before `git reset --hard`, protecting manual hotfixes from accidental loss.
- **Production env validation** remains mandatory before `docker compose build`.

### Local deploy script

- The internal manual VPS deploy script is no longer shipped in the public
  repository.
- Public CI and docs must not expose VPS hostnames, SSH wiring, or deploy
  secrets.

### Image publishing (`publish-internal-images.yml`)

- **Semver major/minor tags** already present via `docker/metadata-action`.
- **SBOM and provenance** enabled on `docker/build-push-action` for supply-chain visibility.
- **GHA cache** unchanged (`type=gha`); provenance/SBOM are additive.

## Testing

Static unit tests assert the public-safe behavior by parsing workflow YAML and
remaining public release-gate scripts:

- `tests/unit/test_ci_deploy_workflow.py`
- `tests/unit/test_release_gate_contract.py`

These tests do not require live Docker builds or VPS access.

## Related

- Fixes #1244
