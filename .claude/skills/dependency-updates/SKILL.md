---
name: dependency-updates
description: "Use when checking project freshness, reviewing outdated packages, auditing Docker image versions, or managing Renovate PRs. Triggers on /deps, 'обновления', 'проверь версии', 'what is outdated', 'dependency audit', 'check updates'"
---

# Dependency Updates

Full project audit via **Mend Renovate** — tracks Python, Docker, GH Actions automatically.

**Dashboard:** [developer.mend.io/github/yastman/rag](https://developer.mend.io/github/yastman/rag)

## How It Works

Mend Renovate is installed as a GitHub App. It scans the repo on schedule (Monday before 9:00 Kyiv) and:

1. Detects all dependencies across all tracked files
2. Creates PRs for available updates
3. Auto-merges patches and safe minor updates
4. Groups related updates (databases, ml-platform, ai-services)

**Config:** `renovate.json` in repo root.

## What's Tracked

| Layer | Files | Examples |
|-------|-------|---------|
| Docker Compose | `docker-compose.{dev,local,vps}.yml` | redis, qdrant, litellm, langfuse, loki, promtail |
| Dockerfiles | `Dockerfile*`, `services/*/Dockerfile` | python base, uv, docker/dockerfile syntax |
| Python (pyproject) | `pyproject.toml` | cocoindex, docling, langfuse, ragas, deepeval |
| Python (requirements) | `requirements.txt`, `services/*/requirements.txt`, `telegram_bot/requirements.txt` | aiogram, transformers, FlagEmbedding, qdrant-client |
| GH Actions | `.github/workflows/*.yml` | actions/checkout, astral-sh/setup-uv |

## Check Status

```bash
# Dependency Dashboard issue (full overview)
gh issue view 11

# Open Renovate PRs
gh pr list --author "renovate[bot]" --json number,title,state,mergeable

# Trigger manual re-scan
# → check the checkbox at bottom of issue #11
```

## Auto-merge Rules (renovate.json)

| Rule | What | Auto-merge |
|------|------|-----------|
| All patches | `1.2.3 → 1.2.4` | Yes |
| Database minor | pgvector, redis, qdrant | Yes |
| ML Platform | litellm, langfuse, mlflow | No (grouped PR) |
| AI Services | docling, lightrag | No (grouped PR) |
| Python base | `3.12 → 3.14` | No |

## Reviewing Updates

```bash
# View specific PR diff
gh pr view {number}
gh pr diff {number}

# Merge a PR
gh pr merge {number} --squash

# Request rebase
gh pr comment {number} --body "@renovate rebase"

# Force all awaiting PRs to create now
# → check "Create all awaiting schedule PRs" in issue #11
```

## Risk Categories

| Risk | Criteria | Action |
|------|----------|--------|
| SAFE | Auto-merged patches, grouped minor | Already handled |
| MEDIUM | Minor of ML/AI libs, Docker minor | Review PR diff, merge |
| RISKY | Major bumps (open PRs) | Test in branch before merge |
| CRITICAL | EOL, security vulns | Prioritize immediately |

### Known Breaking (project-specific)

numpy v2, transformers v5, huggingface-hub 1.x, pandas 3.0, sentence-transformers v5, Python 3.14

### Known Safe (fast-track)

pydantic, httpx, uvicorn, aiogram 3.x, qdrant-client 1.x, langfuse 3.x, cocoindex 0.3.x, fastapi 0.128.x, sentry-sdk, tenacity, tqdm, rich

## After Merging

```bash
# Pull merged changes
git pull

# Sync lock file
uv sync

# Run tests
pytest tests/unit/ -q
make check
```

## Common Mistakes

- **Merging ML major bumps without testing** — transformers v5 / sentence-transformers v5 can break HybridChunker and BGE-M3
- **Forgetting VPS compose** — Renovate tracks `docker-compose.vps.yml` too, but verify images match across envs
- **Ignoring "Awaiting Schedule"** — these are pending PRs waiting for Monday; check dashboard issue #11 to trigger early
- **RC images** — litellm uses RC tags (`ignoreUnstable: false` in config); review before merging
- **Not checking EOL** — Renovate flags updates but doesn't warn about approaching end-of-life
