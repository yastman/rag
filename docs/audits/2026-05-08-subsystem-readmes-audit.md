# Subsystem READMEs Audit — 2026-05-08

**Worker**: `W-docs-subsystem-readmes-audit-20260508`
**Branch**: `docs/docs-subsystem-readmes-audit-20260508`
**Base**: `origin/dev` (`ec061b9c`)
**Scope**: Folder `README.md` and `AGENTS.override.md` files under `telegram_bot/`, `src/`, `mini_app/`, `services/`, `k8s/`
**Reserved file**: `docs/audits/2026-05-08-subsystem-readmes-audit.md`

---

## Method

1. Enumerate all scoped `README.md` and `AGENTS.override.md` files.
2. Read each README against the README Index Contract (purpose, entrypoints, boundaries, focused checks, See Also links, no duplicated Compose/env matrices).
3. Run `make docs-check` and `git diff --check`.
4. Record findings with evidence, proposed fix, and priority.

### Commands run

```bash
rg --files telegram_bot src mini_app services k8s | rg 'README.md$|AGENTS.override.md$'
rg -n "make |pytest|docker compose|COMPOSE|LANGFUSE|QDRANT|Redis|owner|boundary|entrypoint|runbook|DOCKER.md|docs/" \
  telegram_bot src mini_app services k8s --glob 'README.md' --glob 'AGENTS.override.md'
make docs-check
git diff --check
```

### Baseline results

- `make docs-check`: **passed** — all relative Markdown links valid.
- `git diff --check`: **passed** — no whitespace issues.
- No absolute local paths (e.g. `/home/user/...`) found in any scoped README.
- No README duplicates a full Compose profile/env matrix (all link to `DOCKER.md` for contract details).

---

## Files Inspected

### READMEs (24)

| Path | AGENTS.override linked? | DOCKER.md linked? | LOCAL-DEVELOPMENT.md linked? | runbooks/README.md linked? | Focused checks present? |
|---|---|---|---|---|---|
| `telegram_bot/README.md` | Yes | Yes | Yes | Yes | Yes |
| `telegram_bot/services/README.md` | Yes | Yes | Yes | Yes | Yes |
| `telegram_bot/middlewares/README.md` | **No** | **No** | **No** | **No** | Yes |
| `src/README.md` | N/A | Yes | Yes | Yes | Yes |
| `src/core/README.md` | N/A | **No** | **No** | **No** | Yes |
| `src/retrieval/README.md` | N/A | Yes | Yes | Yes | Yes |
| `src/ingestion/README.md` | Yes (unified) | Yes | Yes | Yes | Yes |
| `src/ingestion/unified/README.md` | **No** | **No** | **No** | **No** | Yes |
| `src/api/README.md` | N/A | **No** | **No** | **No** | Yes |
| `src/voice/README.md` | N/A | Yes | Yes | Yes | Yes |
| `src/contextualization/README.md` | N/A | **No** | **No** | **No** | No |
| `src/models/README.md` | N/A | **No** | **No** | **No** | Yes |
| `src/config/README.md` | N/A | **No** | **No** | **No** | Yes |
| `src/evaluation/README.md` | N/A | **No** | **No** | **No** | Yes |
| `src/utils/README.md` | N/A | **No** | **No** | **No** | Yes |
| `src/governance/README.md` | N/A | **No** | **No** | **No** | No |
| `src/security/README.md` | N/A | **No** | **No** | **No** | Yes |
| `mini_app/README.md` | N/A | Yes | Yes | Yes | Yes |
| `mini_app/frontend/README.md` | N/A | **No** | **No** | **No** | Yes |
| `services/README.md` | N/A | Yes | Yes | Yes | Yes |
| `services/bge-m3-api/README.md` | N/A | **No** | **No** | **No** | Yes |
| `services/docling/README.md` | N/A | **No** | **No** | **No** | Yes |
| `services/user-base/README.md` | N/A | **No** | **No** | **No** | Yes |
| `k8s/README.md` | N/A | Yes | Yes | **No** | Yes |

### AGENTS.override.md (2)

| Path | Referenced by nearest README? |
|---|---|
| `telegram_bot/AGENTS.override.md` | Yes (`telegram_bot/README.md`, `telegram_bot/services/README.md`). **No** (`telegram_bot/middlewares/README.md`). |
| `src/ingestion/unified/AGENTS.override.md` | Yes (`src/ingestion/README.md`). **No** (`src/ingestion/unified/README.md`). |

---

## Findings

`telegram_bot/middlewares/README.md` and `src/ingestion/unified/README.md` were rechecked against current `origin/dev` and already include "See Also" sections, so the previously reported F1/F2 are removed as stale.

### F1: `src/evaluation/README.md` file list uses plain text instead of Markdown links

- **Evidence**: The file list uses bare backtick names (`evaluator.py`, `ragas_evaluation.py`, etc.) instead of linked references like `[`evaluator.py`](./evaluator.py)`. This is inconsistent with the README Index Contract used by every other scoped README (e.g. `src/retrieval/README.md`, `src/core/README.md`).
- **Proposed fix**: Convert each bare filename to a relative Markdown link.
- **Files to reserve**: `src/evaluation/README.md`
- **Priority**: low

### F2: `src/security/README.md` file reference is unlinked

- **Evidence**: `pii_redaction.py` is listed as a bare backtick name without a relative link (`[`pii_redaction.py`](./pii_redaction.py)`), inconsistent with the index contract.
- **Proposed fix**: Link the filename.
- **Files to reserve**: `src/security/README.md`
- **Priority**: low

### F3: `src/contextualization/README.md` has escaped underscores in `__init__.py` link

- **Evidence**: Line 9 shows `[\\_\\_init\\_\\_.py](./__init__.py)`. In standard Markdown renderers this displays literal backslashes and underscores instead of a clean link label.
- **Proposed fix**: Use backtick code spans inside the link label: ``[`__init__.py`](./__init__.py)``.
- **Files to reserve**: `src/contextualization/README.md`
- **Priority**: low

### F4: `src/api/README.md` missing canonical doc links

- **Evidence**: No "See Also" section. Missing links to `../../DOCKER.md`, `../../docs/LOCAL-DEVELOPMENT.md`, and `../../docs/runbooks/README.md`. This is a transport/runtime-impacting surface (FastAPI app with health endpoint).
- **Proposed fix**: Add a "See Also" section with the three canonical doc links.
- **Files to reserve**: `src/api/README.md`
- **Priority**: medium

### F5: `mini_app/frontend/README.md` missing canonical doc links

- **Evidence**: No "See Also" section. Missing links to `../../DOCKER.md`, `../../docs/LOCAL-DEVELOPMENT.md`, and `../../docs/runbooks/README.md`.
- **Proposed fix**: Add a "See Also" section with the three canonical doc links.
- **Files to reserve**: `mini_app/frontend/README.md`
- **Priority**: low

### F6: `k8s/README.md` missing `docs/runbooks/README.md` link

- **Evidence**: The README links to `DOCKER.md` and `LOCAL-DEVELOPMENT.md` but does not link to `docs/runbooks/README.md`, which is the canonical entry point for operational investigations.
- **Proposed fix**: Add `- [../docs/runbooks/README.md](../docs/runbooks/README.md) — Operational troubleshooting` to the See Also section.
- **Files to reserve**: `k8s/README.md`
- **Priority**: low

---

## Summary

- **Total READMEs inspected**: 24
- **Total AGENTS.override.md inspected**: 2
- **No broken relative Markdown links** (confirmed by `make docs-check`).
- **No absolute local paths** found.
- **No duplicated Compose/env matrices** found.
- **Findings**: 6 (1 medium, 5 low). None are blockers for runtime or deployment.
- **No new bugs** requiring code/config changes.

---

## Next Action

Apply the 6 proposed fixes in a follow-up PR. The medium-priority item (F4) should be fixed first because it affects a runtime-impacting API surface.
