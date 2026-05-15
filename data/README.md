# data/

Project data files: demo fixtures, test datasets, and generated assets.

## Contents

| Path | Purpose |
|------|---------|
| `apartments.csv` | Sample apartment listings for local ingestion (public/synthetic data) |
| `demo/` | Demo data files for ingestion pipeline tests |
| `test/` | Test datasets and sample articles |
| `test_properties.json` | Generated property fixture data |

## Data Provenance and Privacy

- **`apartments.csv`** — contains **public/sample real-estate listing data** (complex names, cities, prices, areas). No personal emails, phone numbers, or private owner details are included.
- **`test_properties.json`** — contains **generated/synthetic fixture data** for tests. UUIDs and values are fabricated.
- **`data/demo/`** — intended for **local demo documents**; files are Git-ignored per `.gitignore`.
- **`data/test/`** — owned by test suites (`tests/`); fixtures must be deterministic and version-controlled.

## Safety Warnings

- Do **not** commit real CRM exports, client contact lists, phone numbers, email addresses, private property records, or personal recordings.
- Do **not** commit large binary files or production datasets.
- If you are unsure whether a dataset contains personal or proprietary information, treat it as sensitive and keep it out of the public repository.

## Related

- [Project overview](../README.md)
- [Scripts](../scripts/README.md)
- [Ingestion docs](../docs/INGESTION.md)
- [Tests](../tests/README.md)
- [Test data](test/README.md)
- [Demo data](demo/README.md)
