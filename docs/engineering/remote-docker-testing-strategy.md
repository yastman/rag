# Remote Docker Testing Strategy

Strategy for running the test suite when the Docker daemon lives on a
remote host (e.g. MacBook reachable via `DOCKER_HOST`). The local
`docker` CLI talks to the remote daemon transparently, but the
container ports listen on the *remote* host, not on `localhost`. Tests
that hard-code `http://localhost:6333` etc. will fail or skip.

This document captures the audit performed in
[#1552](https://github.com/yastman/rag/issues/1552) and turns it into a
durable per-tier matrix. It complements:

- [`test-writing-guide.md`](test-writing-guide.md) — test placement and
  marker rules (the canonical owner of tier policy).
- [`repo-hygiene-runbook.md`](repo-hygiene-runbook.md) — operator
  hygiene checks.
- [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md) — the
  end-to-end local setup ladder.

The matrix below is the source of truth for "what runs without Docker"
and for "what needs port forwarding when Docker is remote".

## TL;DR

| Want to run | Command | Docker daemon | Ports on localhost |
|-------------|---------|---------------|--------------------|
| Default fast lane (PR gate) | `make test` | not required | not required |
| Unit suite | `make test-unit` | not required | not required |
| Contract suite (static analysis) | `make test-contract` | not required | not required |
| Compose render checks | `make test-unit` (subset) | required (CLI only) | not required |
| Live integration / smoke / chaos / load / e2e | dedicated targets | required | **required** (forward or run locally) |

`make test` and `make test-unit` are safe with `DOCKER_HOST` pointed at
a remote host because they neither launch containers nor connect to
service ports.

## Tier matrix

### Category 1 — Pure unit / static analysis (≈85% of the suite)

No Docker, no live services. These run anywhere, including over a
remote `DOCKER_HOST`.

- `tests/unit/**` (~150 files) — fully mocked / pure functions.
- `tests/contract/**` — AST / static-analysis assertions.
- `tests/integration/test_graph_paths.py` — uses LangGraph mocks; runs
  in the fast lane (`make test`).
- `tests/unit/test_dockerfile_*.py` — read Dockerfile contents.
- `tests/unit/test_compose*.py` — parse compose YAML.
- `tests/unit/test_local_compose_contract.py`,
  `tests/unit/test_makefile_contract.py` — parse Makefile text.

### Category 2 — Docker CLI only (no running containers)

Need `docker` in `PATH`, but only call read-only commands like
`docker compose config --quiet`. They work seamlessly over
`DOCKER_HOST` because the CLI talks to the remote daemon. Each test
already has a `shutil.which("docker")` skip-guard.

- `tests/unit/test_docker_static_validation.py` — three compose render
  checks.
- `tests/unit/test_compose_langfuse_runtime_contract.py` — one compose
  render check.

### Category 3 — Need running services on **localhost**

Connect to host-side ports (`localhost:5432`, `localhost:6333`,
`localhost:6379`, `localhost:5001`, `localhost:8000`,
`localhost:8003`, `localhost:8080`, etc.). With a remote
`DOCKER_HOST`, the ports live on the *remote* machine, so localhost
checks either fail or skip via existing TCP / health-check guards.

| Path | Services | Behaviour without port forwarding |
|------|----------|-----------------------------------|
| `tests/integration/test_docker_services.py` | PostgreSQL, Redis, Qdrant, BGE-M3, Docling | TCP probe → graceful skip |
| `tests/integration/test_infrastructure.py` | Qdrant, Redis, Langfuse | TCP probe → graceful skip |
| `tests/integration/test_qdrant_*.py` (3 files) | Qdrant | hard-fail or skip |
| `tests/integration/test_gdrive_ingestion.py` | Qdrant + Docling | gated by `RUN_INTEGRATION` env |
| `tests/integration/test_voice_pipeline.py` | RAG API | HTTP probe → skip |
| `tests/integration/test_userbase_cache.py` | user-base | env-gated skip |
| `tests/smoke/**` | Qdrant, Redis, BGE-M3, Docling, LightRAG, user-base | TCP / fixture guards → graceful skip for most files |
| `tests/chaos/**` | Redis, BGE-M3, Qdrant / failure-mode mocks | mixed mock-only and live probes; skip or fail depending file |
| `tests/load/**` | Redis | TCP / auth guards → skip unless Redis is reachable |
| `tests/e2e/**` | Full stack (RAG API + Redis for current live flow) | skip or fail depending scenario |

To run any of these against a remote daemon you must either:

1. **SSH-forward the ports** to the remote host, e.g.
   `ssh -N -L 6333:localhost:6333 -L 6379:localhost:6379 mac-host`.
2. Or run the tests **on the remote host** itself via the
   `make remote-*` targets in the Makefile (which `ssh` into the host
   and run there).

### Category 4 — Misclassified as integration, actually unit

These files live under `tests/integration/` but use only mocks /
in-memory fakes. They are documented here so they remain visible until
the owners migrate them to `tests/unit/`. Do **not** add new files of
this shape; instead place pure-mock tests directly under
`tests/unit/<area>/` per
[`test-writing-guide.md`](test-writing-guide.md).

| File | Mock pattern |
|------|--------------|
| `tests/integration/test_colbert_backfill.py` | `_FakeQdrantStorage` / `_FakeSyncQdrantClient` (in-memory fakes) |
| `tests/integration/test_qdrant_service.py` | `unittest.mock.AsyncMock` / `MagicMock` / `patch` (no live Qdrant) |
| `tests/integration/test_basic_connection.py` | `urllib`-only Qdrant ping — connectivity check, belongs in `tests/smoke/` |

> **Known duplicates discovered during the audit** —
> `tests/unit/ingestion/test_colbert_backfill.py`,
> `tests/unit/test_colbert_backfill.py`, and
> `tests/unit/test_qdrant_service.py` already exist with overlapping but
> non-identical content. Migrating Category 4 files therefore requires
> a per-test diff and merge, not a flat `git mv`. Tracked as a
> follow-up subtask of #1552.

## Recommended workflow when Docker is remote

1. Run `make test` and `make test-unit` locally — these are tier-clean
   and need no daemon access.
2. For compose-render checks, the local `docker` CLI works through
   `DOCKER_HOST` automatically.
3. To exercise live tiers, either:
   - bring up the stack locally with `make` targets that omit
     `DOCKER_HOST`, or
   - use the `remote-*` Makefile family
     (`remote-core-up`, `remote-bot-up`, `remote-bot-logs`, …) which
     SSHs into the host and runs Compose there.
4. For smoke / e2e / chaos / load runs against the remote stack,
   forward the relevant ports over SSH so existing localhost-coded tests
   can connect without code changes. Common dev ports are PostgreSQL
   5432, Qdrant 6333, Redis 6379, BGE-M3 8000, Docling 5001,
   user-base 8003, RAG API 8080, and LiveKit 7880 when the voice
   profile is under test.

## Hygiene rules

- Do not add `localhost:<port>` strings to `tests/unit/**` or
  `tests/contract/**`; those tiers must remain Docker-free.
- New tests requiring real services go to `tests/integration/`,
  `tests/smoke/`, `tests/chaos/`, or `tests/e2e/` per
  [`test-writing-guide.md`](test-writing-guide.md), with the
  appropriate marker — they are the lanes that allow port-bound
  dependencies.
- Pure-mock tests must live in `tests/unit/<area>/` from the start.
  Adding a new mock-only test under `tests/integration/` is a
  classification bug.

## Verification

This document is grounded in:

- the issue body of #1552 (Categories 1-4 audit);
- a fresh scan of `tests/` confirming the file lists;
- the existing `path_to_marker` mapping in `tests/conftest.py` (pinned
  by `tests/contract/test_test_audit_1515_pinning_contract.py`).

## Refs

- #1552 — original audit and strategy request.
- #1515 — broader test-suite audit that flagged the misclassification
  pattern.
- [`test-writing-guide.md`](test-writing-guide.md) — placement /
  marker contract.
- `Makefile` — `test`, `test-unit`, `test-contract`, and the
  `remote-*` family targets.
