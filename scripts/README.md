# scripts/

Automation, indexing, benchmarking, validation, and maintenance scripts.

## Categories

| Category | Scripts | Purpose |
|----------|---------|---------|
| **Indexing** | `index_*.py` | Chunk, embed, and load documents into Qdrant |
| **Setup** | `setup_*.py`, `qdrant_ensure_indexes.py` | Collection schema and score configs |
| **Validation** | `validate_*.py`, `check_image_drift.py`, `check_services.sh` | Query correctness and drift checks |
| **Benchmarks** | `benchmark_*.py`, `benchmark/*_ab.py` | A/B and throughput comparisons |
| **Experiment** | `eval/run_experiment.py`, `generate_test_properties.py` | Synthetic data and experiment runners |
| **Maintenance** | `qdrant_snapshot.py`, `reindex_to_binary.py` | Disaster recovery and migration |
| **Ops / health** | `probe/release_health_vps.sh`, `smoke-zoo.sh`, `check_services.sh` | Deployment and health checks |
| **Swarm / CI** | `launch_kiro_worker.sh`, `accept_worker_report.py`, `ci/*.py` | tmux worker orchestration and CI gates |
| **Hygiene** | Native `make git-hygiene`, `make repo-cleanup` targets | Repo hygiene |

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
