# Project contract

## Goal

Provide a self-hosted assistant that answers from an operator's document corpus and
supports concrete product actions through Telegram. The shipped domain is real estate:
apartment discovery, service information, viewing requests, and manager contact.
The shared RAG engine still contains domain defaults; replacing the domain requires
reviewing those owners as well as UI and product services.

## Accepted baseline

- A Python modular monolith: Telegram process assembly calls an in-process assistant core.
- A transport-free request/result API in src/core; procedural execution in src/runtime.
  See the [accepted core-path decision](docs/adr/0019-core-text-path-procedural-runtime.md).
- Qdrant retrieval with dense, sparse, and ColBERT representations from the BGE-M3 sidecar.
  Redis provides caches and runtime coordination.
- Docker Compose owns sidecar deployment. PostgreSQL is opt-in for persistent product state;
  dependent UI capabilities follow configuration/readiness.
- Unified document ingestion accepts Markdown. Apartment data has its own ingestion path.
- Root pyproject.toml/uv.lock own application and Telegram dependencies. The BGE image has
  its own service-local manifest and lock.

These are implementation boundaries, not a claim that all scenarios or release gates pass.
Use current tests, issue evidence, and runtime probes to establish readiness.

## Product surfaces

| Surface | Boundary |
| --- | --- |
| Grounded Q&A | Assistant request/result, retrieval, generation, citation policy |
| Apartment catalog | Product filters, catalog dialogs, apartment schema |
| Service cards and viewing requests | Product content and lead delivery |
| Manager handoff | Manager topics, session state, capability checks |
| Bookmarks/user state | Optional PostgreSQL-backed capability |
| Demo and voice-enabled dialogs | Telegram adapter and configured integrations |

## Scope limits

This is not a general agent framework, Kubernetes platform, or separate public HTTP RAG
service. The [RAG VPS v2 proposal](docs/architecture/RAG_VPS_V2_PROPOSED.md) remains a separate
design target. Do not import planned components into maintenance by assumption.

Reuse the existing owner before adding a configuration/dependency authority, ingestion
path, or orchestration layer.

## Terms

- **Knowledge collection:** configured Qdrant collection for document Q&A.
- **Apartment collection:** product catalog collection with a different schema/filter contract.
- **Readiness:** dependency/data checks needed for startup; distinct from a successful live journey.
- **Handoff:** transition between bot assistance and a human manager session.
- **Proposed:** a design under consideration, not current implementation authority.

Detailed invariants belong to their subsystem documents.

## Sources of truth

- [README](README.md): start and navigation.
- [Structure](docs/architecture/STRUCTURE.md): owners, flows, dependencies.
- [AGENTS](AGENTS.md): work routing and delivery rules.
- [GitHub Issues](https://github.com/yastman/rag/issues): work state and acceptance.
- [ADRs](docs/adr/): accepted architectural rationale.
- [Documentation hub](docs/README.md): procedures and subsystem references.

Update this file when accepted scope changes. Keep task progress with its issue/PR.
