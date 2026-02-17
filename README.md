# Contextual RAG Pipeline

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/linter-ruff-green.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Production RAG system with hybrid search (RRF + ColBERT rerank), BGE-M3 embeddings (local CPU), multi-level caching, and Telegram bot.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## Quick Start

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Start services and run
make docker-up          # Start core (5 services, ~17s)
make docker-full-up     # Start all (20 services)
make check              # Lint + type check
make test               # Run tests
```

## Documentation

| File | Purpose |
|------|---------|
| **[AGENTS.md](AGENTS.md)** | Codex workflow and repository-wide agent rules |
| **[docs/agent-rules/workflow.md](docs/agent-rules/workflow.md)** | Development loop and command map |
| **[CHANGELOG.md](CHANGELOG.md)** | Version history (auto-generated) |
| **[TODO.md](TODO.md)** | Current tasks |

## Key Links

- [docs/PIPELINE_OVERVIEW.md](docs/PIPELINE_OVERVIEW.md) - Architecture deep dive
- [docs/QDRANT_STACK.md](docs/QDRANT_STACK.md) - Vector DB configuration
- [docs/LOCAL-DEVELOPMENT.md](docs/LOCAL-DEVELOPMENT.md) - Dev environment setup

---

**Version:** See [CHANGELOG.md](CHANGELOG.md) | **Details:** See [AGENTS.md](AGENTS.md)
