# No-patch dependency alerts — current closeout assessment

**Last reviewed:** 2026-06-15
**Tracking issue:** [#2043](https://github.com/yastman/rag/issues/2043)

This note records the current state of the former no-patch Dependabot alerts for
`diskcache` and `ragas`. Earlier audits tracked two alerts with no upstream
patched version. The current repository state no longer includes either package
in the root dependency or lockfile surfaces.

---

## Current state

| Package | Previous alert | Current repo state | Current exposure |
|---------|----------------|--------------------|------------------|
| `diskcache` | CVE-2025-69872, medium, vulnerable `<=5.6.3`, no patched version at original audit time | Not declared in `pyproject.toml`; no package record/string match in `uv.lock`; no first-party imports | No current dependency/lockfile exposure found |
| `ragas` | CVE-2026-6587, low, vulnerable `>=0.2.3, <=0.4.3`, no patched version at original audit time | Not declared in `pyproject.toml`; no package record/string match in `uv.lock`; the old evaluation module is now a disabled compatibility shim | No current dependency/lockfile exposure found |

`ragas` must not be restored to the `eval` optional extra, base dependencies, or
lockfile without a fresh #2043 risk review and maintainer acceptance. `diskcache`
must not be added directly or indirectly as part of this tracking issue without
the same review.

---

## Verification commands

Use these commands when rechecking the current state:

```bash
rg -n '^name = "(ragas|diskcache)"|ragas|diskcache' uv.lock
rg -n 'ragas|diskcache|\[project.optional-dependencies\]|eval\s*=|dependencies\s*=' pyproject.toml
rg -n --hidden --glob '!uv.lock' --glob '!*.pyc' --glob '!node_modules/**' --glob '!vendor/**' '\bragas\b|from ragas|import ragas' .
rg -n --hidden --glob '!uv.lock' --glob '!*.pyc' --glob '!node_modules/**' --glob '!vendor/**' '\bdiskcache\b|from diskcache|import diskcache' .
uv lock --locked
```

Expected current result:

- `uv.lock` has no `ragas` or `diskcache` package records.
- `pyproject.toml` has no `ragas` or `diskcache` dependency declarations.
- `diskcache` appears only in documentation/status references.
- `ragas` appears in documentation, dependency contracts, disabled compatibility
  tests, and `src/evaluation/ragas_evaluation.py`, which now raises an explicit
  unavailable-lane error instead of importing the undeclared package.

---

## Historical context

Earlier #2043 audits described this older state:

- `ragas` was a direct optional `eval` dependency.
- `diskcache` was present transitively through `ragas`.
- The active mitigation was isolation of the evaluation lane while waiting for
  upstream patched versions or explicit risk acceptance.

That older assessment is retained here only as history. It is not the current
repo state after the dependency surface was removed.

---

## Reassessment triggers

Reopen the full risk assessment before any of these changes:

| Change | Required action |
|--------|-----------------|
| `ragas` is added back to any dependency group or optional extra | Full #2043 risk review and maintainer acceptance |
| `diskcache` appears in `uv.lock` or any dependency file | Determine whether it is direct/transitive and reassess CVE-2025-69872 exposure |
| The disabled RAGAS shim is replaced with active evaluation code | Review dependency, network, input, and cache exposure before merge |
| Dependabot reports fresh root-lock alerts for either package | Re-run the verification commands and reconcile GitHub Security-tab state |

---

## Closeout recommendation

For #2043, the code/dependency closeout recommendation is: close after
maintainers confirm the GitHub Dependabot UI no longer reports active root
`uv.lock` alerts for `ragas` or `diskcache`. If the UI still shows historical
alerts while the packages are absent from `uv.lock`, handle that as an admin
Security-tab reconciliation item rather than a dependency-change PR.
