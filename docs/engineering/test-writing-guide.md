# Test Writing Guide

## Goal
- Keep tests fast, deterministic, and aligned with repository lane contracts.
- Prefer minimal, behavior-focused checks over broad snapshot-like assertions.
- Avoid duplicate ownership: one behavior should have one canonical test owner.

## Test Placement
- `tests/unit/` for isolated logic with mocks/fakes, no live service dependency.
- `tests/unit/e2e_adapters/` for unit checks around E2E helper code (config/adapters/validators), still unit lane.
- `tests/integration/` for service-aware paths and real component interaction.
- `tests/smoke/`, `tests/load/`, `tests/chaos/`, `tests/e2e/`, `tests/benchmark/` for heavy-tier and runtime-sensitive coverage.
- Keep tests close to owning surface (`services`, `graph`, `mini_app`, `ingestion`, etc.).

E2E naming contract:
- Real end-to-end tests belong to `tests/e2e/` only.
- Do not add live/runtime E2E flows under `tests/unit/**`.

## Naming And Structure
- File: `test_<feature>.py`
- Test: `test_<behavior>_<expected_outcome>()`
- Use Arrange/Act/Assert structure inside each test.
- Use descriptive fixture names and keep fixture scope as narrow as possible.

## Markers And Lane Contract
- Valid markers are defined in `pyproject.toml` (`unit`, `integration`, `slow`, `chaos`, `load`, `e2e`, `smoke`, `benchmark`, `requires_extras`, etc.).
- Mark tests with the smallest correct marker set.
- Do not move heavy/live scenarios into the local fast lane.
- Local fast loop should remain compatible with:
  - `make test-unit`
  - `make test`

## GitHub CI And Local Gate Contracts

### Fast Tests lane (`.github/workflows/ci.yml`)
- GitHub `fast-tests` runs `tests/unit/` + `tests/contract/` + critical graph-path
  integration with `-m "not legacy_api and not requires_extras and not slow"`.
- Keep new fast-lane tests free of `pytest.mark.slow`, `pytest.mark.requires_extras`,
  and any marker that would exclude them from that expression.
- Fast tests must not require Docker or live services.

### Contract tests
- Contract tests live in `tests/contract/`.
- They are static analysis (no Docker) and run in the fast-lane gate.
- Run them locally with `make test-contract`.

### Runtime and heavy tests
- Tests that need live services, Docker, credentials, or long durations belong in
  `tests/integration/`, `tests/smoke/`, `tests/e2e/`, `tests/load/`, or
  `tests/benchmark/`.
- These are for local powerful-machine validation (`make test-full`) or nightly
  gates (`.github/workflows/nightly-heavy.yml`), not the CI fast lane.
- For the complete local validation ladder (including `make test-full`,
  parallelism tuning, and WSL memory considerations), see
  [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Reliability Rules
- Mock external APIs and non-deterministic boundaries in unit tests.
- Freeze or control time/random inputs when behavior depends on them.
- Avoid sleep-based timing assertions; assert explicit state transitions instead.
- For credential-dependent live paths, prefer explicit skip gates over flaky failures.

## Anti-Duplication Rules
- Before adding a test, search for existing coverage:
  - `rg -n "<function_or_behavior>" tests/`
- If coverage exists, extend the canonical file instead of creating a second owner.
- Remove low-signal duplicates that repeat identical behavior checks without adding new risk coverage.

## Minimal Verification For Test Changes
- Focused run for touched files first:
  - `uv run pytest <path/to/test_file.py> -q`
- Then run repository baseline:
  - `make check`
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- If skipping a relevant check, document it explicitly in the report.

## References
- `AGENTS.md`
- `tests/README.md`
- `Makefile`
- `pyproject.toml`
- `.github/workflows/ci.yml`
- `.github/workflows/nightly-heavy.yml`
