# AGENTS.override.md

## Scope
- Applies to `mini_app/frontend/src/**` (React + TypeScript Telegram Mini App frontend).
- Extends root `AGENTS.md` with frontend-specific constraints.

## Local Rules
- TypeScript strict mode is mandatory — no `any`, no `// @ts-ignore` without an inline rationale and a tracking issue.
- Keep boundaries:
  - `components/` — presentational React components.
  - `pages/` — route-level views.
  - `guards/` — auth/route guards.
  - `api.ts` — single source of truth for backend HTTP calls.
- Do not import from `telegram_bot/` or `src/` Python paths; the frontend talks to the backend over HTTP only.

## Required Validation
- Type check: `npm run typecheck` (in `mini_app/frontend/`).
- Unit tests (Vitest): `npm test` (in `mini_app/frontend/`).
- For UI changes, also run the relevant `__tests__/` suites under `mini_app/frontend/src/`.

## Guardrails
- Do not commit secrets or hardcoded environment URLs — read from Vite env (`import.meta.env`).
- Avoid silent default-export refactors that break route guards or page registration.

## References
- `mini_app/frontend/README.md`
- `mini_app/frontend/tsconfig.json`
- root `AGENTS.md`
