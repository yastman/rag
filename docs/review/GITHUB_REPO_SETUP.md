# GitHub Repository Setup

This checklist is for making the repository understandable and safe when access
is shared with recruiters, technical interviewers, or collaborators.

## Repository Metadata

Recommended GitHub sidebar description:

> AI real-estate automation platform: Telegram bot, RAG, apartment search, CRM
> workflows, voice agent, Langfuse observability, and Dockerized AI runtime.

Recommended topics:

```text
rag
langgraph
telegram-bot
qdrant
langfuse
fastapi
docker
real-estate
ai-agents
crm
kommo
voice-ai
```

Recommended homepage link:

- a live demo, sanitized demo video, or `docs/portfolio/resume-case-study.md`
  rendered through GitHub.

## Default Review Entry Points

Pin or link these prominently:

- `README.md`
- `docs/portfolio/resume-case-study.md`
- `docs/review/PROJECT_GUIDE.md`
- `docs/review/ACCESS_FOR_REVIEWERS.md`
- `DOCKER.md`

## Branch And Release Hygiene

Recommended setup:

- default branch: `main` for public portfolio repos, or document clearly if
  `dev` is the active integration branch.
- protect the default branch.
- require PRs for changes.
- require fast CI checks before merge.
- disallow force pushes to protected branches.
- create a review snapshot tag such as `portfolio-review-2026-05`.

If the everyday integration branch is not `main`, explain that in `README.md`
and keep PR/release instructions consistent.

## CI Expectations

Minimum useful checks:

- lint and format
- type checking
- focused unit tests
- Compose config validation for runtime-sensitive changes
- secret scanning friendly repository layout

For this repository, local verification remains stronger than CI. README should
say that CI is a guardrail and local `make check` plus focused tests are the
primary evidence for code changes.

## Security And Sanitization

Before granting external access:

- verify no `.env`, tokens, SSH keys, database dumps, or production logs are in
  the repository.
- verify screenshots and docs do not expose client data or real credentials.
- keep `.env.example` complete but non-secret.
- avoid publishing VPS IPs, private hostnames, or deploy keys.
- review Git history if real secrets were ever committed.

Recommended files:

- `.env.example`
- `SECURITY.md`
- `docs/review/ACCESS_FOR_REVIEWERS.md`

## README Checklist

The README should answer these in under one minute:

- What is the project?
- What business problem does it solve?
- What are the main subsystems?
- What is technically interesting?
- How should a reviewer inspect it safely?
- Which docs explain the architecture?
- What are the honest limitations?

## Portfolio Review Checklist

Before sending a repository link, verify:

- `README.md` has a reviewer path.
- `docs/review/PROJECT_GUIDE.md` maps important folders.
- `docs/review/ACCESS_FOR_REVIEWERS.md` says what is safe to run.
- `docs/portfolio/resume-case-study.md` is accurate and conservative.
- outdated claims are removed or softened.
- `git status` does not include accidental secrets, logs, dumps, or local-only
  scratch files intended to stay private.
