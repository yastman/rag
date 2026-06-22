# data/demo/

Demo data files for local indexing pipeline tests.

## Contents

This directory holds sample documents used to verify the ingestion pipeline end-to-end.
Data files are excluded from Git (see `.gitignore`) to avoid committing large binaries.

Typical local filenames you can place here (these are not committed):
- `demo_BG.csv` — Sample property listings
- `info_bg_home.docx` — Sample company contact document

## Data Status

Files placed here should be **synthetic, public, or fully anonymized**.
They are meant for local pipeline verification only and are not part of the public repository.

## Safety Warnings

- Do **not** commit real CRM exports, client contact lists, phone numbers, email addresses, private property records, or personal recordings.
- Do **not** place proprietary or licensed documents here unless you have explicit redistribution rights.
- When in doubt, generate synthetic data or use clearly public-domain sources.

## Usage

Index demo files via the unified ingestion pipeline or helper scripts in [`scripts/`](../../scripts/):

```bash
uv run python scripts/index_test_data.py
```

## Related

- [`docs/INGESTION.md`](../../docs/INGESTION.md) — Ingestion runbook
- [`src/ingestion/`](../../src/ingestion/) — Ingestion modules
