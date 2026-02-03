---
paths: "Makefile, pyproject.toml, uv.lock, .pre-commit-config.yaml"
---

***REMOVED*** Build & Tooling

Project uses **uv** package manager (2026 best practice) with pre-commit hooks.

***REMOVED******REMOVED*** Package Management

***REMOVED******REMOVED******REMOVED*** uv Commands

| Command | Purpose |
|---------|---------|
| `uv sync` | Install all deps from uv.lock |
| `uv sync --no-dev` | Production only |
| `uv add package` | Add dependency |
| `uv add package --dev` | Add dev dependency |
| `uv remove package` | Remove dependency |
| `uv lock` | Regenerate lock file |
| `uv lock --upgrade` | Upgrade all deps |
| `uv run command` | Run in venv |

***REMOVED******REMOVED******REMOVED*** Makefile Targets

| Target | Command | Purpose |
|--------|---------|---------|
| `make install` | `uv sync --no-dev` | Production deps |
| `make install-dev` | `uv sync` | All deps |
| `make lock` | `uv lock` | Regenerate lock |
| `make update` | `uv lock --upgrade` | Upgrade all |
| `make setup-hooks` | `uv run pre-commit install` | Install git hooks |

***REMOVED******REMOVED*** Pre-commit Hooks

**Status:** Activated (`.git/hooks/pre-commit`, `.git/hooks/pre-push`)

***REMOVED******REMOVED******REMOVED*** Hooks Configuration

File: `.pre-commit-config.yaml`

| Hook | Stage | Purpose |
|------|-------|---------|
| ruff-check | pre-commit | Lint + auto-fix |
| ruff-format | pre-commit | Code formatting |
| trailing-whitespace | pre-commit | Trim whitespace |
| end-of-file-fixer | pre-commit | Ensure newline |
| check-yaml/toml/json | pre-commit | Syntax check |
| check-added-large-files | pre-commit | Block >1MB files |
| branch-protection | pre-push | Warn on main/master |

***REMOVED******REMOVED******REMOVED*** Commands

```bash
***REMOVED*** Install hooks (one-time)
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

***REMOVED*** Run manually
uv run pre-commit run --all-files

***REMOVED*** Skip hooks (emergency only)
git commit --no-verify
```

***REMOVED******REMOVED******REMOVED*** Bypass for CI

```bash
***REMOVED*** Use --no-verify only when:
***REMOVED*** 1. Pre-existing lint errors not related to your changes
***REMOVED*** 2. Documented in commit message
git commit --no-verify -m "feat: ... (skip hooks: pre-existing E402)"
```

***REMOVED******REMOVED*** Lock File

**File:** `uv.lock` (committed to git)

- Ensures reproducible builds across dev/CI/prod
- Regenerate after pyproject.toml changes: `uv lock`
- Verify in CI: `uv lock --check`

***REMOVED******REMOVED*** Dependencies

***REMOVED******REMOVED******REMOVED*** Production (pyproject.toml `[project.dependencies]`)

Key packages:
- `qdrant-client>=1.15.0` — Vector DB
- `voyageai>=0.3.0` — Embeddings
- `cocoindex>=0.1.60` — Ingestion
- `langfuse>=3.0.0` — Observability

***REMOVED******REMOVED******REMOVED*** Development (`[project.optional-dependencies.dev]`)

Key packages:
- `ruff>=0.6.0` — Linter + formatter
- `mypy>=1.11.0` — Type checking
- `pytest>=8.3.0` — Testing
- `pytest-httpx>=0.35.0` — HTTP mocking
- `pre-commit>=3.0.0` — Git hooks

***REMOVED******REMOVED*** Troubleshooting

| Issue | Fix |
|-------|-----|
| `uv: command not found` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Lock file outdated | `uv lock` |
| Pre-commit not running | `uv run pre-commit install` |
| Dependency conflict | `uv lock --upgrade-package X` |
