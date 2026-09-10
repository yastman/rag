# RAG Q&A Chatbot

A self-hosted Telegram assistant for grounded answers over private documents, with a
real-estate layer for apartment search, service cards, viewing requests, and manager handoff.
Python 3.12+, an in-process core/runtime, and Docker Compose sidecars.

[PROJECT.md](PROJECT.md) defines accepted scope; [AGENTS.md](AGENTS.md) defines work rules.

## Quick start

Linux/POSIX commands; see [Local Development](docs/LOCAL-DEVELOPMENT.md) for PowerShell/WSL.

```bash
uv sync --frozen --extra telegram
cp .env.example .env
# Fill in credentials and configure the verified BGE model artifact.
make core-up
make run-bot
```

The default sidecar stack needs a verified BGE-M3 artifact before its image can be built.
Follow the [BGE artifact instructions](services/bge-m3-api/README.md) and
[Compose guide](DOCKER.md). `compose.core.yml` backs `make core-min-up`, which starts
Qdrant + Redis only; embeddings and
data readiness still need to be supplied for the full bot. `make docker-bot-up` runs the bot
in Compose. PostgreSQL is an opt-in product capability.

Local configuration is the root .env, based on [.env.example](.env.example).
[pyproject.toml](pyproject.toml) and [uv.lock](uv.lock) own application/Telegram dependencies.

## Runtime

Telegram messages reach [run_assistant_request](src/core/assistant.py), which delegates to
the procedural [assistant pipeline](src/runtime/pipeline/assistant_pipeline.py).
Retrieval/generation or a deterministic product action returns an AssistantResult.
See [Structure](docs/architecture/STRUCTURE.md) for owners and dependency boundaries.

Qdrant stores search data; BGE-M3 supplies embeddings/reranking; Redis supplies caches and
coordination. PostgreSQL-backed features and manager/CRM integrations depend on their
configuration and capability checks. A module's presence does not prove it is enabled.

[Unified ingestion](docs/INGESTION.md) is Markdown-only, with stable file identity and
idempotent writes. Removing a source file does not automatically delete its Qdrant chunks;
follow the ingestion cleanup procedure.

## Validation

Start with focused tests. `make dev-setup` installs commit and push hooks.

```bash
make test-core        # Core/runtime behavior and import boundaries
make test             # Core + no-service integration/smoke lane
make test-contract    # Repository contracts
make candidate-check  # Authoritative local delivery gate
```

The delivery gate includes frozen-environment checks, lint/types, formatting, deterministic
tests, and contracts. [Tests](tests/README.md) explains setup and lane coverage.
`make test-full` is the manual full-suite gate. Live scenarios require their services and
credentials; static/unit checks do not establish live readiness.

GitHub runs the approved Candidate Gate and static/security checks. Hosted coverage is
narrower than the full local delivery gate. See [branch protection](docs/runbooks/BRANCH-PROTECTION.md)
and the actual [CI workflow](.github/workflows/ci.yml).

## Navigation

| Task | Read |
| --- | --- |
| Understand product scope | [PROJECT.md](PROJECT.md) |
| Work on the repository | [AGENTS.md](AGENTS.md) |
| Find code owners and flows | [Structure](docs/architecture/STRUCTURE.md) |
| Install, run, diagnose the environment | [Local Development](docs/LOCAL-DEVELOPMENT.md) |
| Change deployment/profiles/ports | [DOCKER.md](DOCKER.md) |
| Change document ingestion | [INGESTION.md](docs/INGESTION.md) |
| Choose checks | [Tests](tests/README.md) |
| Perform an operational procedure | [Runbooks](docs/runbooks/README.md) |
| Find other maintained documents | [Documentation hub](docs/README.md) |

The [RAG VPS v2 proposal](docs/architecture/RAG_VPS_V2_PROPOSED.md) describes a future design.
[GitHub Issues](https://github.com/yastman/rag/issues) own work state;
[ADRs](docs/adr/) own accepted rationale.

## License

This project is licensed under the [MIT License](LICENSE).
