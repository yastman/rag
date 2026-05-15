# Documentation Maintenance Guide

**Scope:** How agents and workers should create, update, and review documentation after code, config, or runtime changes.
**Related:** #1396

---

## 1. Purpose

Docs are part of the production surface. Stale docs waste agent time, mislead reviewers, and increase the blast radius of every config change. This guide defines the minimum maintenance contract for the repo.

---

## 2. Docs Lookup Order

When answering questions or writing documentation, use this order. Do not skip layers without a reason.

| Priority | Layer | Examples |
|---|---|---|
| 1 | **Project indexes** | `docs/README.md`, `docs/runbooks/README.md`, nearest folder `README.md` |
| 2 | **Nearest README / `AGENTS.override.md`** | `telegram_bot/README.md`, `src/ingestion/unified/AGENTS.override.md` |
| 3 | **Current code / config** | `compose.yml`, `Makefile`, `pyproject.toml`, service entrypoints |
| 4 | **Official docs / Context7** | SDK/framework docs for version-sensitive behavior |
| 5 | **Broad web / Exa** | Only when layers 1–4 do not answer the question |

**Rule:** `AGENTS.md` stays a **gateway** — it points to indexes and rules, but it does not duplicate long operations manuals. Navigation and detailed guidance belong in `docs/README.md`, `docs/runbooks/README.md`, and folder READMEs.

---

## 3. Canonical Owners (One Source of Truth per Fact)

| Fact | Canonical Doc | Do Not Duplicate In |
|---|---|---|
| Docker Compose files, profiles, services, ports, env, local project name | `DOCKER.md` | Folder READMEs, `ONBOARDING.md`, root `README.md` |
| Local developer flow, commands, validation ladder | `docs/LOCAL-DEVELOPMENT.md` | `ONBOARDING_CHECKLIST.md`, root `README.md` |
| Repo overview, primary entrypoints, high-level architecture | `README.md` (root) | `docs/PROJECT_STACK.md` (keep boundary: root = elevator pitch; `PROJECT_STACK` = subsystem map) |
| Folder ownership, entrypoints, boundaries, local checks | Nearest `README.md` | Parent READMEs, `AGENTS.md` |
| Test-writing rules | `docs/engineering/test-writing-guide.md` | `DEVELOPER_GUIDE.md` |
| Runtime/Compose contract tests | `tests/unit/test_docker_static_validation.py` + Compose fixtures | Markdown prose only |
| SDK/framework lookup order and versions | `docs/engineering/sdk-registry.md` | `AGENTS.md`, folder READMEs |
| Issue triage workflow | `docs/engineering/issue-triage.md` | `AGENTS.md` (gateway only) |
| Operational runbooks | `docs/runbooks/*.md` | `docs/TROUBLESHOOTING_*.md` (redirect or archive) |

Folder READMEs are **indexes**, not second sources of truth. They may summarize and link to canonical docs; they must not duplicate long Compose/env/deploy rules.

---

## 4. Impact Gate (When Must Docs Be Updated?)

Before finishing any task that changes code, config, tests, runtime behavior, public commands, service boundaries, API routes, Docker/Compose files, env vars, dependencies, or user-visible workflow, ask:

1. **Did this task change a documented command, port, env var, profile, service name, route, entrypoint, runtime version, test command, dependency, or owner boundary?**
2. **Which canonical doc owns that fact?**
3. **Is that doc inside the current `RESERVED_FILES`?**

**Disposition:**

- **Impacted + reserved** → Update docs in this PR.
- **Impacted + not reserved** → Do not edit outside reservation. Report a `new_bugs` entry with evidence and `recommended_disposition: new_or_existing_issue`.
- **Not impacted** → Add command evidence or a finding: `Docs impact check: no documented contract changed`.

Do not finish code/config/runtime work without either updating docs or explicitly reporting why no docs update is needed.

---

## 5. Agent / Worker Update Rules

### 5.1 Before Editing Docs

Inspect the code/config that owns the fact:

- **Docker/runtime docs:** `compose.yml`, `compose.dev.yml`, `Makefile`, Dockerfiles, healthchecks, `tests/fixtures/compose.ci.env`.
- **Service docs:** Service entrypoint, Dockerfile, compose service name, tests.
- **API docs:** Code route definitions, Dockerfile `EXPOSE`, compose ports/healthcheck, README entrypoints.
- **SDK/framework docs:** If behavior is version-sensitive, use Context7/official-docs summary; if missing and tools are available, refresh docs before writing.

Do not preserve stale text just because it was already documented. **Code/config wins** unless the task is explicitly to change the contract.

### 5.2 README Index Contract

Every maintained folder README should be concise and scannable:

- Purpose (one paragraph)
- Entrypoints / important files
- Runtime services or dependencies when relevant
- Owner boundaries / invariants
- Focused checks (commands)
- **See also** links to canonical docs

Use **relative links**. Never write absolute local paths such as `/home/USER/...`.

### 5.3 Docker Docs Contract

- `DOCKER.md` owns service/profile/project-name/env/port truth.
- `docs/LOCAL-DEVELOPMENT.md` owns the day-to-day local sequence.
- Folder READMEs should link to `DOCKER.md`, not duplicate profile matrices.
- Canonical local Compose project is `dev`; do not document worktree-named Docker projects.
- LiveKit/voice stays separate/off by default unless the task explicitly re-enables it.

When updating Docker docs, validate at least one relevant command or explain why skipped:

```bash
COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml --compatibility config --services
make check
```

### 5.4 Audit and Plan Docs

- New validation reports and audit summaries go in `docs/reports/` with a `YYYY-MM-DD-` prefix when they are intended for active review.
- Historical audit artifacts should not remain in the public docs tree after follow-up is complete.
- Plans go in `docs/plans/` when they are intended to be public and durable.
- Reports, audits, and plans are **dated evidence**, not timeless source of truth. They may be archived when follow-up is complete.
- Do not let audit findings silently replace canonical policy docs.

---

## 6. Review Traps

Block or fix docs that contain any of the following:

| Trap | Example | Fix |
|---|---|---|
| **Contradicted boundaries** | A package README says "no dependency on X" while imports prove otherwise | Update README or code; do not leave the contradiction |
| **Stale ports / healthcheck paths / service names / profile names / Python versions** | Doc lists an outdated local port while compose maps the current one | Edit canonical doc; link from others |
| **Absolute local links** | `/repo/...` | Replace with relative repo paths |
| **Raw secrets / tokens / DSNs / chat IDs / phone numbers / private URLs** | Pasted `.env` line with `TELEGRAM_BOT_TOKEN=123:abc` | Redact to `<redacted>` or describe the variable name |
| **Instructions to use VPS/deploy/live services for local-only tasks** | "Run on production Langfuse to test" | Restrict to local Docker endpoints |
| **Duplicate source-of-truth tables** | Folder README repeats the full Compose profile matrix from `DOCKER.md` | Replace with a link to `DOCKER.md` |
| **Marketing prose in READMEs** | "Revolutionary AI-powered platform" | Replace with purpose, entrypoints, boundaries, checks |
| **Broken relative links** | Link to `.claude/rules/features/telegram-bot.md` which no longer exists | Fix or remove the link |

---

## 7. Verification for Doc Changes

Run these checks before claiming a docs task is complete:

```bash
# 1. No trailing whitespace or conflict markers
git diff --check

# 2. Changed files are only the intended docs
git diff --name-only

# 3. Markdown relative-link existence check (example for this repo)
# Python one-liner: scan for relative links and assert the path exists
python3 -c "
import re, sys
from pathlib import Path
files = Path('docs').rglob('*.md')
files = list(files) + [Path('README.md'), Path('DOCKER.md'), Path('AGENTS.md')]
bad = []
for f in files:
    text = f.read_text()
    for m in re.finditer(r'\]\(([^)]+)\)', text):
        link = m.group(1)
        if link.startswith('http') or link.startswith('#'):
            continue
        target = (f.parent / link).resolve()
        if not target.exists():
            bad.append((f, link))
if bad:
    for f, link in bad:
        print(f'BROKEN: {f} -> {link}')
    sys.exit(1)
print('All relative links OK')
"
```

If `make check` is required by the worker prompt, run it. If the task is docs-only and no code/runtime behavior changed, record:

```json
{
  "cmd": "make check",
  "exit": 0,
  "status": "skipped",
  "required": false,
  "summary": "docs-only; no code/runtime behavior changed"
}
```

---

## 8. Fast Doc Search Recipes

Add or preserve these recipes in folder READMEs and runbook indexes:

```bash
# Cross-cutting code search by topic
rg -n "Langfuse|trace|score|observation" docs/runbooks docs/audits telegram_bot src scripts
rg -n "Redis|cache|semantic cache|redis-cli" docs/runbooks telegram_bot src tests
rg -n "Qdrant|collection|vector|ColBERT|hybrid" docs/runbooks src telegram_bot tests
rg -n "LiteLLM|proxy|master_key|provider" docs/ README.md compose*.yml

# Find all folder READMEs and AGENTS overrides
find . -maxdepth 3 \( -name 'README.md' -o -name 'AGENTS.override.md' \) | sort

# Find duplicate source-of-truth phrases
rg -n -i "source of truth|canonical" docs/ README.md DOCKER.md AGENTS.md
```

---

## 9. Summary Checklist for Workers

Before finishing any PR that touches docs:

- [ ] I inspected the code/config that owns the fact before editing docs.
- [ ] I updated the canonical doc, not a duplicate.
- [ ] I did not duplicate Compose/env/test rules in folder READMEs.
- [ ] I used relative links, not absolute paths.
- [ ] I redacted any secrets, tokens, or DSNs.
- [ ] I ran `git diff --check`.
- [ ] I ran a relative-link existence check or recorded why it was skipped.
- [ ] If the task changed runtime behavior, I validated the relevant command or recorded why skipped.
- [ ] If the task is docs-only, I recorded `make check` as skipped with reason `docs-only; no code/runtime behavior changed`.
- [ ] I did not edit `AGENTS.md` to duplicate navigation that belongs in `docs/README.md` or `docs/runbooks/README.md`.
