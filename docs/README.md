# Documentation hub

Choose the document for the task. Each durable fact has one owner.

| Need | Owner |
| --- | --- |
| Product goal, accepted baseline, terms | [PROJECT.md](../PROJECT.md) |
| Start the application | [README.md](../README.md) |
| Work and delivery rules | [AGENTS.md](../AGENTS.md) |
| Module ownership, flows, dependencies | [Structure](architecture/STRUCTURE.md) |
| Dependencies, Windows/WSL, local setup | [Local Development](LOCAL-DEVELOPMENT.md) |
| Test lanes and validation | [Tests](../tests/README.md) |
| Test-writing conventions | [Test-writing guide](engineering/test-writing-guide.md) |
| Compose services, profiles, ports, environment | [DOCKER.md](../DOCKER.md) |
| Recovery and demo procedures | [Runbooks](runbooks/README.md) |
| Contribution process | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Security policy | [SECURITY.md](../SECURITY.md) |
| Accepted architectural rationale | [ADRs](adr/) |

## Subsystem entry points

| Change | Read |
| --- | --- |
| Public API and dependency contracts | [Core](../src/core/README.md) |
| Retrieval, generation, routing, caches | [Runtime](../src/runtime/README.md) |
| Telegram handlers, lifecycle, product UI | [Telegram](../telegram_bot/README.md), [local rules](../telegram_bot/AGENTS.override.md) |
| Markdown ingestion and cleanup | [Ingestion authority](INGESTION.md), [local rules](../src/ingestion/unified/AGENTS.override.md) |
| Apartment corpus | [Apartment ingestion](../src/ingestion/apartments/README.md) |
| BGE artifact, API, image | [BGE-M3](../services/bge-m3-api/README.md), [local rules](../services/bge-m3-api/AGENTS.override.md) |
| Operator scripts | [Scripts](../scripts/README.md), [local rules](../scripts/AGENTS.override.md) |
| Real user-journey demonstration | [Five-minute demo](runbooks/FIVE-MINUTE-DEMO.md) |

## Decisions and work state

[GitHub Issues](https://github.com/yastman/rag/issues) own work, priorities, dependencies,
and acceptance. PRs own review and delivery evidence. CodeIndexer provides search and context;
there is no mandatory second phase/card lifecycle.

The [RAG VPS v2 proposal](architecture/RAG_VPS_V2_PROPOSED.md) is a design target.
Dated audits and execution reports are historical evidence, not current configuration.

Update the owning document when changing a fact. Link from other pages. Use Git for raw
history. Add a document only for durable knowledge or a repeatable procedure with no existing home.
