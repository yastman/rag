# data/

Project data files: demo fixtures, test datasets, and generated assets.

## Contents

| Path | Purpose |
|------|---------|
| `apartments.csv` | Sample apartment listings for local ingestion |
| `demo/` | Demo data files for ingestion pipeline tests |
| `test/` | Test datasets and sample articles |
| `test_properties.json` | Generated property fixture data |

## Owner Boundaries

- **`data/demo/`** — owned by ingestion testing; keep files Git-ignored per `.gitignore`.
- **`data/test/`** — owned by test suites (`tests/`); fixtures must be deterministic and version-controlled.
- **`data/apartments.csv`, `data/test_properties.json`** — owned by scripts under `scripts/`; regenerated as needed.
- Do not commit large binary files, real user data, or production datasets to this directory.

## Related

- [Project overview](../README.md)
- [Scripts](../scripts/README.md)
- [Ingestion docs](../docs/INGESTION.md)
- [Tests](../tests/README.md)
- [Test data](test/README.md)
- [Demo data](demo/README.md)
