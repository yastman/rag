# Issue #3247 Deterministic Windows UTF-8 Test Reads Specification

## Outcome

Repository-source tests decode tracked UTF-8 files explicitly on native Windows, independent of the host's legacy code page.

## Evidence

The official Windows Full gate failed eight node IDs with `UnicodeDecodeError` under `locale.getencoding() == "cp1251"`. The same nodes passed under `python -X utf8`, proving that omitted `Path.read_text()` encodings—not file corruption or product behavior—caused the failures.

## Contract

Add `encoding="utf-8"` only to the implicated repository-source reads in these seven test files:

- `tests/unit/security/test_secret_hygiene.py`
- `tests/unit/test_catalog_handler.py`
- `tests/unit/test_check_image_drift.py`
- `tests/unit/test_cloud_dependency_contract.py`
- `tests/unit/test_docker_static_validation.py`
- `tests/unit/test_env_example.py`
- `tests/unit/test_kfp_kubernetes_dependency_contract.py`

The catalog aggregation must update each `read_text()` in the same expression so the failure cannot move to the next source file.

## Non-Goals

- Product/runtime changes.
- Global source sweep or file recoding.
- `PYTHONUTF8`, `PYTHONIOENCODING`, locale, or preflight workarounds.

## Acceptance

The eight former failures pass with the native process encoding still cp1251; Linux behavior remains unchanged; only the seven test files plus this issue's spec/plan change.

## Rollback

Revert the mechanical test-read commit.
