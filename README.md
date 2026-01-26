# Contextual RAG Pipeline

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/linter-ruff-green.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Production RAG system with hybrid search (RRF + ColBERT), Voyage AI embeddings, and Telegram bot.

## Quick Start

```bash
make install-dev        # Install dependencies
make docker-up          # Start Qdrant, Redis, MLflow
make check              # Lint + type check
make test               # Run tests
```

## Documentation

| File | Purpose |
|------|---------|
| **[CLAUDE.md](CLAUDE.md)** | Full technical context (architecture, commands, patterns) |
| **[CHANGELOG.md](CHANGELOG.md)** | Version history (auto-generated) |
| **[TODO.md](TODO.md)** | Current tasks |

## Key Links

- [docs/PIPELINE_OVERVIEW.md](docs/PIPELINE_OVERVIEW.md) - Architecture deep dive
- [docs/QDRANT_STACK.md](docs/QDRANT_STACK.md) - Vector DB configuration
- [docs/LOCAL-DEVELOPMENT.md](docs/LOCAL-DEVELOPMENT.md) - Dev environment setup

---

**Version:** See [CHANGELOG.md](CHANGELOG.md) | **Details:** See [CLAUDE.md](CLAUDE.md)
