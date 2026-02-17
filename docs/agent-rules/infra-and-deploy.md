***REMOVED*** Infrastructure And Deployment

***REMOVED******REMOVED*** Local Compose Profiles
- Core services: `make docker-up`
- Core + bot path: `make docker-bot-up`
- Full stack: `make docker-full-up`

Use profile-specific startup where needed for faster feedback loops.

***REMOVED******REMOVED*** k3s Deployment Path
Primary commands:
- `make k3s-secrets`
- `make k3s-core`
- `make k3s-bot`
- `make k3s-ingest`
- `make k3s-full`
- `make k3s-status`
- `make k3s-logs SVC=<name>`
- `make k3s-down`

***REMOVED******REMOVED*** Deployment Guardrails
- Keep secrets outside committed manifests.
- Preserve PVC/data migration intent when changing storage resources.
- Prefer overlays for environment-specific behavior; keep base reusable.

***REMOVED******REMOVED*** Runtime Services (Common)
- Redis, Qdrant, LiteLLM, Langfuse, Docling, BGE-M3.
- Optional voice stack uses LiveKit/SIP and API bridge services.

***REMOVED******REMOVED*** Operations References
- `AGENTS.md`
- `docs/agent-rules/workflow.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/QDRANT_STACK.md`
- `docs/ALERTING.md`
