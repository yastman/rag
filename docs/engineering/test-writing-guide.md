# Test-Writing Guide

Conventions for adding tests to the RAG Q&A chatbot. For the directory layout, tier model,
and the full command map see [`../../tests/README.md`](../../tests/README.md); for running
them locally see [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Pick the right tier

Tests are tiered by what they prove and what they cost (markers defined in
[`../../pyproject.toml`](../../pyproject.toml) `[tool.pytest.ini_options]`):

| Tier | Location | Needs services? | When |
|---|---|---|---|
| `unit` | `tests/unit/` | No (mocks/fakes) | Default — isolated logic |
| `contract` | `tests/contract/` | No (static analysis) | Lock an invariant: trace/schema/architecture, "no monolith X" guards, migration ratchets |
| `integration` | `tests/integration/` | Yes (Qdrant/Redis/APIs) | Real component interaction |
| `smoke` | `tests/smoke/` | Yes (live) | Health/routing sanity |
| `eval` | `tests/eval/` | Yes | RAG quality (faithfulness/relevance) |
| `chaos` / `load` | `tests/chaos/`, `tests/load/` | Yes | Degraded-service behavior, throughput |
| `e2e` | `tests/e2e/` | Yes | Full-stack / Telegram flows |

Keep the local fast lane (`unit` + `contract`) fast and Docker-free. **Do not** move
live-service scenarios into it.

## Rules of thumb

- **Search before adding.** Reuse existing coverage — `search_code(query, project="rag-fresh")`
  or `rg -n "<behavior>" tests/` — before creating a new file.
- **Unit tests mock external services** (Qdrant, Redis, LLM providers); keep them
  deterministic. Shared ML-lib mocks live in `tests/unit/conftest.py`.
- **Mark heavy tests** with the right marker (`@pytest.mark.integration`, `smoke`, `e2e`,
  `requires_extras`, …) so the fast gate can exclude them.
- **Keep fixture scopes narrow**; put shared setup in the nearest `conftest.py`, not the root.
- **Add a test with every bug fix and feature** (TDD when touching hotspots like
  `telegram_bot/agents/rag_pipeline.py` or `src/runtime/generation/service.py`).

## Naming

```
test_<feature>.py                  # file
test_<behavior>_<expected>()       # function
```

```python
def test_store_embedding_creates_hash():
    """Embedding storage creates a unique hash key."""
    ...
```

## Running

```bash
make test-core                                   # core gate, run first
uv run pytest tests/unit/test_<module>.py -q     # focused while developing
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
make test-cov                                    # coverage (fail_under=80)
```
