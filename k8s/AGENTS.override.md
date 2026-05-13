# AGENTS.override.md

## Scope
- Applies to `k8s/**`.
- Extends root `AGENTS.md` with k8s-specific constraints.

## Local Rules
- Keep base manifests reusable and put deployment-mode differences in overlays.
- Respect namespace/label conventions defined in `k8s/base/kustomization.yaml`.
- Prefer overlays for `core`, `bot`, `ingest`, `full` deployment-mode differences.

## Required Validation
- Static inspection when a cluster is available:
  - `make k3s-status`
- For deployment changes, validate secrets and the target overlay:
  - `make k3s-secrets`
  - `make k3s-core` (or `make k3s-bot`, `make k3s-ingest`, `make k3s-full`)

## Guardrails
- Do not hardcode secrets.
- Do not remove PVC resources without an explicit migration plan.

## References
- `docs/LOCAL-DEVELOPMENT.md`
- `DOCKER.md`
- `k8s/base/kustomization.yaml`
