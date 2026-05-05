# data/demo/

Demo data files for local indexing pipeline tests.

## Contents

This directory holds sample documents used to verify the ingestion pipeline end-to-end.
Data files are excluded from Git (see `.gitignore`) to avoid committing large binaries.

Typical files placed here:
- `demo_BG.csv` — Sample property listings
- `info_bg_home.docx` — Sample company contact document

## Usage

Index demo files via the unified ingestion pipeline or helper scripts in [`scripts/`](../../scripts/):

```bash
uv run python scripts/index_test_data.py
```

## Related

- [`docs/INGESTION.md`](../../docs/INGESTION.md) — Ingestion runbook
- [`src/ingestion/`](../../src/ingestion/) — Ingestion modules
