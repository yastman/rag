***REMOVED*** ADR-0011: Docker Compose as Primary Runtime

**Status:** Accepted

**Date:** 2025-05-21

***REMOVED******REMOVED*** Context

The platform needed a reproducible, developer-friendly runtime for local development, CI, and VPS deployment. The service set includes PostgreSQL, Redis, Qdrant, BGE-M3, Docling, LiteLLM, Langfuse, Loki, and the application containers (bot, ingestion, RAG API). We evaluated several approaches:

1. **Docker Compose** - Declarative multi-container orchestration with profile-based layering
2. **Bare-metal scripts** - Direct host installation with shell-based service management
3. **Full Kubernetes (k8s/k3s)** - Container orchestration with auto-scaling and rolling updates
4. **HashiCorp Nomad** - Lightweight orchestrator with job-based scheduling
5. **Nix / devcontainers** - Reproducible dev environments via functional package manager or containerized IDEs

***REMOVED******REMOVED*** Decision

We chose **Docker Compose** as the primary local and VPS runtime with profile-based service layering.

***REMOVED******REMOVED******REMOVED*** Why Docker Compose

1. **One-command local setup** - `docker compose up` brings the full stack or a targeted subset online instantly
2. **Profile-based isolation** - Profiles (core, bot, ingest, ml, obs, voice, full) let developers run only the services they need, reducing resource usage
3. **Same tooling local and VPS** - Identical Compose files run on developer laptops and production VPS with minimal override differences
4. **Declarative service dependencies** - Health checks, depends_on, and restart policies are defined once in YAML
5. **Ecosystem maturity** - Wide adoption, excellent documentation, and broad IDE support for debugging

***REMOVED******REMOVED******REMOVED*** Why Not Others

| Approach | Reason Rejected |
|----------|----------------|
| Bare-metal scripts | Fragile, no isolation between services, hard to reproduce across machines |
| Full Kubernetes | Too complex for solo/small-team development; operational overhead not justified at current scale |
| Nomad | Smaller ecosystem and community; less tooling integration than Compose |
| Nix / devcontainers | Less production parity; does not solve multi-service orchestration for deployment |

***REMOVED******REMOVED*** Consequences

***REMOVED******REMOVED******REMOVED*** Positive
- One-command local setup for any profile combination
- Profile isolation reduces resource usage on developer machines
- Same Compose tooling used local and on VPS
- Declarative service dependencies with health checks and restart policies
- Makefile wraps common Compose commands for discoverability

***REMOVED******REMOVED******REMOVED*** Negative
- Compose limits: no auto-scaling, no rolling updates without extra tooling
- Partial k3s manifests needed if scaling to production clusters in the future
- Profile combinatorics can confuse newcomers unfamiliar with Compose profiles
- Override file layering (base + dev + vps) adds indirection

***REMOVED******REMOVED*** Implementation

- `compose.yml` provides the secure baseline with all services defined and profile-gated
- `compose.dev.yml` adds local development overrides (port exposure, volume mounts, debug flags)
- `compose.vps.yml` adds production overrides (resource limits, external networks, TLS)
- Profiles: `core` (default: PostgreSQL, Redis, Qdrant), `bot`, `ingest`, `ml`, `obs`, `voice`, `full`
- `COMPOSE_PROJECT_NAME=dev` convention for consistent container naming
- `Makefile` wraps common Compose commands: `docker-up`, `docker-bot-up`, `docker-full-up`, `local-up`

***REMOVED******REMOVED*** References

- [DOCKER.md](../../DOCKER.md) - Full service/port/env map and profile matrix
- [docs/LOCAL-DEVELOPMENT.md](../LOCAL-DEVELOPMENT.md) - Developer workflow and local setup
