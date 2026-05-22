# Dependabot no-patch alerts — exposure audit

> Tracks issue [#2043](https://github.com/yastman/rag/issues/2043).
> Audit date: 2026-05-22. Audit scope: post-merge security audit on `dev`
> after PRs #2028, #2031, #2035, #2037 closed all fixable Dependabot
> alerts.

## Alerts in scope

After the patched fixes landed, two open Dependabot alerts remain with
**no upstream patched version**:

| Package | CVE | Severity | Current | Vulnerable range | Patched version |
|---|---|---|---|---|---|
| `diskcache` | CVE-2025-69872 | medium | `5.6.3` | `<=5.6.3` | none |
| `ragas` | CVE-2026-6587 | low | `0.4.3` | `>=0.2.3, <=0.4.3` | none |

## Repository exposure

### `ragas` — confined to evaluation pipeline

`ragas` appears as a **direct dependency in exactly one place**:

```toml
# pyproject.toml
[project.optional-dependencies]
eval = [
    "ragas>=0.4.3",
    "datasets>=3.0.0",
    "pandas>=2.0.0",
]
```

It is **not** in `[project].dependencies` (the production install set).
Subpackage `pyproject.toml` files (`telegram_bot/`, `mini_app/`,
`services/bge-m3-api/`, `services/user-base/`, `services/docling/`) do
not depend on `ragas`.

First-party imports — verified by `grep -rn -E "(import ragas|from ragas)"`:

| File | Purpose |
|---|---|
| `src/evaluation/ragas_evaluation.py` | The only production-style import. Builds a `Dataset` locally from `tests/eval/ground_truth.json` and calls `evaluate(dataset, metrics=...)`. Never receives external/user input. |
| `tests/conftest.py` | Two log-level overrides (`logging.getLogger("ragas")`) — no SDK call. |
| `tests/unit/evaluation/test_evaluate_with_ragas.py` | Mocks `ragas.dataset_schema`, `ragas.llms`, `ragas.metrics`, `ragas.metrics.collections` via `MagicMock`. The actual `ragas` package is never imported in the test path. |

Runtime entrypoints — verified by `grep -nE "^eval-rag" Makefile`:

```
Makefile:942: eval-rag: ## Run RAG evaluation with RAGAS metrics
Makefile:950: eval-rag-quick: ## Quick RAG evaluation (10 samples)
Makefile:956: eval-rag-full: ## Full RAG evaluation with all metrics
```

`make eval-rag*` is the only path that actually loads `ragas`. None of
the bot/API/Mini-App/voice runtimes import `src.evaluation.ragas_evaluation`.

**Net exposure:** `ragas` runs only when an operator manually invokes
`make eval-rag` (or one of its variants). Input to `ragas.evaluate(...)`
comes from a **locally curated ground-truth dataset** under `tests/eval/`,
not from user-facing channels (Telegram messages, Mini App requests,
voice transcriptions, ingestion documents). The CVE-2026-6587 attack
surface — whatever it requires — is not reachable from any production
runtime path.

### `diskcache` — transitive-only via `ragas`

`diskcache` is **not declared anywhere** in this repository:

```bash
$ grep -i diskcache pyproject.toml services/*/pyproject.toml telegram_bot/pyproject.toml
(no output)

$ grep -rn -E "(import diskcache|from diskcache)" \
       src/ telegram_bot/ mini_app/ services/ scripts/ tests/
(no output)
```

`uv.lock` resolves it as a transitive dependency of `ragas`:

```
[[package]]
name = "ragas"
...
dependencies = [
    ...
    { name = "diskcache" },
    ...
]
```

The `eval` optional extra is the only install path that pulls
`diskcache` into the venv. The bot, Mini App, ingestion, and voice
images do not install the `eval` extra; their Dockerfiles pin the base
runtime install set explicitly.

**Net exposure:** identical to `ragas` — the package is loaded only when
a developer or operator runs the evaluation pipeline locally with `uv
sync --extra eval` followed by `make eval-rag*`. CVE-2025-69872 is not
reachable from production deployments.

## Mitigation

The audit decision is **monitor-and-isolate**, not "patch-or-replace":

1. **No production code change.** Both packages already sit outside the
   production install set; no further isolation is achievable without
   removing the `eval` extra altogether.
2. **Lock the seam with a contract test.** New test
   `tests/contract/test_dependabot_no_patch_isolation_contract.py`
   asserts the four invariants:
   - `ragas` stays in `[project.optional-dependencies].eval` (and only there).
   - `ragas` does not leak into any subpackage `pyproject.toml`.
   - `diskcache` is not declared as a direct dependency anywhere.
   - First-party Python source does not `import diskcache`, and `import
     ragas` is only in `src/evaluation/`.
3. **Track upstream.** Watch the
   [`ragas`](https://github.com/explodinggradients/ragas) and
   [`diskcache`](https://github.com/grantjenks/python-diskcache)
   repositories for a patched release. Reopen #2043 (or its successor)
   if a fix is shipped so we can bump and remove the suppression.
4. **Do not blanket-dismiss the alerts.** Per the issue body: *"Do not
   dismiss these alerts without explicit risk acceptance."* The
   contract test plus this document are that explicit acceptance.

## Verification commands

```bash
# Confirm ragas is only in the eval extra
python -c "import tomllib; cfg = tomllib.load(open('pyproject.toml','rb')); \
  print({k: 'ragas' in [d.split('>=')[0].split('==')[0] for d in v] \
         for k, v in cfg['project']['optional-dependencies'].items()})"

# Confirm no first-party imports of diskcache
grep -rn -E "(import diskcache|from diskcache)" src/ telegram_bot/ mini_app/ services/ scripts/ tests/

# Confirm ragas imports stay under src/evaluation/
grep -rn -E "(import ragas|from ragas)" src/ telegram_bot/ mini_app/ services/ scripts/ \
  | grep -v ^src/evaluation/

# Run the contract test
uv run pytest tests/contract/test_dependabot_no_patch_isolation_contract.py -q
```

All four commands return clean results on `dev` at the time of this audit.
