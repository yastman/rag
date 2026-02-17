# AGENTS.override.md

## Scope
- Applies to `k8s/**`.
- Extends root `AGENTS.md` with k3s deployment constraints.

## Local Rules
- Keep base manifests reusable; environment-specific differences go to overlays.
- Respect existing namespace and labeling conventions.
- Prefer changing overlays for deployment-mode differences (`core`, `bot`, `ingest`, `full`).

## Required Validation
- Static inspection after edits:
  - `make k3s-status` (when cluster available)
- For deployment changes, validate target flow:
  - `make k3s-secrets`
  - `make k3s-core` or `make k3s-bot`/`make k3s-ingest`/`make k3s-full`

## Guardrails
- Do not hardcode secrets in manifests.
- Do not remove PVC-related resources without explicit migration plan.

## References
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/agent-rules/infra-and-deploy.md`
- `k8s/base/kustomization.yaml`
