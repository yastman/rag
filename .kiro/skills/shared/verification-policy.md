# Shared: Verification ownership policy

> Single source of truth for who verifies what. Referenced by the swarm phase
> skills instead of being restated in each (#2305 P2).

## Ownership

- **Workers verify their own work.** No worker may send `[DONE]` without fresh
  verification evidence produced in its own session (command + exit code +
  result in the report).
- **the orchestrator (orchestrator) does mechanical control-plane checks only**: artifact
  path existence, file size, terminal-event shape, and whether required report
  fields are present. the orchestrator does not run `git` / `gh` / tests / repo-scans for
  content verification during acceptance.
- **A dedicated verification / review worker** owns content re-verification when
  the worker's self-report is missing, contradictory, or high-risk.

## Rules

- Treat a worker self-report as a lead, not proof.
- `schema-valid != accepted`: a passing mechanical/structural check is a fact,
  not an acceptance verdict.
- For code-changing reports, require `changed_files`, `tests_run`,
  `verification_evidence`, and `evidence_commands`. Missing or empty
  verification fields are `needs_fix` / `needs_review`, not accepted.
- The semantic accept / needs_fix / PR / merge decision belongs to the
  orchestrator, never to a rail script.
