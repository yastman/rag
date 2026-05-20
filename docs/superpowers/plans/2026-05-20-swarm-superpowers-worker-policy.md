# Swarm Superpowers Worker Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make repo and tmux/OpenCode swarm rules explicit: lint/static gates may run in git hooks, tests stay as deliberate local commands, non-trivial work starts in isolated worktrees, workers use only assigned worktrees, and Superpowers skills are opt-in per worker role.

**Architecture:** Keep `AGENTS.md` as the short gateway and move durable workflow detail into canonical docs and swarm skills. Put planning decisions in `swarm-plan`, enforcement in `swarm-launch`, worker obligations in worker contract/OpenCode agent prompts, and proof/disposition checks in `swarm-acceptance`. Update launcher/validator scripts so namespaced Superpowers skills can be required without globally enabling every Superpower in workers.

**Tech Stack:** Markdown docs, Python unit tests, Bash launcher scripts, git worktrees, tmux/OpenCode swarm skills, pytest.

---

## File Map

- `AGENTS.md` - repo gateway; link to hygiene and validation docs, do not duplicate long policy.
- `.gitignore` - keep internal Superpowers trees ignored while allowing committed plan documents under `docs/superpowers/plans/*.md`.
- `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy.md` - this implementation plan.
- `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md` - manifest for changes made outside this repo under `/home/user/.codex` and `/home/user/.config/opencode`.
- `docs/LOCAL-DEVELOPMENT.md` - canonical local validation commands and hook/test separation.
- `docs/engineering/repo-hygiene-runbook.md` - canonical dirty-checkout, worktree, PR, and cleanup runbook.
- `tests/unit/test_agents_contract.py` - contract tests for `AGENTS.md` and repo hygiene docs.
- `tests/unit/test_ci_deploy_workflow.py` - contract tests for hook/test separation in docs/config.
- `/home/user/.codex/skills/swarm-plan/SKILL.md` - require worktree allocation and worker skill declarations in plans.
- `/home/user/.codex/skills/swarm-launch/SKILL.md` - enforce worktree/branch/reservation/required-skill preflight before launching workers.
- `/home/user/.codex/skills/swarm-acceptance/SKILL.md` - verify worker reports, diffs, skill usage, and final disposition.
- `/home/user/.codex/skills/swarm-worker-contract/SKILL.md` - worker finish-report schema and forbidden git operations.
- `/home/user/.codex/skills/swarm-orchestrator/SKILL.md` - clarify orchestration boundary only; no direct worktree creation for worker implementation.
- `/home/user/.config/opencode/agents/pr-worker.md` - OpenCode worker invariant: load only prompt-required skills, stay in assigned worktree.
- `/home/user/.config/opencode/agents/pr-review-fix.md` - review-fix worker invariant with same boundaries.
- `/home/user/.config/opencode/agents/pr-review.md` - reviewer invariant: read-only unless explicitly assigned.
- `/home/user/.config/opencode/skills/swarm-worker-contract/SKILL.md` - OpenCode-facing worker finish-report schema.
- `/home/user/.config/opencode/skills/swarm-pr-finish/SKILL.md` - OpenCode-facing final report fields and local verification evidence.
- `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh` - resolve and bundle namespaced Superpowers required skills.
- `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py` - validate worker prompts include/forbid correct Superpowers policy.
- `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py` - allow namespaced skills in signal/report validation if currently rejected.
- `/home/user/.codex/skills/tmux-swarm-orchestration/tests/` - add/update launcher and validator tests.

External paths under `/home/user/.codex` and `/home/user/.config/opencode` are not git repositories on this machine. Tasks that edit those paths must record an external-change manifest in this repo plan directory, or use an owning upstream repository if one is intentionally introduced later. Do not run `git add /home/user/.codex/...` or `git add /home/user/.config/opencode/...` from the repo.

## Policy Decisions

- Hooks and push gates are for lint/static guardrails only. Tests are run locally through explicit commands such as `make test-unit` or `make local-pr-ready`.
- Do not start non-trivial edits in a dirty checkout. Use `.worktrees/<branch>` for feature work or when unrelated changes exist.
- Orchestrator coordinates and routes. It may request plan/launch/acceptance/disposition, but it does not implement worker tasks itself.
- `swarm-plan` owns worker allocation: worktree, base branch, target branch, reserved files, and required role skills.
- `swarm-launch` enforces the allocation before any worker starts.
- Workers do not create worktrees, switch branches, rebase, merge, push, clean, stash, delete branches, or finish PR disposition unless explicitly assigned.
- Workers may use Superpowers only when required by the prompt or plan. Never auto-load `superpowers:using-superpowers`, `superpowers:using-git-worktrees`, or `superpowers:finishing-a-development-branch` into ordinary workers.
- Code-changing workers should normally require `superpowers:test-driven-development` and `superpowers:verification-before-completion`. Bugfix/review-fix work should add `superpowers:systematic-debugging` or `superpowers:receiving-code-review` when applicable.

---

### Task 1: Repo Gateway And Hygiene Policy

**Files:**
- Modify: `.gitignore`
- Modify: `AGENTS.md`
- Modify: `docs/LOCAL-DEVELOPMENT.md`
- Modify: `docs/engineering/repo-hygiene-runbook.md`
- Test: `tests/unit/test_agents_contract.py`
- Test: `tests/unit/test_ci_deploy_workflow.py`

- [ ] **Step 1: Write failing AGENTS contract tests**

Add tests asserting:

```python
def test_agents_declares_workspace_isolation_policy():
    text = Path("AGENTS.md").read_text()
    assert "Do not start non-trivial edits in a dirty checkout" in text
    assert "Use an isolated git worktree" in text
    assert "docs/engineering/repo-hygiene-runbook.md" in text

def test_agents_declares_hooks_static_tests_local_policy():
    text = Path("AGENTS.md").read_text()
    assert "Git hooks and push gates run lint/static guardrails only" in text
    assert "Run tests explicitly as local validation" in text
    assert "docs/LOCAL-DEVELOPMENT.md" in text

def test_gitignore_allows_superpowers_plan_documents():
    text = Path(".gitignore").read_text()
    assert "docs/superpowers/" in text
    assert "!docs/superpowers/plans/" in text
    assert "!docs/superpowers/plans/*.md" in text
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_agents_contract.py tests/unit/test_ci_deploy_workflow.py -q`
Expected: fail because the gateway/hygiene phrases are not all present.

- [ ] **Step 3: Update gateway and canonical docs**

Add a short `AGENTS.md` section named `Workspace And Swarm Hygiene`:

```markdown
Do not start non-trivial edits in a dirty checkout. Use an isolated git
worktree for feature work or when unrelated local changes exist; see
[`docs/engineering/repo-hygiene-runbook.md`](docs/engineering/repo-hygiene-runbook.md).

Git hooks and push gates run lint/static guardrails only. Run tests explicitly
as local validation; see [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md).
```

In `.gitignore`, allow tracked plan documents while keeping generated/internal Superpowers content ignored:

```gitignore
docs/superpowers/
!docs/superpowers/
docs/superpowers/*
!docs/superpowers/plans/
!docs/superpowers/plans/*.md
```

In `docs/engineering/repo-hygiene-runbook.md`, add a `Before Starting New Work` section covering:

```bash
make git-hygiene
git fetch origin
git worktree add .worktrees/<branch> -b <branch> origin/dev
```

In `docs/LOCAL-DEVELOPMENT.md`, state that hooks may run static checks and tests remain explicit local commands.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_agents_contract.py tests/unit/test_ci_deploy_workflow.py -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add .gitignore AGENTS.md docs/LOCAL-DEVELOPMENT.md docs/engineering/repo-hygiene-runbook.md tests/unit/test_agents_contract.py tests/unit/test_ci_deploy_workflow.py docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy.md
git commit -m "docs: define agent workspace hygiene policy"
```

---

### Task 2: Swarm Plan Worker Allocation And Orchestrator Boundary Contract

**Files:**
- Modify: `/home/user/.codex/skills/swarm-orchestrator/SKILL.md`
- Modify: `/home/user/.codex/skills/swarm-plan/SKILL.md`
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_plan_contract.py`

- [ ] **Step 1: Write failing test or fixture check**

Add tests that read `swarm-plan/SKILL.md` and `swarm-orchestrator/SKILL.md` separately:

```python
def test_swarm_plan_requires_worker_allocation_fields():
    text = Path("/home/user/.codex/skills/swarm-plan/SKILL.md").read_text()
    for literal in [
        "worktree",
        "base_branch",
        "target_branch",
        "reserved_files",
        "required_superpowers",
        "forbidden_superpowers",
        "superpowers:verification-before-completion",
    ]:
        assert literal in text

def test_swarm_orchestrator_is_control_plane_only():
    text = Path("/home/user/.codex/skills/swarm-orchestrator/SKILL.md").read_text()
    assert "control plane" in text
    assert "do not implement worker tasks directly" in text
    assert "reserved worker files" in text
```

- [ ] **Step 2: Run test to verify failure**

Run from `/home/user/.codex/skills/tmux-swarm-orchestration`: `pytest tests/test_swarm_plan_contract.py -q`
Expected: fail on missing allocation fields or missing orchestrator boundary text.

- [ ] **Step 3: Update `swarm-plan`**

Add a worker allocation block to the plan template:

```markdown
### Worker Allocation
- id:
- kind: implementation | review-fix | review | docs | secretary
- worktree:
- base_branch:
- target_branch:
- reserved_files:
- required_skills:
- required_superpowers:
- forbidden_superpowers:
- local_validation:
- disposition: pr | merge_done | keep_worktree | discard_with_confirmation
```

Add mapping rules:

```markdown
- Code-changing implementation: require `superpowers:test-driven-development`
  and `superpowers:verification-before-completion`.
- Bugfix or failing-test work: add `superpowers:systematic-debugging`.
- Review-fix work: add `superpowers:receiving-code-review` when handling
  reviewer feedback.
- Never require `superpowers:using-superpowers`,
  `superpowers:using-git-worktrees`, or
  `superpowers:finishing-a-development-branch` for ordinary workers.
```

In `swarm-orchestrator/SKILL.md`, make the boundary explicit:

```markdown
The orchestrator is a control plane. It routes intake, planning, launch,
acceptance, recovery, and disposition. It must not implement worker tasks
directly, edit reserved worker files, or create ad hoc worker branches outside
the plan/launch flow.
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_swarm_plan_contract.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append a section to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md` listing changed external files, verification command output, and backup paths if backups were made. Do not run `git add` on `/home/user/.codex`.

---

### Task 3: Launcher Superpowers Skill Resolution

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launch_opencode_worker.py`

- [ ] **Step 1: Write failing launcher tests**

Add tests for:

```python
def test_required_skills_accept_namespaced_superpowers():
    assert launch_with_required("superpowers:test-driven-development").returncode == 0

def test_required_superpower_is_bundled_with_safe_directory_name():
    assert ".codex/required-skills/superpowers-test-driven-development/SKILL.md" in files

def test_using_superpowers_is_rejected_for_worker_prompt():
    assert launch_with_required("superpowers:using-superpowers").returncode != 0
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_launch_opencode_worker.py -q`
Expected: fail because current validation only accepts unnamespaced slugs and does not search Superpowers plugin paths.

- [ ] **Step 3: Update launcher**

Implement:

```bash
is_valid_skill_name() {
  [[ "$1" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] && return 0
  [[ "$1" =~ ^superpowers[:/][a-z0-9]+(-[a-z0-9]+)*$ ]] && return 0
  return 1
}
```

Search these locations for Superpowers:

```bash
$HOME/.config/opencode/node_modules/superpowers/skills/<slug>/SKILL.md
$CODEX_HOME/superpowers/skills/<slug>/SKILL.md
$HOME/.codex/superpowers/skills/<slug>/SKILL.md
```

Bundle namespaced skills under a filesystem-safe directory:

```bash
bundle_name="${skill//:/-}"
bundle_name="${bundle_name//\//-}"
```

Reject forbidden worker Superpowers:

```bash
superpowers:using-superpowers
superpowers:using-git-worktrees
superpowers:finishing-a-development-branch
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_launch_opencode_worker.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append changed external files and verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Do not run `git add` on `/home/user/.codex`.

---

### Task 4: Prompt Validator Superpowers Policy

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py`
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_validate_worker_prompt.py`

- [ ] **Step 1: Write failing validator tests**

Add tests asserting:

```python
def test_code_changing_prompt_requires_superpowers_policy():
    prompt = "Role: implementation\nReserved files:\n- src/a.py\n"
    assert validate(prompt).fails_with("Required Superpowers")

def test_worker_prompt_rejects_forbidden_superpowers():
    prompt = "Required Superpowers: superpowers:using-git-worktrees"
    assert validate(prompt).fails_with("forbidden")

def test_docs_only_prompt_may_skip_tdd_with_reason():
    prompt = "Required Superpowers: none\nSkipped Superpowers: superpowers:test-driven-development - docs-only"
    assert validate(prompt).ok
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_validate_worker_prompt.py -q`
Expected: fail on missing Superpowers prompt checks.

- [ ] **Step 3: Update validator**

Require code-changing worker prompts to include:

```text
Required Superpowers:
Forbidden Superpowers:
Finish Report Must Include:
- superpowers_used
- skipped_superpowers
- evidence_commands
```

Reject forbidden worker skills from Task 3. Allow docs/read-only prompts to skip TDD only with a reason.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_validate_worker_prompt.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append changed external files and verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Do not run `git add` on `/home/user/.codex`.

---

### Task 5: Swarm Launch Enforcement

**Files:**
- Modify: `/home/user/.codex/skills/swarm-launch/SKILL.md`
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_launch_contract.py`

- [ ] **Step 1: Write failing contract test**

Assert `swarm-launch/SKILL.md` requires:

```python
[
    "git -C <worktree> status --short",
    "git -C <worktree> branch --show-current",
    "reserved_files",
    "OPENCODE_REQUIRED_SKILLS",
    "Required Superpowers",
]
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_swarm_launch_contract.py -q`
Expected: fail if launch skill does not specify these gates.

- [ ] **Step 3: Update launch skill**

Add preflight checklist:

```markdown
Before launch, verify:
- `git -C <worktree> status --short` has no unrelated dirt.
- `git -C <worktree> branch --show-current` equals `target_branch`.
- Reserved files are present in the worker prompt.
- `OPENCODE_REQUIRED_SKILLS` includes required swarm role skills and required Superpowers.
- Worker prompt names forbidden Superpowers and final report fields.
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_swarm_launch_contract.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append changed external files and verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Do not run `git add` on `/home/user/.codex`.

---

### Task 6: Worker Contract And OpenCode Finish Reports

**Files:**
- Modify: `/home/user/.codex/skills/swarm-worker-contract/SKILL.md`
- Modify: `/home/user/.config/opencode/skills/swarm-worker-contract/SKILL.md`
- Modify: `/home/user/.config/opencode/skills/swarm-pr-finish/SKILL.md`
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_worker_contract.py`

- [ ] **Step 1: Write failing contract tests**

Require both Codex and OpenCode worker contracts to mention:

```python
[
    "superpowers_used",
    "skipped_superpowers",
    "evidence_commands",
    "reserved_files",
    "changed_files",
    "head_sha",
    "Do not switch branches",
    "Do not push",
]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_worker_contract.py -q`
Expected: fail on missing report fields or forbidden git operation text.

- [ ] **Step 3: Update worker contracts**

Add finish report schema:

```markdown
## Finish Report
- status: DONE | FAILED | BLOCKED
- worker:
- task:
- worktree:
- branch:
- head_sha:
- reserved_files:
- changed_files:
- superpowers_used:
- skipped_superpowers:
- docs_impact:
- new_bugs:
- evidence_commands:
- skipped_checks:
- blockers:
- next:
```

Add forbidden operations:

```markdown
Workers must not switch branches, rebase, merge, push, stash, clean, delete
branches, create extra worktrees, or edit outside reserved files unless the
prompt explicitly expands the reservation.
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_worker_contract.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append changed external files and verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Do not run `git add` on `/home/user/.codex` or `/home/user/.config/opencode`.

---

### Task 7: Acceptance Verification And Disposition

**Files:**
- Modify: `/home/user/.codex/skills/swarm-acceptance/SKILL.md`
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_acceptance_contract.py`

- [ ] **Step 1: Write failing acceptance tests**

Assert acceptance skill requires checks for:

```python
[
    "changed_files",
    "reserved_files",
    "superpowers_used",
    "skipped_superpowers",
    "git -C <worktree> diff --name-only",
    "disposition",
    "pr",
    "merge_done",
    "keep_worktree",
    "discard_with_confirmation",
]
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_swarm_acceptance_contract.py -q`
Expected: fail while acceptance does not require all checks.

- [ ] **Step 3: Update acceptance skill**

Add acceptance gates:

```markdown
- Compare actual changed files from `git -C <worktree> diff --name-only` and
  staged files against `reserved_files`.
- Compare required Superpowers from the plan against `superpowers_used` and
  `skipped_superpowers`.
- Require evidence commands for claimed lint/test/static status.
- Choose disposition: `pr`, `merge_done`, `keep_worktree`, or
  `discard_with_confirmation`.
- Never delete or discard a dirty worktree without explicit confirmation.
```

Define disposition semantics:

```markdown
- `pr`: leave the worker worktree and branch intact, create or update the PR,
  report branch/head SHA/PR URL, and do not delete anything.
- `merge_done`: only after merge is externally verified; fetch, verify the
  merged head contains the worker head or PR merge commit, then remove the
  clean worker worktree and delete the local branch only if it is fully merged.
- `keep_worktree`: leave worktree and branch intact, record reason and next
  owner/action.
- `discard_with_confirmation`: require explicit human confirmation naming the
  exact worktree and branch; archive `git -C <worktree> diff` first; then remove
  only the confirmed worktree/branch.
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_swarm_acceptance_contract.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append changed external files and verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Do not run `git add` on `/home/user/.codex`.

---

### Task 8: OpenCode Agent Invariants

**Files:**
- Modify: `/home/user/.config/opencode/agents/pr-worker.md`
- Modify: `/home/user/.config/opencode/agents/pr-review-fix.md`
- Modify: `/home/user/.config/opencode/agents/pr-review.md`
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_opencode_agent_contract.py`

- [ ] **Step 1: Write failing agent prompt tests**

Assert each worker/review-fix agent contains:

```python
"Load only prompt-required skills"
"assigned worktree"
"Do not switch branches"
"Do not push"
```

For `pr-review.md`, assert read-only behavior unless explicit assignment exists.

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_opencode_agent_contract.py -q`
Expected: fail if agent prompts do not contain the invariants.

- [ ] **Step 3: Update agent prompts**

Add concise invariant:

```markdown
Load only prompt-required skills. Stay in the assigned worktree and branch.
Do not switch branches, create worktrees, push, merge, rebase, stash, clean, or
perform PR disposition unless the prompt explicitly assigns that operation.
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_opencode_agent_contract.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append changed external files and verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Do not run `git add` on `/home/user/.codex` or `/home/user/.config/opencode`.

---

### Task 9: Signal Validator Compatibility For Namespaced Skills

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py`
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_validate_worker_signal.py`

- [ ] **Step 1: Write failing validator test**

Add a report fixture with:

```json
{
  "superpowers_used": ["superpowers:test-driven-development", "superpowers:verification-before-completion"],
  "skipped_superpowers": []
}
```

Assert validation accepts the namespaced values.

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_validate_worker_signal.py -q`
Expected: fail if validator rejects colon-separated skill names or unknown fields.

- [ ] **Step 3: Update signal validator**

Allow namespaced Superpowers in `superpowers_used` and `skipped_superpowers` fields. Keep strict validation for status values, required evidence fields, and malformed JSON if legacy strict mode is used.

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_validate_worker_signal.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append changed external files and verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Do not run `git add` on `/home/user/.codex`.

---

### Task 10: End-To-End Dry Run Without Real Worker Launch

**Files:**
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_superpowers_dry_run.py`

- [ ] **Step 1: Write dry-run test**

Create a temporary repo/worktree fixture and simulate:

```python
plan = WorkerAllocation(
    worktree=temp_worktree,
    target_branch="feature/example",
    reserved_files=["src/example.py"],
    required_superpowers=[
        "superpowers:test-driven-development",
        "superpowers:verification-before-completion",
    ],
)
```

Assert launch prompt generation includes required skills, validation passes, and a fake DONE report with matching `changed_files` and `superpowers_used` is accepted.

- [ ] **Step 2: Run dry-run test to verify failure**

Run: `pytest tests/test_swarm_superpowers_dry_run.py -q`
Expected: fail before the launcher/validator/acceptance updates are complete.

- [ ] **Step 3: Wire minimal integration helpers**

Reuse existing launcher/validator helpers. Do not launch real tmux/OpenCode. Keep this as a pure local test around generated prompts, copied required skills, and report validation.

- [ ] **Step 4: Run full swarm orchestration test subset**

Run: `pytest tests/test_launch_opencode_worker.py tests/test_validate_worker_prompt.py tests/test_validate_worker_signal.py tests/test_swarm_superpowers_dry_run.py -q`
Expected: pass.

- [ ] **Step 5: Record external change manifest**

Append changed external files and verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Do not run `git add` on `/home/user/.codex`.

---

### Task 11: Final Review And Handoff

**Files:**
- Modify: `docs/engineering/repo-hygiene-runbook.md` if execution discovers missing cleanup details.
- Modify: `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md` if review fixes touch external skill/config files.
- Modify: relevant external skill/config files only for review fixes.

- [ ] **Step 1: Run repo verification**

Run from repo worktree:

```bash
uv run pytest tests/unit/test_agents_contract.py tests/unit/test_ci_deploy_workflow.py -q
uv run ruff check tests/unit/test_agents_contract.py tests/unit/test_ci_deploy_workflow.py
```

Expected: pass.

- [ ] **Step 2: Run swarm tooling verification**

Run from `/home/user/.codex/skills/tmux-swarm-orchestration`:

```bash
pytest tests/test_launch_opencode_worker.py tests/test_validate_worker_prompt.py tests/test_validate_worker_signal.py tests/test_swarm_plan_contract.py tests/test_swarm_launch_contract.py tests/test_worker_contract.py tests/test_swarm_acceptance_contract.py tests/test_opencode_agent_contract.py tests/test_swarm_superpowers_dry_run.py -q
```

Expected: pass.

- [ ] **Step 3: Run manual policy spot checks**

Run:

```bash
rg "superpowers:using-superpowers|superpowers:using-git-worktrees|superpowers:finishing-a-development-branch" /home/user/.codex/skills/swarm-* /home/user/.config/opencode/agents /home/user/.config/opencode/skills
rg "superpowers:test-driven-development|superpowers:verification-before-completion" /home/user/.codex/skills/swarm-* /home/user/.config/opencode/skills
```

Expected: forbidden Superpowers appear only in “do not require/use in workers” text; required Superpowers appear in plan/launch/contract policy.

- [ ] **Step 4: Request code review**

Use `superpowers:requesting-code-review` or the local `review` skill for changed repo files and changed swarm tooling files.

- [ ] **Step 5: Apply review fixes**

If review finds blockers, use `superpowers:receiving-code-review` before changing code or docs. If fixes touch `/home/user/.codex` or `/home/user/.config/opencode`, append those files and fresh verification output to `docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`. Repeat verification after fixes.

- [ ] **Step 6: Final disposition**

Use `superpowers:finishing-a-development-branch` only after verification is fresh and implementation is complete. Choose one disposition:

```text
pr
merge_done
keep_worktree
discard_with_confirmation
```

Do not delete dirty worktrees automatically.

---

## Execution Notes

- Keep repo edits in a dedicated worktree, not the dirty main checkout.
- External skill/config edits under `/home/user/.codex` and `/home/user/.config/opencode` are outside the repo; verify them separately and do not mix their commit assumptions with repo commits.
- If a test path under `/home/user/.codex/skills/tmux-swarm-orchestration/tests/` does not exist yet, create the smallest focused test file named in the task.
- Do not globally enable all Superpowers for workers. Required Superpowers must be role-specific and visible in the worker prompt.
- Treat worker reports as leads until acceptance verifies actual git diff, branch, head SHA, reserved files, and evidence commands.
