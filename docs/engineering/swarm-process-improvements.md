# Swarm Deploy Process Improvements

## Issue

CI/CD deploy reliability suffered from several brittle defaults that made production pushes risky and slow to debug.

## Changes

### CI deploy job (`ci.yml`)

- **Timeout increased** from 10 to 15 minutes to accommodate slower VPS builds.
- **BuildKit enabled** with `DOCKER_BUILDKIT=1` and `BUILDKIT_INLINE_CACHE=1` for faster incremental builds.
- **Health-driven wait** replaces fixed `sleep 20`; `docker compose up -d --wait` blocks until services report healthy.
- **Dirty-tree guard** stashes local VPS changes before `git reset --hard`, protecting manual hotfixes from accidental loss.
- **Production env validation** remains mandatory before `docker compose build`.

### Local deploy script (`scripts/deploy-vps.sh`)

- **Connection params are env-driven** (`VPS_HOST`, `VPS_PORT`, `VPS_USER`, `VPS_KEY`) with clear failures when required vars are missing.
- **Safer SSH defaults** replace `StrictHostKeyChecking=no` with `accept-new` (configurable via `VPS_SSH_STRICT_HOST_KEY_CHECKING`).
- **No hardcoded IPs, ports, users, or key paths** remain in the script.

### Image publishing (`publish-internal-images.yml`)

- **Semver major/minor tags** already present via `docker/metadata-action`.
- **SBOM and provenance** enabled on `docker/build-push-action` for supply-chain visibility.
- **GHA cache** unchanged (`type=gha`); provenance/SBOM are additive.

## Testing

Static unit tests assert each behavior by parsing workflow YAML and the deploy script:

- `tests/unit/test_ci_deploy_workflow.py`
- `tests/unit/scripts/test_deploy_vps.py`
- `tests/unit/test_publish_internal_images_workflow.py`

These tests do not require live Docker builds or VPS access.

## Related

- Fixes #1244
