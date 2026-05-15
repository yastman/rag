# Access For Reviewers

Use this file for technical review, portfolio review, hiring evaluation, or
getting oriented as a new contributor.

> **Start here.** Read this file first, then `README.md` and
> `docs/review/PROJECT_GUIDE.md`, before running any commands or inspecting
> code folders.

## Recommended Review Path

If you have 10 minutes:

1. Read `README.md`.
2. Read `docs/portfolio/resume-case-study.md`.
3. Skim `docs/review/PROJECT_GUIDE.md`.
4. Inspect `telegram_bot/graph/` for LangGraph orchestration.
5. Inspect `telegram_bot/agents/` and `telegram_bot/services/` for product logic.
6. Inspect `src/ingestion/unified/` for ingestion architecture.
7. Inspect `compose.yml` and `DOCKER.md` for runtime architecture.

If you have more time:

- Review `docs/QDRANT_STACK.md` for vector schema and ColBERT operations.
- Review `docs/INGESTION.md` and `docs/GDRIVE_INGESTION.md`.
- Review `docs/RAG_QUALITY_SCORES.md`.
- Review `tests/unit/`, `tests/contract/`, and `tests/eval/`.

## Safe Commands

These commands are intended for local review and should not call production
systems when the environment is configured safely. Approximate run times on a
modern laptop:

| Command | ~Duration | What it proves |
|---------|-----------|----------------|
| `uv sync` | 30–60 s | Dependencies resolve and lock |
| `make check` | 45–90 s | Lint and type-check pass |
| `uv run pytest tests/unit` | 1–3 min | Unit tests pass |
| `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services` | <5 s | Dev Compose config is valid |
| `COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config --services` | <5 s | VPS Compose config is valid |

For a narrower first pass, prefer focused tests around the subsystem being
reviewed, then `make check`.

## Do Not Run Without Coordination

- production deploy scripts
- real Kommo CRM write flows
- commands that require production `.env`
- VPS/k3s deploy commands
- destructive Docker or database cleanup commands
- ingestion against real production documents

## Environment Rules

- Use `.env.example` as the public contract.
- Do not request or inspect production `.env` files for code review.
- Use fake/demo credentials for local inspection.
- Treat Telegram, Kommo, Langfuse, LiveKit, and cloud credentials as external
  secrets, not repository content.

## Branch Context

- `dev` is the active integration branch; `main` lags behind and is used for
  stable snapshots. Reviewers inspecting recent work should look at `dev` and
  open PRs against it.

## What To Look At For Senior-Level Review

- State and routing contracts in `telegram_bot/graph/`.
- SDK/native API usage in `telegram_bot/integrations/` and `telegram_bot/services/`.
- Cheap-first apartment parsing in `telegram_bot/services/filter_extractor.py`.
- HITL safety boundaries in `telegram_bot/agents/hitl.py` and CRM tools.
- Ingestion determinism in `src/ingestion/unified/manifest.py` and
  `src/ingestion/unified/state_manager.py`.
- Runtime contract and healthchecks in Compose files.
- Evaluation and observability wiring in Langfuse-related scripts/tests.

## Known Limitations To Keep In Mind

- k3s manifests are partial and should not be treated as full Compose parity.
- local/dev monitoring exists through Loki/Alertmanager; production monitoring
  evidence should be reviewed separately.
- RAGAS and trace validation tooling exists, but some gates are manual rather
  than CI-enforced.
- Some user-facing strings remain outside Fluent localization files.
