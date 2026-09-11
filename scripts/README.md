# scripts/

Automation, indexing, validation, and maintenance scripts. Markdown is the only
RAG ingestion format (#3235); the unified ingestion pipeline owns indexing.

## Categories

| Category | Scripts | Purpose |
|----------|---------|---------|
| **Setup** | `setup_*.py`, `qdrant_ensure_indexes.py` | Collection schema and score configs |
| **Validation** | `validate_*.py`, `check_image_drift.py`, `check_services.sh` | Query correctness and drift checks |
| **Maintenance** | `qdrant_snapshot.py`, `reindex_to_binary.py` | Disaster recovery and migration |
| **Ops / health** | `probe/release_health_vps.sh`, `check_services.sh` | Deployment and health checks |
| **CI** | `ci/*.py` | CI gates (CVE gate, PR guardrails) |
| **E2E** | `e2e/runner.py`, `e2e/demo_gate.py` | Capability E2E runner and demo gate |

Operators run these scripts directly with `uv run` (see `make help` for the
retained Make entrypoints). Retired evaluation/benchmark and Kiro/tmux swarm
surfaces were removed; native task agents are the sole supported agent runtime.

## Usage

Most scripts are self-contained and run with `uv run` or directly:

```bash
uv run python scripts/setup_qdrant_collection.py
```

## Related

- [`docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local commands and validation ladder
- [`docs/INGESTION.md`](../docs/INGESTION.md) — Unified ingestion runbook
- [`docs/runbooks/README.md`](../docs/runbooks/README.md) — Operational runbooks
- [`tests/README.md`](../tests/README.md) — Test pyramid and markers
