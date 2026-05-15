# scripts/

Automation, indexing, benchmarking, validation, and maintenance scripts.

## Categories

| Category | Scripts | Purpose |
|----------|---------|---------|
| **Indexing** | `index_*.py` | Chunk, embed, and load documents into Qdrant |
| **Setup** | `setup_*.py`, `qdrant_ensure_indexes.py` | Collection schema, score configs, and Langfuse dashboards |
| **Validation** | `validate_*.py`, `check_image_drift.py`, `run_legal_grounding_audit.py` | Query correctness, trace validation, and drift checks |
| **Benchmarks** | `benchmark_*.py`, `test_*_ab.py`, `test_quantization_ab.py` | A/B and throughput comparisons |
| **Experiment** | `run_experiment.py`, `generate_test_properties.py` | Synthetic data and experiment runners |
| **Maintenance** | `qdrant_snapshot.py`, `reindex_to_binary.py` | Disaster recovery and migration |
| **Ops** | `test_release_health_vps.sh`, `test_bot_health.sh`, `smoke-zoo.sh` | Deployment and health checks |
| **Hygiene** | `git_hygiene.py`, `repo_cleanup.sh` | Repo hygiene |
| **Alerting** | `langfuse_alert.py`, `langfuse_triage.py` | Langfuse monitoring and triage |
| **CRM / Seeding** | `kommo_seed.py`, `update_advisor_prompts.py` | CRM seeding and prompt updates |

## Usage

Most scripts are self-contained and run with `uv run` or directly:

```bash
uv run python scripts/setup_qdrant_collection.py
```

## Related

- [`docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local commands and validation ladder
- [`docs/INGESTION.md`](../docs/INGESTION.md) — Unified ingestion runbook
- [`tests/README.md`](../tests/README.md) — Test pyramid and markers
