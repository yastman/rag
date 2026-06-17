# Dependency Hygiene Audit (#2710)

Audit of root and service-local manifests. Produced 2026-06-17.

## Summary

| Finding | Severity | Action |
|---|---|---|
| `core` extra is an exact duplicate of base deps | Low | Add comment clarifying intent; consider removing |
| `ingest` extra is an exact duplicate of `ingestion` | Low | Remove `ingest` alias or consolidate note |
| `aiohttp` and `requests` in root base: zero direct imports in `src/` | Low | Add comment clarifying transitive/safety-pin rationale |
| `bge-m3-api` test extra has 3 dead test deps | Low | Remove `qdrant-client`, `aiogram`, `langchain-core` from `[test]` |
| Dependabot only watches `/` — service manifests untracked | Medium | Add entries for `telegram_bot/`, `services/bge-m3-api/`, `services/docling/` |
| `archive/user-base/` has a live-looking pyproject.toml and lockfile | Low | No action required — archived surface, no Dockerfile in compose |

---

## Full Classification Table

| Package / manifest | Location | Current owner | Classification | Evidence | Action |
|---|---|---|---|---|---|
| `openai` | root base | src/runtime | core runtime | `src/runtime/llm/`, `src/adapters/llm/` | keep |
| `qdrant-client` | root base | src/retrieval, src/ingestion | core runtime | multiple direct imports in src/ | keep |
| `redis` | root base | src/runtime/integrations/cache | core runtime | cache layer | keep |
| `redisvl` | root base | src/runtime/integrations/cache | core runtime | semantic cache | keep |
| `pydantic-settings` | root base | src/config/settings.py | core runtime | app config | keep |
| `httpx` | root base | src/services/bge_m3_client.py | core runtime | HTTP client for BGE-M3 | keep |
| `tenacity` | root base | src/services/_retry.py | core runtime | retry logic | keep |
| `pyyaml` | root base | src/ config/ingestion | core runtime | YAML config/prompts | keep |
| `litellm` | root base | src/runtime/llm/ | core runtime | LLM provider router | keep |
| `python-dotenv` | root base | src/config | core runtime | env loading | keep |
| `typing-extensions` | root base | src/ | core runtime | typing compat | keep |
| `numpy` | root base | src/utils/serialization.py | core runtime | array serialisation for Qdrant | keep |
| `aiohttp` | root base | none direct in src/ | **transitive safety-pin** | pulled by litellm/openai transitively; declared for explicit version control | add comment explaining pin |
| `requests` | root base | none direct in src/ | **transitive safety-pin** | pulled by docling/fastembed/tenacity; no direct import in src/ or telegram_bot/ | add comment explaining pin |
| `phonenumbers` | root base | src/phone_utils.py | core runtime | used by telegram_bot via src.phone_utils | keep |
| `core` optional extra | root pyproject.toml | CI/docs symmetry | **exact duplicate of base deps** | automated check confirms identical set | add clarifying comment or remove if no CI target relies on it |
| `telegram` extra | root | telegram_bot surface | optional adapter | aiogram, aiogram-dialog, fluentogram, cachetools, asyncpg, uvloop | keep |
| `uvloop` | root `telegram` extra | telegram_bot/main.py | optional adapter dep | imported in `__main__` block; not in telegram_bot/pyproject.toml — telegram_bot Dockerfile uses its own manifest | keep in root `telegram` extra; note that telegram_bot Dockerfile does NOT get uvloop via its own lockfile |
| `providers` extra | root | anthropic/groq users | optional adapter | correct grouping | keep |
| `ml-local` extra | root | local model inference | optional profile dep | torch/FlagEmbedding/sentence-transformers/transformers | keep |
| `docs` extra | root | mkdocs | dev/docs-only | mkdocs-material + mkdocstrings | keep |
| `docling` extra | root | intentionally empty | optional profile dep | root talks to docling-serve over HTTP; comment explains rationale | keep |
| `ingestion` extra | root | src/ingestion | optional profile dep | pymupdf/docling/cocoindex/fastembed | keep |
| `ingest` extra | root | Makefile compat alias | **exact duplicate of `ingestion`** | automated check confirms identical set | add comment; consider consolidating |
| `all` extra | root | meta-extra | correct | covers core, telegram, providers, docs, ingest, ml-local | keep |
| `ruff` | root dev group | CI/pre-commit | dev/test | linter/formatter | keep |
| `mypy` | root dev group | CI type-check | dev/test | type checker | keep |
| `pylint` | root dev group | none active in CI | dev/test | not in Makefile `check` target, not in CI | consider removing |
| `bandit` | root dev group | none active in CI | dev/test | not in Makefile `check` target, not in CI | consider removing |
| `vulture` | root dev group | none active in CI | dev/test | not in Makefile `check` target, not in CI | consider removing |
| `telethon` | root dev group | scripts/e2e/ | dev/test | used by scripts/e2e/telegram_client.py, auth.py, etc. | keep |
| `pytest*` + test plugins | root dev group | tests/ | dev/test | all used | keep |
| `click` | root dev group | scripts/ | dev/test | CLI scripts | keep |
| `pre-commit` | root dev group | .pre-commit-config.yaml | dev/test | git hooks | keep |
| `fakeredis` | root dev group | tests/unit/ | dev/test | redis mocking | keep |
| `pytest-split` | root dev group | Makefile split targets | dev/test | test splitting | keep |
| `aiogram`, `aiogram-dialog`, `fluentogram`, `cachetools`, `asyncpg`, `phonenumbers`, `openai`, `litellm`, etc. | telegram_bot/pyproject.toml | telegram_bot/ | internal service runtime | all actively imported | keep |
| `langfuse` | services/bge-m3-api/pyproject.toml | bge-m3-api app | internal service runtime | OTel/observability | keep |
| `qdrant-client` | services/bge-m3-api `[test]` extra | no test files exist | **dead test dep** | zero `.py` test files in services/bge-m3-api/; not imported in app.py | remove from `[test]` |
| `aiogram` | services/bge-m3-api `[test]` extra | no test files exist | **dead test dep** | same as above | remove from `[test]` |
| `langchain-core` | services/bge-m3-api `[test]` extra | no test files exist | **dead test dep** | same as above | remove from `[test]` |
| `docling-serve[ui]`, `torch`, `torchvision` | services/docling/pyproject.toml | docling service | internal service runtime | Dockerfile installs via `uv sync --extra docling` | keep |
| `docling-serve[ui]`, `torch`, `torchvision` | services/docling `docling` optional extra | Dockerfile | mirror of base | comment explains intent | keep; comment is adequate |
| all deps | archive/user-base/pyproject.toml | archived | archived-surface | `archive/user-base/` has no entry in compose.yml; archived | no action needed |
| `uv.lock` (root) | `/uv.lock` | root project | active | CI job `uv-lock` verifies integrity | keep |
| `telegram_bot/uv.lock` | `telegram_bot/uv.lock` | telegram_bot | internal service | Dockerfile uses `--frozen` | keep |
| `services/bge-m3-api/uv.lock` | `services/bge-m3-api/uv.lock` | bge-m3-api service | internal service | Dockerfile uses `--frozen` | keep |
| `services/docling/uv.lock` | `services/docling/uv.lock` | docling service | internal service | Dockerfile uses `--frozen` | keep |
| `archive/user-base/uv.lock` | `archive/user-base/uv.lock` | archived | archived | not used by any active compose service | no action needed |
| Dependabot: root `/` only | `.github/dependabot.yml` | root pyproject.toml | active | CI `uv-lock` job checks root integrity | add entries for service manifests |
| Dependabot: `telegram_bot/` | missing | unconfigured | gap | updates to telegram_bot/pyproject.toml not auto-PRed | add dependabot entry |
| Dependabot: `services/bge-m3-api/` | missing | unconfigured | gap | updates not auto-PRed | add dependabot entry |
| Dependabot: `services/docling/` | missing | unconfigured | gap | updates not auto-PRed | add dependabot entry |

---

## Done-when checklist

- [x] Every heavy dependency has a clear owner and classification. (See table above.)
- [x] Root core install does not pull archived-surface dependencies. (`archive/user-base/` is not in compose.yml; `docling` extra is intentionally empty at root per existing comment; archived extras `observability`, `ui`, `mini-app`, `voice`, `eval` already removed by #2640.)
- [x] Service-local dependencies stay isolated to their service. (Each service has its own pyproject.toml and lockfile; Dockerfiles use `--frozen`.)
- [ ] Duplicate or unused manifests have child cleanup issues. (See below.)
- [ ] Dependabot tracks only authoritative live manifests. (See below — dependabot.yml needs service entries.)

## Child cleanup issues recommended

| Finding | Recommended action |
|---|---|
| `core` exact-duplicate extra | Add doc comment clarifying CI-docs-symmetry intent (trivial inline fix) |
| `ingest` exact-duplicate of `ingestion` | Consolidate: either remove `ingest` and update Makefile targets, or add a comment that `ingest` is a compat alias |
| `aiohttp` / `requests` direct-but-zero-import pins | Add inline comments explaining transitive safety-pin purpose |
| `pylint`, `bandit`, `vulture` in dev group but unused in CI | Open issue to remove or wire into a `make lint-full` target |
| `bge-m3-api` dead test deps (`qdrant-client`, `aiogram`, `langchain-core`) | Remove from `[test]` optional extra |
| Dependabot missing service entries | Update `.github/dependabot.yml` with entries for `telegram_bot/`, `services/bge-m3-api/`, `services/docling/` |
