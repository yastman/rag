# Bug-Class Registry

> Machine-readable source of truth: [`.github/bug-classes.yml`](../../.github/bug-classes.yml).
> This Markdown file is the human-readable mirror.

## Purpose

This is the human-readable mirror of the recurring bug classes discovered
through issue triage, regression analysis, and operational incidents. The
machine-readable source of truth is `.github/bug-classes.yml`. When a bug
pattern repeats, it is promoted from a one-off fix to a named class with a
permanent guardrail. Every new PR that touches an area listed here must either
reference the relevant class or explain why the class does not apply.

## Registry

| Bug Class | Guardrail | Canonical Issue | Related Issues | First Seen | Last Confirmed |
|---|---|---|---|---|---|
| Langfuse/OTEL/contextvars loss | Context propagation contract in `tests/contract/test_observability_contextvars_contract.py`; span metadata coverage in `tests/unit/test_observability_span_metadata.py`; CI gate via `make test-contract` | [#2301](https://github.com/yastman/rag/issues/2301) | [#2302](https://github.com/yastman/rag/issues/2302), [#2246](https://github.com/yastman/rag/issues/2246), [#2272](https://github.com/yastman/rag/issues/2272), [#2266](https://github.com/yastman/rag/issues/2266), [#2256](https://github.com/yastman/rag/issues/2256), [#2253](https://github.com/yastman/rag/issues/2253), [#2223](https://github.com/yastman/rag/issues/2223), [#2222](https://github.com/yastman/rag/issues/2222), [#2221](https://github.com/yastman/rag/issues/2221), [#2216](https://github.com/yastman/rag/issues/2216), [#2215](https://github.com/yastman/rag/issues/2215), [#2214](https://github.com/yastman/rag/issues/2214), [#2166](https://github.com/yastman/rag/issues/2166), [#2064](https://github.com/yastman/rag/issues/2064) | 2025 | 2026 |
| uv .venv mutation | Review-safe gates use `check-frozen` / `candidate-check`: `uv sync --frozen --check` first, then `$(UV_RUN_NO_SYNC)` (`uv run --no-sync`) for Ruff/MyPy; bot startup preflight also uses `$(UV_RUN_NO_SYNC)`; contract coverage in `tests/contract/test_makefile_review_gate_no_autosync_contract.py` and `tests/unit/test_makefile_contract.py`; CI gate via `make test-contract` | [#2296](https://github.com/yastman/rag/issues/2296) | [#2285](https://github.com/yastman/rag/issues/2285) duplicates [#2289](https://github.com/yastman/rag/issues/2289) (same root cause, uv autosync corrupted shared env) | 2025 | 2026 |
| Docker/compose drift | `tests/unit/test_compose_runtime_contract.py` pins service profile expectations; `tests/unit/test_check_image_drift.py` locks the read-only runtime drift checker; `make verify-compose-runtime` compares running image digests and published host ports against Compose source | [#2185](https://github.com/yastman/rag/issues/2185) | [#2123](https://github.com/yastman/rag/issues/2123), [#2182](https://github.com/yastman/rag/issues/2182), [#2188](https://github.com/yastman/rag/issues/2188), [#2103](https://github.com/yastman/rag/issues/2103) duplicates [#2124](https://github.com/yastman/rag/issues/2124) (postgres `cap_drop` duplicate fix) | 2025 | 2026 |
| RAG quality regression | Evaluation pipeline (`make eval-rag`, `make eval-rag-quick`, `make eval-rag-full`) gates quality score thresholds; regression detected if score drops below baseline | preventive/backlog | No concrete duplicate cluster in current issue corpus; this class is **preventive/backlog** pending first recurrence | 2025 | 2026 |
| Testing hygiene/tautological assertions | `tests/contract/test_ingestion_e2e_assertions_contract.py` enforces assertion quality for ingestion flows; `docs/engineering/test-writing-guide.md` defines review traps and anti-duplication rules; `make test` gates these checks on every push | [#1515](https://github.com/yastman/rag/issues/1515) | [#1539](https://github.com/yastman/rag/issues/1539), [#1944](https://github.com/yastman/rag/issues/1944), [#1978](https://github.com/yastman/rag/issues/1978), [#1508](https://github.com/yastman/rag/issues/1508), [#1617](https://github.com/yastman/rag/issues/1617) duplicates [#1626](https://github.com/yastman/rag/issues/1626) (tautological assertions on empty output) | 2025 | 2026 |

## Guardrail Standards

This section defines the vocabulary and process for the anti-regression guardrail
system. These definitions are the first-wave standard; broader practices from the
2026 roadmap (feature flags, progressive delivery, DORA metrics, SAST/SBOM/DAST,
golden paths) are tracked as follow-up backlog and will be integrated as subsequent
slices.

### Regression-driven TDD

Every bug fix follows the same cycle: discover the bug, write a failing regression
test that reproduces it, implement the minimal fix, and ensure the test passes.
The regression test becomes the gate that prevents the bug from recurring.

### Guardrail

A guardrail is a permanent executable rule that prevents a recurring bug class.
Guardrails take the form of contract tests, CI gates, or automated checks that
run on every push and PR. A guardrail is not a comment, not a code-review
convention, and not a manual checklist -- it is automated and enforced.
Semgrep is the generic code-pattern guardrail engine for repeated forbidden
patterns; project-specific root-cause, bug-class, and cross-file contracts stay
in Python/pytest checks.

### Quality Gate

A quality gate is a CI or branch-protection enforcement point that blocks
merging when a guardrail fails. Quality gates run during `make check`, `make test`,
`make test-contract`, and the CI pipeline; they are non-bypassable without
documented override.

### Principle

**Every recurring bug must become a permanent guardrail.**

No bug class may be registered without at least one automated guardrail. When a
new recurrence of a registered class is discovered, the existing guardrail must
be reviewed and strengthened. All guardrails are cumulative -- each new guardrail
makes it harder for the same class of defect to slip through.

## Follow-up Backlog (2026 Map)

The following broader practices are tracked for future slices and are **not**
implemented in the first wave:

- **Feature flags**: decouple deploy from release for safer rollbacks.
- **Progressive delivery**: canary deployments and staged rollouts.
- **DORA metrics**: deployment frequency, lead time, change failure rate, mean time to restore.
- **SAST/SBOM/DAST**: static analysis, software bill of materials, dynamic analysis in CI.
- **Golden paths**: opinionated templates and workflows for common change types.

## Ownership

- **Maintainer**: engineering process owner (see [`docs/engineering/README.md`](README.md)).
- **Update rule**: add new bug classes after confirmed recurrence (>=2 occurrences).
- **Review trigger**: every PR that touches a registered area must reference this registry.
- **Recurrence rule**: a repeated class must include a canonical issue, related
  issues, a guardrail path, and the required CI/check that executes the guardrail.
- **Disposition rule**: duplicate issues close against the canonical issue;
  recurrences stay open until the guardrail is added or strengthened.
