# Swarm Skill Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the oversized tmux swarm orchestration skill into small worker-first control-plane skills so Codex spends tokens on routing and decisions, while OpenCode workers do discovery, planning, implementation, review, and artifact validation.

**Architecture:** Keep `tmux-swarm-orchestration` as a thin router. Move each workflow phase into a focused Codex skill with one responsibility and one expected artifact. Promote secretary OpenCode agents and a secretary-facing OpenCode skill so broad issue/PR/repo research happens in workers.

**Tech Stack:** Codex skills in `~/.codex/skills`, OpenCode agents/skills in repo `.opencode/` and/or `~/.config/opencode`, existing tmux launcher scripts, JSON signal artifacts.

---

## File Structure

- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md`
  - Reduce to router-only guidance and cross-skill invariants.
- Create: `/home/user/.codex/skills/swarm-intake/SKILL.md`
  - Secretary-first issue/PR/queue/artifact intake.
- Create: `/home/user/.codex/skills/swarm-plan/SKILL.md`
  - Route selection, decomposition, file reservations, worker wave planning.
- Create: `/home/user/.codex/skills/swarm-launch/SKILL.md`
  - tmux marker, registry, worktree, launcher, route-check mechanics.
- Create: `/home/user/.codex/skills/swarm-acceptance/SKILL.md`
  - DONE/FAILED/BLOCKED signal validation and accept/reject decisions.
- Create: `/home/user/.codex/skills/swarm-pr-review-flow/SKILL.md`
  - PR review -> review-fix -> fresh review -> merge-readiness loop.
- Create: `/home/user/.codex/skills/swarm-recovery/SKILL.md`
  - Broken routing, stale registry, invalid signal, stuck worker, log leak recovery.
- Create: `/home/user/.config/opencode/skills/swarm-secretary-intake/SKILL.md`
  - Worker-facing secretary contract for `SECRETARY_BRIEF`.
- Modify or create: `/home/user/projects/rag-fresh/.opencode/agents/secretary-flash.md`
- Modify or create: `/home/user/projects/rag-fresh/.opencode/agents/secretary-pro.md`
  - Make secretary agents first-class and tracked.
- Modify: `/home/user/projects/rag-fresh/.opencode/agents/pr-worker.md`
- Modify: `/home/user/projects/rag-fresh/.opencode/agents/pr-review.md`
- Modify: `/home/user/projects/rag-fresh/.opencode/agents/pr-review-fix.md`
- Modify: `/home/user/projects/rag-fresh/.opencode/agents/complex-escalation.md`
  - Add explicit local-only permissions required by launcher when `SWARM_LOCAL_ONLY=1`.

## Task 1: Create Codex Skill Skeletons

**Files:**
- Create: `/home/user/.codex/skills/swarm-intake/SKILL.md`
- Create: `/home/user/.codex/skills/swarm-plan/SKILL.md`
- Create: `/home/user/.codex/skills/swarm-launch/SKILL.md`
- Create: `/home/user/.codex/skills/swarm-acceptance/SKILL.md`
- Create: `/home/user/.codex/skills/swarm-pr-review-flow/SKILL.md`
- Create: `/home/user/.codex/skills/swarm-recovery/SKILL.md`
- Create: each skill's `agents/openai.yaml`

- [ ] **Step 1: Initialize each skill**

Run:

```bash
for skill in swarm-intake swarm-plan swarm-launch swarm-acceptance swarm-pr-review-flow swarm-recovery; do
  /home/user/.codex/skills/.system/skill-creator/scripts/init_skill.py "$skill" \
    --path "${CODEX_HOME:-$HOME/.codex}/skills"
done
```

Expected: each skill folder exists with `SKILL.md` and `agents/openai.yaml`.

- [ ] **Step 2: Write short trigger descriptions**

Each description must include the exact use case:

- `swarm-intake`: first step for issue/PR/queue/artifact intake through secretary workers.
- `swarm-plan`: use after accepted `SECRETARY_BRIEF` to classify and decompose work.
- `swarm-launch`: use when launching OpenCode workers through tmux.
- `swarm-acceptance`: use when a worker sends DONE/FAILED/BLOCKED.
- `swarm-pr-review-flow`: use for PR review, review-fix, fresh review, merge readiness.
- `swarm-recovery`: use for broken swarm state or red flags.

- [ ] **Step 3: Validate skill metadata**

Run:

```bash
for skill in swarm-intake swarm-plan swarm-launch swarm-acceptance swarm-pr-review-flow swarm-recovery; do
  /home/user/.codex/skills/.system/skill-creator/scripts/quick_validate.py "${CODEX_HOME:-$HOME/.codex}/skills/$skill"
done
```

Expected: all validations pass.

## Task 2: Move Control-Plane Rules Into Focused Skills

**Files:**
- Modify: `/home/user/.codex/skills/swarm-intake/SKILL.md`
- Modify: `/home/user/.codex/skills/swarm-plan/SKILL.md`
- Modify: `/home/user/.codex/skills/swarm-launch/SKILL.md`
- Modify: `/home/user/.codex/skills/swarm-acceptance/SKILL.md`
- Modify: `/home/user/.codex/skills/swarm-pr-review-flow/SKILL.md`
- Modify: `/home/user/.codex/skills/swarm-recovery/SKILL.md`

- [ ] **Step 1: Add the shared worker-first invariant**

Add this concise rule to every new Codex skill:

```markdown
Codex is the control plane. If this step requires broad reading, launch or use a worker artifact. Do not spend orchestrator context on raw issue archaeology, full diffs, raw logs, broad repo scans, or transcript reading unless the artifact is missing, contradictory, safety-critical, or the task is tiny.
```

- [ ] **Step 2: Define one output artifact per skill**

Use these artifact names:

- `swarm-intake` -> `SECRETARY_BRIEF`
- `swarm-plan` -> `SWARM_PLAN`
- `swarm-launch` -> `LAUNCH_RECORD`
- `swarm-acceptance` -> `ACCEPTANCE_DECISION`
- `swarm-pr-review-flow` -> `MERGE_READINESS`
- `swarm-recovery` -> `RECOVERY_REPORT`

- [ ] **Step 3: Keep each `SKILL.md` under 150 lines**

Move long details to existing `tmux-swarm-orchestration/references/*.md` only when needed. Do not duplicate long schemas in multiple skills.

## Task 3: Convert `tmux-swarm-orchestration` Into A Router

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md`

- [ ] **Step 1: Replace detailed workflow with routing table**

The router should map events to skills:

```markdown
| State/Event | Use |
| --- | --- |
| No accepted intake artifact | `swarm-intake` |
| Accepted `SECRETARY_BRIEF`, no plan | `swarm-plan` |
| Ready to launch worker | `swarm-launch` |
| Worker terminal signal | `swarm-acceptance` |
| PR review/review-fix/merge readiness | `swarm-pr-review-flow` |
| Broken routing/stale registry/invalid signal/stuck worker | `swarm-recovery` |
```

- [ ] **Step 2: Keep only global invariants**

Keep these in router:

- secretary-first unless tiny/local;
- artifacts over transcripts;
- no broad reads by orchestrator;
- active worker cap;
- no production/secrets/live writes without explicit authorization;
- workers run in dedicated worktrees;
- PR review workers are read-only.

- [ ] **Step 3: Validate**

Run:

```bash
/home/user/.codex/skills/.system/skill-creator/scripts/quick_validate.py /home/user/.codex/skills/tmux-swarm-orchestration
```

Expected: validation passes.

## Task 4: Add Worker-Facing Secretary Skill

**Files:**
- Create: `/home/user/.config/opencode/skills/swarm-secretary-intake/SKILL.md`

- [ ] **Step 1: Create the OpenCode skill**

Write a short worker-facing skill with:

- bounded reads only;
- no worker launches;
- no issue mutation;
- no product edits unless reserved;
- write `logs/SECRETARY.md`;
- write `.signals/secretary*.json`;
- optional `logs/NEXT_WORKER_PROMPT.md`;
- output `SECRETARY_BRIEF` with confidence, risks, recommended route, reserved files, focused checks, and commands.

- [ ] **Step 2: Update secretary worker prompts to require this skill**

Future secretary launches should set:

```bash
OPENCODE_REQUIRED_SKILLS=swarm-secretary-intake
```

- [ ] **Step 3: Validate launcher skill discovery**

Run from repo root:

```bash
test -f "$HOME/.config/opencode/skills/swarm-secretary-intake/SKILL.md"
```

Expected: command exits 0.

## Task 5: Make Secretary Agents First-Class

**Files:**
- Modify or create: `/home/user/projects/rag-fresh/.opencode/agents/secretary-flash.md`
- Modify or create: `/home/user/projects/rag-fresh/.opencode/agents/secretary-pro.md`

- [ ] **Step 1: Track secretary agents**

Run:

```bash
git status --short .opencode/agents/secretary-flash.md .opencode/agents/secretary-pro.md
```

Expected now: files may be untracked. Add them in the implementation commit.

- [ ] **Step 2: Enforce model split**

`secretary-flash.md` frontmatter:

```yaml
model: opencode-go/deepseek-v4-flash
```

`secretary-pro.md` frontmatter:

```yaml
model: opencode-go/deepseek-v4-pro
```

- [ ] **Step 3: Add local-only permissions**

For all default local-only agents, add frontmatter permissions compatible with launcher checks:

```yaml
permission:
  "*": allow
  skill:
    "*": allow
  webfetch: deny
  websearch: deny
  external_directory: ask
mcp:
  context7:
    enabled: false
  exa:
    enabled: false
```

## Task 6: Validate End-To-End Contracts Without Launching Real Work

**Files:**
- No source changes expected.

- [ ] **Step 1: List OpenCode agents**

Run:

```bash
opencode agent list | rg "secretary-flash|secretary-pro|pr-worker|pr-review|pr-review-fix|complex-escalation"
```

Expected: all listed agents are visible.

- [ ] **Step 2: Validate Codex skills**

Run:

```bash
for skill in tmux-swarm-orchestration swarm-intake swarm-plan swarm-launch swarm-acceptance swarm-pr-review-flow swarm-recovery; do
  /home/user/.codex/skills/.system/skill-creator/scripts/quick_validate.py "${CODEX_HOME:-$HOME/.codex}/skills/$skill"
done
```

Expected: all validations pass.

- [ ] **Step 3: Run existing swarm tests**

Run:

```bash
pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests -q
```

Expected: existing launcher/signal/prompt tests pass.

## Task 7: Commit

**Files:**
- All modified Codex skill files under `/home/user/.codex/skills`
- Repo OpenCode files under `/home/user/projects/rag-fresh/.opencode`
- Plan file: `docs/superpowers/plans/2026-05-14-swarm-skill-split.md`

- [ ] **Step 1: Review diffs**

Run:

```bash
git status --short
git diff -- .opencode docs/superpowers/plans/2026-05-14-swarm-skill-split.md
```

Expected: only intended repo files changed.

- [ ] **Step 2: Commit repo-owned files**

Run:

```bash
git add .opencode docs/superpowers/plans/2026-05-14-swarm-skill-split.md
git commit -m "chore: split swarm orchestration skill plan"
```

Expected: commit created for repo-owned files. Commit or back up `~/.codex/skills` changes separately if that tree is under its own git repository.

---

## Notes

- Keep Phase 1 small. Do not create `swarm-plan-draft`, `swarm-artifact-check`, or `swarm-runtime-verify` until repeated real use proves they are needed.
- The main success metric is lower orchestrator context use: Codex should read compact artifacts and validator output, not raw issue/PR/log/diff sources.
- Plan review loop intentionally skipped for this low-overhead planning pass.
