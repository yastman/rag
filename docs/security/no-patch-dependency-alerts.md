# No-patch dependency alerts — exposure assessment

**Last reviewed:** 2026-05-22
**Source artifacts:**
`logs/NO-PATCH-DEPENDENCY-MITIGATION.audit.md`,
`logs/SECURITY-ISSUE-POSTMERGE.audit.md`,
GitHub issue [#2043](https://github.com/yastman/rag/issues/2043)

Two open Dependabot alerts have no upstream patched version. This note records
the project's assessment and monitoring criteria so future maintainers can
understand why these alerts are open and what would change the verdict.

---

## Current alert matrix

| Alert # | Package | CVE | Severity | Current | Patched | Dep type |
|---------|---------|-----|----------|---------|---------|----------|
| 51 | diskcache | CVE-2025-69872 | medium | 5.6.3 | none | transitive (via ragas) |
| 65 | ragas | CVE-2026-6587 | low | 0.4.3 | none | direct, optional `eval` extra |

**All other Dependabot alerts resolved** as of 2026-05-22 (including Dependabot
PRs #2031, #2035, #2037).

---

## Why these are not production-exposed today

### ragas — eval-only optional dependency

- ragas is declared in the `[project.optional-dependencies]` → `eval` group in
  `pyproject.toml`. It is **not** in core `[project.dependencies]`.
- The `eval` extra is **not** installed by:
  - `make install` (production install, `uv sync --no-dev`)
  - `Dockerfile.ingestion`
  - Any published Docker image build workflow
- The `eval` extra **is** installed by:
  - `make sync` / `make install-all` (developer local convenience targets)
  - `.github/workflows/nightly-heavy.yml` (`uv sync --frozen --extra all`)
- The vulnerable code path — `multi_modal_faithfulness` in
  `ragas/metrics/collections/multi_modal_faithfulness/util.py` — is **never
  imported** in any project source file. The project uses only four ragas
  metrics (`Faithfulness`, `ContextPrecision`, `ContextRecall`, `AnswerRelevancy`),
  none of which touch multimodal paths.
- Evaluation input is local, version-controlled test data
  (`tests/eval/ground_truth.json`); no untrusted URLs or user-supplied content
  flow into any ragas call path.

### diskcache — transitive-only

- diskcache is **not** a direct dependency; it appears in `uv.lock` only as a
  transitive dependency of ragas.
- **Zero direct imports** of diskcache in any project source file under `src/`,
  `tests/`, `telegram_bot/`, `scripts/`, or `services/`.
- The CVE (unsafe pickle deserialization) requires an attacker with write access
  to the cache directory. In this project:
  - The ragas cache directory exists only inside the evaluation execution
    environment (CI container / developer machine).
  - No external, network-accessible service writes to or reads from this
    directory.
  - A filesystem compromise would be a higher-severity incident regardless of
    this CVE.

---

## What would invalidate this assessment

The following changes would require reassessment:

| Change | Affected CVE | Action |
|--------|-------------|--------|
| Project adds multimodal RAG evaluation (image/video) | CVE-2026-6587 | Reassess SSRF reachability |
| ragas is promoted from `eval` extra to core dependencies | Both | Full risk review |
| Evaluation pipeline accepts untrusted external input | CVE-2026-6587 | Reassess SSRF reachability |
| ragas cache directory is exposed as a network-writable service | CVE-2025-69872 | Reassess pickle deserialization |
| Production Docker images include the `eval` extra | Both | Full risk review |

---

## Monitoring and upgrade criteria

**Monitoring:**
- Watch [ragas releases](https://github.com/explodinggradients/ragas/releases)
  for a version that patches CVE-2026-6587 and/or removes the diskcache
  dependency.
- Watch [diskcache releases](https://github.com/grantjenks/python-diskcache/releases)
  for a version that addresses CVE-2025-69872 (e.g., non-pickle serialization
  option).
- The open `ragas>=0.4.3` constraint in `pyproject.toml` means that when
  upstream ships a fix, adopting it requires only a standard dependency upgrade
  workflow — no changes to `pyproject.toml` constraints.

**Upgrade criteria:**
- When a patched ragas version is released, follow the standard dependency
  upgrade workflow (see `dependency-upgrade` skill / dep-upgrade workflow).
- When a patched diskcache version is released, bump it through ragas or
  constrain it directly in `pyproject.toml` if ragas has not yet adopted it.

---

## Dependabot dismissal note

Dismissing these alerts manually through the GitHub Security tab requires
explicit risk acceptance. Dismissal options:

- **Risk accepted** — documented in this file; two reviewers have reviewed the
  assessment.
- **Not exploitable** — the vulnerable code paths are unreachable in the
  current project configuration.

Dismissal does **not** mean the vulnerability is harmless in all contexts. It
means the project's current configuration renders it not practically
exploitable.

**Do not add Dependabot ignore rules** to `.github/dependabot.yml` for these
alerts. The intent is to keep them visible as a monitoring signal — when a
patched version ships, Dependabot will clear the alert automatically, serving
as a prompt to upgrade.

---

## Related issues

- [#2043](https://github.com/yastman/rag/issues/2043) — Tracking issue for
  no-patch Dependabot alerts.
