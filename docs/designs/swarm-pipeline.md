# Kiro CLI Swarm Workflow Pipeline

## Главная идея

```text
Orchestrator = brain
Skills = engineering discipline
Scripts = light rails
Workers = execution
Reviewer = independent judgment
```

Оркестратор сам принимает решения:
- нужен ли intake / grill / plan
- сколько воркеров запускать
- какую модель выбрать
- какие skills использовать
- нужен ли PR review
- кто чинит blockers
- merge_ready или needs_human

Скрипты только помогают: создать worktree, запустить worker, скачать skills, проверить базовую безопасность.

---

## 0. One-time setup

```bash
./scripts/install_ready_skills.sh
./scripts/check_installed_skills.sh
./scripts/list_installed_skills.sh
```

Active skills: `grill-me`, `grill-with-docs`, `writing-plans`, `executing-plans`, `test-driven-development`, `using-git-worktrees`, `verification-before-completion`, `requesting-code-review`, `receiving-code-review`, `finishing-a-development-branch`

Reference-only (`.kiro/skills_reference/`): `using-superpowers`, `subagent-driven-development`, `dispatching-parallel-agents` — не запускают nested swarm.

---

## 1. Intake stage

**Actor:** `swarm-orchestrator`, optional `secretary-flash` (haiku)

**When:** issue длинный, много комментариев, нужно дёшево собрать brief

**Output:**
```
INTAKE BRIEF:
- Task:
- User goal:
- Constraints:
- Important files:
- Open questions:
- Risk level:
```

**Decision:** `continue_to_grill` | `continue_to_plan` | `ask_human` | `stop`

---

## 2. Grill / pressure-test stage

**Actor:** `swarm-orchestrator`, optional `secretary-pro` (sonnet)

**Use `grill-me`:** требования мутные, много assumptions, непонятно done criteria

**Use `grill-with-docs`:** задача внутри codebase с CONTEXT.md / ADR / docs, меняется API/domain/schema

**Output:**
```
GRILL SUMMARY:
- Goal:
- Non-goals:
- Assumptions:
- Risks:
- Resolved decisions:
- Open questions:
- Ready for plan: yes/no
```

---

## 3. Planning stage

**Actor:** `swarm-orchestrator`, optional `secretary-pro` (sonnet)

**Skill:** `writing-plans`

**Output:**
```
SWARM PLAN:
1. Goal
2. Non-goals
3. Files likely touched
4. Worker split (T1/T2/T3/PRR)
5. Worktrees / branches
6. Required skills per worker
7. Test / verification commands
8. Risks
9. Done criteria
```

---

## 4. Worker launch stage

**Scripts:** `launch_kiro_worker.sh`, `create_worker_worktree.sh`

**Model routing guideline** (orchestrator can override):
```
intake/summary:      claude-haiku-4.5
planning/impl:       claude-sonnet-4.6
deep PR review:      claude-opus-4.8
```

---

## 5. Worker execution stage

**Actor:** implementation worker (usually sonnet)

**Required skills:** `using-git-worktrees`, `executing-plans`, `verification-before-completion`

**Use when needed:** `test-driven-development`

**Worker flow:**
1. Confirm worktree (not main repo, correct branch)
2. Read plan fully — use `executing-plans`
3. If blocker/ambiguity: stop and report
4. Execute step by step
5. Use TDD when behavior changes
6. Run `verification-before-completion` — no [DONE] without fresh verification
7. Write worker report → send [DONE]

**TDD rule:** required for bugfix, new feature, behavior change, regression risk, auth/payment/security/data

**Worker report:**
```
WORKER REPORT:
- Task:
- What changed:
- Files changed:
- Tests / verification run:
- Exit code:
- Result:
- Risks:
- Unverified areas:
- Ready for acceptance: yes/no
```

---

## 6. Acceptance stage

**Actor:** `swarm-orchestrator`

**Checks:** scope, verification evidence, no forbidden files changed

**Forbidden files by default:** `.kiro/skills/**`, `.kiro/agents/**`, `.env`, `.env.*`, `*.pem`, `*.key`

**Decision:** `accepted` | `needs_fix` | `needs_more_tests` | `needs_human`

---

## 7. PR creation stage

**Scripts:** `create_pr.sh`

PR description: Summary, files changed, tests run, verification evidence, risks, related issue.

---

## 8. PR review stage

**Actor:** pr-review worker (opus for high-risk, sonnet for normal)

**Skill:** `requesting-code-review`

**Reviewer context:** issue summary, plan, worker report, diff, verification output, PR link

**Output:**
```
PR_REVIEW:
- Decision: merge_ready / blockers_found / needs_human
- Critical blockers:
- Important issues:
- Minor issues:
- Test / verification assessment:
- Security / architecture concerns:
- Final recommendation:
```

---

## 9. Blocker fix loop

**Trigger:** `PR_REVIEW Decision == blockers_found`

**Actor:** pr-review-fix worker (sonnet)

**Skills:** `receiving-code-review`, `verification-before-completion`, optional `test-driven-development`

**Rules:** inspect code first, verify each blocker technically, fix only valid named blockers, do not expand scope

**Fix report:**
```
FIX REPORT:
- Blockers addressed:
- Files changed:
- Tests / verification run:
- Exit code:
- Result:
- Reviewer comments disagreed with + reason:
```

After fix → back to PR review stage.

---

## 10. Final branch finish stage

**Skill:** `finishing-a-development-branch` (checklist only, must not merge automatically)

---

## 11. Merge decision stage

**Actor:** `swarm-orchestrator` only. Auto-merge disabled.

Merge allowed only if: worker accepted + verification evidence + PR review `merge_ready` + blockers resolved + no forbidden files + no unresolved risk.

---

## 12. Full pipeline diagram

```
Issue
  ↓
/swarm-orchestrator
  ↓
Intake? → INTAKE BRIEF
  ↓
Grill? → grill-me / grill-with-docs → GRILL SUMMARY
  ↓
Plan → writing-plans → SWARM PLAN
  ↓
Launch workers → tmux + git worktrees
  ↓
Worker execution
  ├─ using-git-worktrees
  ├─ executing-plans
  ├─ test-driven-development (if needed)
  └─ verification-before-completion
  ↓
Worker report + [DONE]
  ↓
Acceptance
  ↓
Create PR
  ↓
PR review → requesting-code-review
  ↓
Blockers?
  ├─ yes → fix worker (receiving-code-review + verification) → re-review
  └─ no
       ↓
Final checklist → finishing-a-development-branch
       ↓
Orchestrator merge decision
```

---

## 13. Adaptive strictness

**Tiny task** (typo, docs, comment): orchestrator → one worker → verification → optional PR review

**Normal task** (bugfix, small feature, refactor): optional grill → writing-plans → worker + TDD if behavior changes → verification → PR → review

**High-risk task** (auth, payment, security, data model, architecture): intake → grill-with-docs → writing-plans → parallel workers → TDD expected → Opus PR review → blocker fix loop → merge decision

---

## 14. Default skill map

| Actor | Skills |
|---|---|
| Orchestrator | `grill-me`, `grill-with-docs`, `writing-plans`, `requesting-code-review`, `finishing-a-development-branch` |
| Implementation worker | `using-git-worktrees`, `executing-plans`, `test-driven-development`, `verification-before-completion` |
| PR reviewer | `requesting-code-review` |
| PR fix worker | `receiving-code-review`, `test-driven-development`, `verification-before-completion` |

---

## 15. Golden rules

1. **No worker may send `[DONE]` without fresh verification evidence.**
2. **No reviewer may merge.**
3. **No skill may override orchestrator.**
4. **No script may replace orchestrator judgment.**
5. **The orchestrator remains the brain.**
