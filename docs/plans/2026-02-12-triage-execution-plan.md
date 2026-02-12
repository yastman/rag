# Triage Execution Plan — 2026-02-12

**Issue:** #175 (backlog audit v2)
**Branch:** `chore/parallel-backlog/triage-175`

## Scope

Review all 41 open issues, map to open PRs, assign priorities, close duplicates.

## Label Strategy

| Label | Color | Meaning |
|-------|-------|---------|
| `P0-critical` | `#d73a4a` | Blocking: security, CI broken, data loss |
| `P1-next` | `#e4e669` | Next sprint: has PR or actively in-progress |
| `P2-backlog` | `#0075ca` | Planned but not urgent |
| `has-pr` | `#a2eeef` | Issue has an open pull request |

## PR-to-Issue Mapping

| Issue | PR | Branch | Status |
|-------|-----|--------|--------|
| #164 | #180 | fix/164-chaos-llm-api | Open |
| #166 | #177 | fix/166-validation-retry-resilience | Open |
| #168 | #194 | fix/168-validation-thresholds | Open |
| #176 | #178 | fix/176-cache-flush-version | Open |
| #181 | #182 | fix/181-mypy-unblock | Open |
| #183 | #185 | fix/183-redisvl-gate | Open |
| #191 | #193 | fix/191-ci-green-sweep | Open |

## Priority Assignment

### P0-critical (2 issues)
- #71: security: pin uv builder images + update minio (CVE)
- #179: chore(ci): clean dirty worktree before baseline/verification steps

### P1-next (9 issues)
- #164, #166, #168, #176, #181, #183, #191 — all have PRs
- #155: fix(vectorizers) redisvl 0.14.0 migration (assigned yastman)
- #189: fix(baseline) CI isolation (possibly resolved by PR #190)

### P2-backlog (28 issues)
- CI/test fixes: #184, #186, #187, #188
- Features: #75, #74, #152, #157, #162, #147
- Eval: #126, #127
- Infra: #54, #70, #72, #73, #100, #102
- Kommo Agentic: #132, #134, #135, #136, #137, #138, #139, #140, #141, #142

### Not prioritized (meta)
- #175: this triage issue
- #130, #133: epics (tracking)
- #11: Renovate dependency dashboard

## Duplicates Closed
- #192 → duplicate of #168 (impl copy, PR #194 covers both)
- #174 → already closed as dup of #166 (prior triage)

## Execution Steps
1. ✅ Fetch all open issues and PRs
2. ✅ Create priority labels
3. ✅ Apply `has-pr` labels
4. ✅ Apply priority labels (P0/P1/P2)
5. ✅ Close #192 as duplicate
6. ✅ Add triage comment to #189
7. Write triage results report
8. Commit plan + report
