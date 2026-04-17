# Dependency Upgrade Design

## Context

This repository is a production multi-system product with several dependency surfaces that move at different speeds:

- root Python application dependencies in `/home/user/projects/rag-fresh/pyproject.toml` and `/home/user/projects/rag-fresh/uv.lock`;
- nested Python manifests in `/home/user/projects/rag-fresh/telegram_bot/` and service images under `/home/user/projects/rag-fresh/services/`;
- frontend dependencies in `/home/user/projects/rag-fresh/mini_app/frontend/package.json`;
- Docker image tags and base images across runtime and deployment files;
- CI, cleanup, and automation scripts that shape how dependency updates enter the repository.

The repository currently shows workflow drift:

- the active local integration branch is `dev`;
- recent merged PRs are landing in `dev`;
- `renovate.json` declares `"baseBranches": ["dev"]`;
- open Renovate PRs are currently targeting `main`;
- deploy and some hygiene scripts still encode `main` as the operational default branch.

That means "upgrade everything to latest" is not a single package-management task. It is a workflow alignment problem plus a staged dependency modernization effort.

## Problem

If we upgrade dependencies without first aligning the dependency workflow, the repository will keep generating mis-targeted PRs, unclear CI results, and cleanup behavior that assumes a different branch model from the one used in practice.

If we also try to update Python, npm, Docker, and runtime service images in one sweep, failures will be hard to attribute and regressions will be expensive to unwind.

We need a dependency upgrade strategy that:

- treats `dev` as the current integration source of truth;
- restores predictable Renovate behavior;
- upgrades dependencies to latest feasible versions;
- isolates risky migrations instead of burying them inside a giant bump PR;
- preserves runtime verification for production-facing surfaces.

## Goals

- Align dependency automation and repo workflow around `dev`.
- Upgrade dependencies in bounded waves rather than a one-shot mega-bump.
- Use the smallest grouping that still preserves compatibility reasoning.
- Run fresh verification after each wave.
- Surface blocked or migration-heavy major upgrades explicitly instead of hiding them.

## Non-Goals

- This design does not implement the upgrades itself.
- This design does not redefine release promotion from `dev` to `main`.
- This design does not promise that every upstream major version is immediately adoptable.
- This design does not collapse all open Renovate PRs into one branch or one PR.

## Current-State Findings

### Branch and Automation Drift

- `git branch --show-current` reports `dev`.
- Recent merged PRs are targeting `dev`.
- Open Renovate PRs are targeting `main`.
- `.github/workflows/ci.yml` runs CI on both `main` and `dev`, but deploy is gated on pushes to `main`.
- `scripts/git_hygiene.py` and `scripts/repo_cleanup.sh` treat `main` as the default merged/cleanup branch.

### Dependency Surfaces

- Root Python dependency management is centered on `uv` with a large shared `pyproject.toml`.
- The mini app uses npm with React, Vite, and Vitest.
- Runtime images span Compose files, service Dockerfiles, and image digests managed partly by Renovate.
- The repository contains runtime-sensitive surfaces where dependency changes must be validated via Compose, not only unit tests.

### Execution Risk

- Python dependency upgrades can affect Telegram bot behavior, API behavior, LangGraph state handling, RAG retrieval, ingestion, and voice components.
- Frontend dependency upgrades can break build output, tests, or Telegram mini app runtime behavior.
- Docker and base image upgrades can change service availability without any Python test failure.

## Recommended Approach

Use a two-layer strategy:

1. Fix the dependency control plane first.
2. Execute upgrades in bounded waves by compatible subsystem.

This is better than both extremes:

- better than manual ad hoc bumps, because it fixes the workflow that creates the upgrade stream;
- better than a mega-bump, because each failure stays attributable to one dependency cluster.

## Dependency Control Plane

Before aggressive upgrades, the repository should behave consistently for dependency work.

### Source-of-Truth Branch

For dependency integration, `dev` is treated as the active source of truth because:

- current local work is on `dev`;
- current merged PR history points to `dev`;
- `renovate.json` already declares `dev` as the base branch.

### Required Alignment

The implementation phase should align these surfaces with that branch reality:

- Renovate target branch behavior;
- CI expectations for dependency PRs;
- branch-specific cleanup and hygiene assumptions;
- documentation or scripts that imply a different integration branch.

### Release Semantics

This design does not change the fact that deployment may still happen from `main`.
Instead, it makes dependency work stabilize in `dev` first, with release promotion handled separately by the existing repo workflow.

## Upgrade Waves

Dependency work should move in waves, each with a bounded responsibility and bounded failure domain.

### Wave 1: Workflow and Tooling Alignment

Purpose:
- eliminate branch drift and restore predictable dependency automation.

Scope:
- `renovate.json`;
- `.github/workflows/ci.yml`;
- branch-assuming hygiene and cleanup scripts;
- any dependency-process docs touched by the same problem.

Expected outcome:
- dependency PRs target `dev`;
- CI results on dependency work reflect the real integration branch;
- cleanup and hygiene commands no longer misclassify merged branches because they assume the wrong default branch.

### Wave 2: Python Dependency Modernization

Purpose:
- update the shared Python ecosystem to latest feasible versions.

Scope:
- root `pyproject.toml` and `uv.lock`;
- nested maintained Python manifests where they mirror actively used runtime surfaces;
- grouped upgrades for core libs, API stack, RAG stack, bot stack, LangGraph stack, and document-processing stack.

Rules:
- keep related packages together when compatibility is coupled;
- isolate migration-heavy majors if they require code changes disproportionate to the rest of the wave;
- prefer fixing concrete regressions revealed by tests over speculative compatibility shims.

Expected outcome:
- Python dependencies are updated wave by wave with attributable fixes;
- blocked majors are listed explicitly with reasons.

### Wave 3: Mini App Dependency Modernization

Purpose:
- update the frontend toolchain and runtime dependencies without mixing them into Python failures.

Scope:
- `/home/user/projects/rag-fresh/mini_app/frontend/package.json`;
- the corresponding npm lockfile;
- grouped updates for React/runtime, Vite/build, Vitest/test, and related typings.

Rules:
- keep build-toolchain upgrades grouped where version compatibility is coupled;
- treat changes to test runner, build pipeline, or type-checking behavior as dedicated checkpoints.

Expected outcome:
- mini app dependencies reach current feasible versions with green frontend build and test flow.

### Wave 4: Docker and Runtime Image Modernization

Purpose:
- update base images and service images after application-level dependency surfaces are stable.

Scope:
- Dockerfiles, Compose-referenced images, and Renovate-managed image digests or tags.

Rules:
- runtime-impacting image updates require Compose validation even if Python and npm tests pass;
- group images by subsystem only when they are operationally coupled.

Expected outcome:
- container and runtime image updates are validated against the actual service matrix.

## Grouping Strategy

The unit of change should usually be a compatibility cluster, not a single package and not the whole repository.

Recommended grouping order:

- workflow/tooling;
- Python core and shared libraries;
- Python framework-specific clusters such as bot, LangGraph, or RAG stack;
- frontend runtime and build/test toolchain;
- Docker base and service images.

This gives most of the debugging value of one-by-one updates without the operational overhead of dozens of tiny PRs.

## Verification Strategy

Every wave must end with fresh verification before the next wave begins.

### Base Verification

For most code changes:

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

### Runtime and Compose Verification

For runtime-impacting changes:

- `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services`
- `COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config --services`
- `make verify-compose-images`

### Wave Discipline

Within each wave:

- run targeted checks early for the packages being changed;
- fix regressions while the scope is still narrow;
- run the full required gate at the end of the wave;
- only proceed when that wave is stable or when remaining failures are explicitly documented as pre-existing blockers.

## Stop Rules

- If a major version requires a structural migration, stop and split it into a dedicated follow-up track.
- If an open Renovate PR already exposes a concrete failing path, investigate that real failure before broadening the same stack update.
- If branch automation still conflicts between `dev` and `main`, treat that as a blocking dependency-workflow issue, not an optional cleanup.
- Do not mix unrelated runtime fixes into a dependency wave unless they are strictly required to restore compatibility.

## Definition Of Done

This effort is complete when:

- dependency automation is aligned with `dev` as the active integration branch;
- all feasible dependency surfaces have been upgraded in bounded waves;
- blocked majors or deferred migrations are listed with explicit reasons;
- each completed wave has fresh verification evidence;
- the resulting changes are reviewable and attributable, not one opaque repository-wide bump.

## Implementation Guidance

Implementation should follow this spec with an explicit plan document that sequences:

- workflow alignment first;
- then Python waves;
- then frontend waves;
- then Docker/runtime waves.

That implementation plan should preserve the same stop rules and verification gates defined here.
