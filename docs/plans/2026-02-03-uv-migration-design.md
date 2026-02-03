# UV Migration Design — Best Practices 2026

## Overview

Migrate project from `pip` to `uv` for faster, reproducible builds across development, CI/CD, and Docker environments.

## Current State

| Component | Current | Target |
|-----------|---------|--------|
| Makefile | `pip install -e .` | `uv sync` |
| CI/CD | `pip install`, `cache: pip` | `uv sync`, `cache: uv` |
| Lock file | None | `uv.lock` (committed) |
| Pre-commit | Configured, not installed | Activated |
| Docs | pip instructions | uv instructions |

## Architecture

```
Developer                    CI/CD                      Docker
    │                          │                          │
    ▼                          ▼                          ▼
uv sync                    uv sync                    uv sync
    │                          │                          │
    ▼                          ▼                          ▼
uv.lock ◄──────────────────────┴──────────────────────────┘
(single source of truth)
```

**Key principle:** One `uv.lock` file ensures identical dependencies everywhere.

---

## Component 1: Makefile Migration

### Changes

```makefile
# OLD
install:
    pip install -e .

install-dev:
    pip install -e ".[dev]"

test:
    pytest tests/

# NEW
install:
    uv sync --no-dev

install-dev:
    uv sync

test:
    uv run pytest tests/

lint:
    uv run ruff check .

format:
    uv run ruff format .
```

### New Targets

```makefile
# Lock file management
lock:
    uv lock

# Update all dependencies
update:
    uv lock --upgrade

# Update specific package
update-pkg:
    uv lock --upgrade-package $(PKG)

# Clean and reinstall
reinstall:
    rm -rf .venv
    uv sync
```

---

## Component 2: CI/CD Migration

### Current `.github/workflows/ci.yml`

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
    cache: "pip"

- run: pip install ruff mypy
- run: pip install -e ".[dev]"
```

### New CI/CD with uv

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"

- name: Install uv
  uses: astral-sh/setup-uv@v4
  with:
    version: "latest"
    enable-cache: true
    cache-dependency-glob: "uv.lock"

- name: Install dependencies
  run: uv sync

- name: Lint
  run: uv run ruff check src/ --output-format=github

- name: Type check
  run: uv run mypy src/ --ignore-missing-imports
```

### Benefits

| Metric | pip | uv | Improvement |
|--------|-----|-----|-------------|
| Install time | ~60s | ~5s | 12x faster |
| Cache hit | Partial | Full (lock-based) | Reproducible |
| Lock file | None | uv.lock | Deterministic |

---

## Component 3: uv.lock Management

### Generation

```bash
# Generate lock file from pyproject.toml
uv lock

# Verify lock file is up-to-date
uv lock --check
```

### Git Integration

```gitignore
# .gitignore — DO NOT ignore uv.lock
# uv.lock should be committed for reproducible builds
```

### CI Check

Add to CI to ensure lock file is in sync:

```yaml
- name: Verify lock file
  run: uv lock --check
```

---

## Component 4: Pre-commit Activation

### One-time Setup

```bash
# Install pre-commit hooks
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

# Verify installation
ls -la .git/hooks/pre-commit
```

### Add to Makefile

```makefile
setup-hooks:
    uv run pre-commit install
    uv run pre-commit install --hook-type pre-push
    @echo "✓ Pre-commit hooks installed"
```

---

## Component 5: Documentation Updates

### CLAUDE.md Changes

```markdown
## Quick Reference

\`\`\`bash
uv sync                 # Install all dependencies
make check              # Lint + types
make test               # All tests
\`\`\`

## Environment

1. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Copy `.env.example` → `.env`
3. Run: `uv sync && make docker-up`
```

### README.md Section

```markdown
## Installation

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Quick Start
\`\`\`bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone <repo>
cd rag-fresh
uv sync
cp .env.example .env
# Edit .env with your API keys

# Run
make docker-up
make test
\`\`\`
```

---

## Migration Steps

### Phase 1: Lock File (No Breaking Changes)

1. Generate `uv.lock`: `uv lock`
2. Commit to git
3. CI still uses pip (backwards compatible)

### Phase 2: Makefile

1. Update targets to use `uv sync` / `uv run`
2. Add new targets (`lock`, `update`, `setup-hooks`)
3. Test locally

### Phase 3: CI/CD

1. Add `astral-sh/setup-uv@v4` action
2. Replace `pip install` with `uv sync`
3. Add lock file verification step

### Phase 4: Documentation

1. Update CLAUDE.md
2. Update README.md
3. Add troubleshooting section

### Phase 5: Activation

1. Run `uv run pre-commit install`
2. Verify hooks work
3. Announce to team

---

## Rollback Plan

If issues arise:

```bash
# Makefile: Keep pip targets as aliases
install-pip:
    pip install -e ".[dev]"

# CI: Can revert to pip by removing setup-uv step
# Lock file: Can be regenerated anytime with `uv lock`
```

---

## Success Criteria

- [ ] `uv.lock` committed and up-to-date
- [ ] `make install-dev` uses uv
- [ ] CI uses uv with caching
- [ ] CI verifies lock file
- [ ] Pre-commit hooks installed and working
- [ ] CLAUDE.md updated
- [ ] README.md updated
- [ ] Local dev workflow tested
- [ ] CI pipeline passes

---

## Files to Modify

| File | Changes |
|------|---------|
| `Makefile` | Replace pip → uv, add new targets |
| `.github/workflows/ci.yml` | Add setup-uv, replace pip |
| `CLAUDE.md` | Update commands |
| `README.md` | Add uv installation instructions |
| `.gitignore` | Ensure uv.lock NOT ignored |

## Files to Create

| File | Purpose |
|------|---------|
| `uv.lock` | Dependency lock file (generated) |

---

## Appendix: uv Commands Reference

```bash
# Dependency management
uv sync                    # Install from lock file
uv sync --no-dev           # Production only
uv add package             # Add dependency
uv add package --dev       # Add dev dependency
uv remove package          # Remove dependency

# Lock file
uv lock                    # Generate/update lock
uv lock --check            # Verify lock is current
uv lock --upgrade          # Upgrade all deps
uv lock --upgrade-package X # Upgrade specific package

# Running commands
uv run pytest              # Run in venv
uv run python script.py    # Run script
uv run pre-commit install  # Run pre-commit

# Info
uv pip show package        # Package info
uv pip list                # List installed
uv tree                    # Dependency tree
```
