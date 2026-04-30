# OpenCode Swarm Review Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add project-local OpenCode review skills and role configuration so the tmux swarm can run Kimi PR workers, DeepSeek PR review-fix workers, and an explicit escalation path without relying on worker transcript reading.

**Architecture:** Keep methodology in OpenCode skills, role/model selection in OpenCode agents or launcher flags, and orchestration in the existing tmux swarm skill. The PR stage becomes a deterministic loop: Kimi creates PR, DeepSeek reviews and autofixes blockers, Codex/orchestrator performs scope and merge gates.

**Tech Stack:** OpenCode 1.3.17, tmux, GitHub CLI, project-local `.opencode/skills`, project-local `.opencode/agents` or launcher `--model/--agent`, existing `tmux-swarm-orchestration` scripts and docs.

---

## File Structure

- Create: `.opencode/skills/gh-pr-review/SKILL.md`
  - Project-local copy of the PR review methodology currently stored at `/home/user/.codex/skills/gh-pr-review/SKILL.md`.
  - Keeps the review rules discoverable by OpenCode workers via native skill tooling.

- Create: `.opencode/agents/pr-worker.md`
  - Kimi K2.6 role for implementation workers that create PRs.
  - Model: `opencode-go/kimi-k2.6`.

- Create: `.opencode/agents/pr-review-fix.md`
  - DeepSeek V4 Pro role for PR review plus narrow autofix.
  - Model: `opencode-go/deepseek-v4-pro`.

- Create: `.opencode/agents/complex-escalation.md`
  - Reserved role for very complex failures that should be escalated to a stronger Codex/GPT-5.5 high path.
  - If OpenCode cannot access that model directly, the agent file should document the fallback instead of pretending it can.

- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md`
  - Update hard-gate language that currently says "model is already selected in OpenCode" so it allows explicit launcher model/agent selection.
  - Add PR review-fix stage using DeepSeek before final merge gate.

- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh`
  - Add optional `OPENCODE_AGENT`, `OPENCODE_MODEL`, and `OPENCODE_VARIANT` support.
  - Preserve short file-handoff prompt and avoid passing the full prompt in argv.

- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
  - Add `pr-worker` and `pr-review-fix` role contracts.
  - Add required DONE JSON fields: `model`, `agent`, `review_decision`, and `autofix_commits` where relevant.

- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md`
  - Document exact launch examples for Kimi implementation workers and DeepSeek review-fix workers.

- Test: no production test file is required.
  - Verification is by OpenCode discovery smoke tests, launcher dry-run/shellcheck-style inspection, and one harmless prompt-file launch in a scratch worktree if needed.

## Task 1: Add Project-Local `gh-pr-review` OpenCode Skill

**Files:**
- Create: `.opencode/skills/gh-pr-review/SKILL.md`
- Source: `/home/user/.codex/skills/gh-pr-review/SKILL.md`

- [ ] **Step 1: Create the skill directory**

Run:

```bash
mkdir -p .opencode/skills/gh-pr-review
```

Expected: directory exists.

- [ ] **Step 2: Copy the existing Codex skill content**

Run:

```bash
cp /home/user/.codex/skills/gh-pr-review/SKILL.md .opencode/skills/gh-pr-review/SKILL.md
```

Expected: file exists and starts with frontmatter:

```markdown
---
name: gh-pr-review
description: Use when reviewing a pull request, deciding whether it is safe to merge, or operating the review-to-merge flow in repositories where workflow drift, local verification, SDK-first rules, or runtime/container changes matter.
---
```

- [ ] **Step 3: Verify OpenCode can load project skills**

Run:

```bash
opencode run --dir "$PWD" --model "opencode-go/deepseek-v4-pro" "Use the skill tool to list available skills. Confirm whether gh-pr-review is available. Do not edit files."
```

Expected: output mentions `gh-pr-review` or shows enough skill discovery output to confirm `.opencode/skills` is indexed. If it is not discovered, check OpenCode logs with:

```bash
opencode run --dir "$PWD" --print-logs "hello" 2>&1 | rg -i "skill|opencode|superpowers"
```

- [ ] **Step 4: Commit the skill**

```bash
git add .opencode/skills/gh-pr-review/SKILL.md
git commit -m "chore(opencode): add PR review skill"
```

## Task 2: Add OpenCode Role Agents

**Files:**
- Create: `.opencode/agents/pr-worker.md`
- Create: `.opencode/agents/pr-review-fix.md`
- Create: `.opencode/agents/complex-escalation.md`

- [ ] **Step 1: Create the agents directory**

Run:

```bash
mkdir -p .opencode/agents
```

Expected: directory exists.

- [ ] **Step 2: Create Kimi PR worker agent**

Create `.opencode/agents/pr-worker.md`:

```markdown
---
description: Bounded implementation worker that writes code, tests, commits, pushes, opens a PR, and writes DONE JSON.
mode: primary
model: opencode-go/kimi-k2.6
tools:
  bash: true
  read: true
  write: true
  edit: true
  list: true
  glob: true
  grep: true
  webfetch: true
permission:
  edit: allow
  bash: allow
  webfetch: allow
  external_directory: ask
  doom_loop: ask
---

You are a PR implementation worker. Work only in the assigned git worktree and reserved files.

Use the worker prompt as the source of truth. Create focused tests, implement the smallest correct change, run the requested verification ladder, commit, push, open a PR, and write the required DONE JSON atomically.

Do not read long orchestrator logs. Do not inspect unrelated worktrees. Do not change models. Do not merge.
```

- [ ] **Step 3: Create DeepSeek PR review-fix agent**

Create `.opencode/agents/pr-review-fix.md`:

```markdown
---
description: PR review and narrow autofix worker for bringing an existing PR to merge-ready state.
mode: primary
model: opencode-go/deepseek-v4-pro
tools:
  bash: true
  read: true
  write: true
  edit: true
  list: true
  glob: true
  grep: true
  webfetch: true
permission:
  edit: allow
  bash: allow
  webfetch: allow
  external_directory: ask
  doom_loop: ask
---

You are a PR review-fix worker. Use the gh-pr-review skill before judging the patch.

Review the PR with a bug-finding mindset. If blockers are present and the prompt explicitly allows autofix, make only narrow fixes tied to findings, rerun the failing or relevant checks, commit, push to the same PR branch, and write DONE JSON.

Do not broaden the PR. Do not merge. Do not rewrite unrelated code.
```

- [ ] **Step 4: Create complex escalation agent**

Create `.opencode/agents/complex-escalation.md`:

```markdown
---
description: Escalation role for complex design, repeated review-fix failure, runtime/infra risk, or unclear merge decisions.
mode: primary
model: opencode-go/deepseek-v4-pro
tools:
  bash: true
  read: true
  write: true
  edit: true
  list: true
  glob: true
  grep: true
  webfetch: true
permission:
  edit: ask
  bash: ask
  webfetch: allow
  external_directory: ask
  doom_loop: ask
---

You are the escalation analyst. Prefer diagnosis, plan correction, and precise findings over broad rewrites.

If a GPT-5.5 high Codex route is available outside OpenCode, document the escalation recommendation instead of pretending this OpenCode agent is that route.
```

- [ ] **Step 5: Verify agents are discoverable**

Run:

```bash
opencode agent list | rg "pr-worker|pr-review-fix|complex-escalation"
```

Expected: all three names appear. If not, check whether this OpenCode build expects agents under another project-local path and adjust before continuing.

- [ ] **Step 6: Commit the agents**

```bash
git add .opencode/agents/pr-worker.md .opencode/agents/pr-review-fix.md .opencode/agents/complex-escalation.md
git commit -m "chore(opencode): add swarm role agents"
```

## Task 3: Make tmux Launcher Agent-Aware

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh`
- Test: local dry-run command inspection or controlled scratch launch

- [ ] **Step 1: Inspect current launcher**

Run:

```bash
sed -n '1,240p' /home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh
```

Expected: identify the exact `opencode` invocation and confirm it uses a short prompt-file handoff.

- [ ] **Step 2: Add optional model/agent arguments**

Modify the launcher so it accepts environment variables:

```bash
OPENCODE_AGENT="${OPENCODE_AGENT:-}"
OPENCODE_MODEL="${OPENCODE_MODEL:-}"
OPENCODE_VARIANT="${OPENCODE_VARIANT:-}"
```

Build argv safely as an array:

```bash
opencode_args=("$WT_PATH")
if [[ -n "$OPENCODE_AGENT" ]]; then
  opencode_args+=(--agent "$OPENCODE_AGENT")
fi
if [[ -n "$OPENCODE_MODEL" ]]; then
  opencode_args+=(--model "$OPENCODE_MODEL")
fi
if [[ -n "$OPENCODE_VARIANT" ]]; then
  opencode_args+=(--variant "$OPENCODE_VARIANT")
fi
opencode_args+=(--prompt "Read and execute $PROMPT_FILE. Write DONE JSON when finished.")
```

Expected: the full worker prompt is still never passed in argv.

- [ ] **Step 3: Add launch metadata**

Add compact logging before spawning:

```bash
echo "agent=${OPENCODE_AGENT:-default} model=${OPENCODE_MODEL:-default} variant=${OPENCODE_VARIANT:-default} prompt_sha256=$(sha256sum "$PROMPT_FILE" | awk '{print $1}')"
```

Expected: launch metadata is short and does not include prompt contents.

- [ ] **Step 4: Run shell syntax check**

Run:

```bash
bash -n /home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh
```

Expected: exit 0.

- [ ] **Step 5: Commit launcher update**

```bash
git add /home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh
git commit -m "chore(swarm): allow explicit OpenCode worker roles"
```

## Task 4: Update tmux Swarm Skill Contract

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md`

- [ ] **Step 1: Update the hard gate**

Change the rule:

```text
Модель worker'а НЕ указывать в prompt/command: она уже выбрана в OpenCode.
```

To:

```text
Модель worker'а НЕ указывать natural-language текстом внутри prompt. Выбор модели/agent делает orchestrator явно через launcher: OPENCODE_AGENT/OPENCODE_MODEL или OpenCode agent config.
```

Expected: the skill no longer forbids deterministic launcher model selection.

- [ ] **Step 2: Add role routing table**

Add this routing table near the existing pipeline table:

```markdown
| Stage | OpenCode agent | Model | Responsibility |
|-------|----------------|-------|----------------|
| PR implementation | `pr-worker` | `opencode-go/kimi-k2.6` | Code, tests, commit, push, PR, DONE JSON |
| PR review-fix | `pr-review-fix` | `opencode-go/deepseek-v4-pro` | Use `gh-pr-review`, find blockers, autofix only allowed blockers, push same PR |
| Escalation | `complex-escalation` or Codex GPT-5.5 high | strongest available | Complex design, repeated failures, runtime/security/infra risk |
```

- [ ] **Step 3: Add PR review-fix loop**

Add this rule to Review-Fix Loop:

```markdown
Default review-fix executor is OpenCode agent `pr-review-fix` on `opencode-go/deepseek-v4-pro`.
It must load `gh-pr-review`, review against the true PR merge base, and either:
- write `review_decision="clean"` with verification evidence, or
- commit narrow fixes to the same PR branch and write `review_decision="fixed"`.
Merge remains orchestrator-owned.
```

- [ ] **Step 4: Extend DONE JSON schema**

Add fields:

```json
{
  "agent": "pr-worker|pr-review-fix|complex-escalation",
  "model": "opencode-go/kimi-k2.6",
  "review_decision": "not_reviewed|clean|blockers|fixed|escalate",
  "autofix_commits": []
}
```

Expected: orchestrator can detect model/agent drift and PR review outcome without reading logs.

- [ ] **Step 5: Add exact launch examples**

Add implementation worker example:

```bash
OPENCODE_AGENT=pr-worker \
OPENCODE_MODEL=opencode-go/kimi-k2.6 \
/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh \
  "W-${ISSUE}-impl" "$WT_PATH" "$PROMPT_FILE"
```

Add review-fix worker example:

```bash
OPENCODE_AGENT=pr-review-fix \
OPENCODE_MODEL=opencode-go/deepseek-v4-pro \
/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh \
  "W-${ISSUE}-review-fix" "$WT_PATH" "$PROMPT_FILE"
```

- [ ] **Step 6: Commit contract docs**

```bash
git add /home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md /home/user/.codex/skills/tmux-swarm-orchestration/worker-contract.md /home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md
git commit -m "docs(swarm): define OpenCode PR review roles"
```

## Task 5: Add Smoke Verification for the New Flow

**Files:**
- Create: `.codex/prompts/smoke-opencode-pr-review.md` during test only
- No committed production code changes

- [ ] **Step 1: Create a scratch worktree**

Run:

```bash
git worktree add ../rag-fresh-wt-opencode-smoke -b chore/opencode-smoke
```

Expected: worktree created.

- [ ] **Step 2: Create a tiny prompt file**

Run:

```bash
mkdir -p ../rag-fresh-wt-opencode-smoke/.codex/prompts
cat > ../rag-fresh-wt-opencode-smoke/.codex/prompts/smoke-opencode-pr-review.md <<'EOF'
# Smoke Test

Do not edit files. Use the skill tool to check whether gh-pr-review is available. Print the selected agent/model if available, then stop.
EOF
```

Expected: prompt file exists.

- [ ] **Step 3: Run a non-mutating OpenCode smoke test**

Run:

```bash
opencode run \
  --dir "../rag-fresh-wt-opencode-smoke" \
  --agent "pr-review-fix" \
  --model "opencode-go/deepseek-v4-pro" \
  --file "../rag-fresh-wt-opencode-smoke/.codex/prompts/smoke-opencode-pr-review.md" \
  --title "smoke-pr-review-fix" \
  "Execute the attached smoke prompt. Do not edit files."
```

Expected:
- OpenCode accepts `--agent pr-review-fix`.
- It can see the prompt file.
- It reports whether `gh-pr-review` is available.
- No repo files are modified.

- [ ] **Step 4: Clean scratch worktree**

Run:

```bash
git worktree remove ../rag-fresh-wt-opencode-smoke
git branch -D chore/opencode-smoke
```

Expected: scratch worktree and branch removed.

## Task 6: End-to-End Dry Run on a Real PR Without Merge

**Files:**
- No production files expected.
- Uses an existing open PR as input.

- [ ] **Step 1: Pick a low-risk open PR**

Run:

```bash
gh pr list --state open --limit 10 --json number,title,baseRefName,headRefName,changedFiles,url
```

Expected: select one PR that is not runtime/infra-critical for the first dry run.

- [ ] **Step 2: Create review prompt file**

Create a prompt in the PR worktree:

```markdown
# PR Review-Fix Dry Run

Use the gh-pr-review skill.

PR: <number>
Mode: read-only dry run.
Autofix: disabled.

Tasks:
1. Gather PR metadata.
2. Review changed files against repository rules.
3. Do not edit files.
4. Write DONE JSON with review_decision clean/blockers/escalate.
```

- [ ] **Step 3: Launch DeepSeek review-fix in dry-run mode**

Run via launcher:

```bash
OPENCODE_AGENT=pr-review-fix \
OPENCODE_MODEL=opencode-go/deepseek-v4-pro \
/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh \
  "W-pr-review-dry-run" "$WT_PATH" "$PROMPT_FILE"
```

Expected: worker writes DONE JSON and does not mutate files.

- [ ] **Step 4: Orchestrator validates artifacts**

Run:

```bash
python3 -m json.tool "$WT_PATH/.signals/worker-pr-review-dry-run.json"
git -C "$WT_PATH" status --short
```

Expected:
- JSON valid.
- `review_decision` is present.
- worktree is clean for dry-run mode.

## Task 7: Update Context Budget Notes

**Files:**
- Modify: `docs/engineering/swarm-context-budget.md`

- [ ] **Step 1: Add a short role/model policy section**

Append a concise section:

```markdown
## OpenCode Role Policy

- Implementation workers use `pr-worker` on `opencode-go/kimi-k2.6`.
- PR review-fix workers use `pr-review-fix` on `opencode-go/deepseek-v4-pro`.
- Model selection belongs in launcher flags or OpenCode agent config, not natural-language prompt text.
- DONE JSON records `agent`, `model`, `review_decision`, and `autofix_commits`.
- Merge remains orchestrator-owned after scope gate, verification, and review gate.
```

- [ ] **Step 2: Commit documentation**

```bash
git add docs/engineering/swarm-context-budget.md
git commit -m "docs(swarm): document OpenCode role policy"
```

## Task 8: Final Verification

**Files:**
- All files from previous tasks.

- [ ] **Step 1: Check file list**

Run:

```bash
git status --short
git diff --name-only HEAD~5..HEAD
```

Expected: only `.opencode/**`, tmux swarm skill files, and docs changed.

- [ ] **Step 2: Verify OpenCode commands still expose required flags**

Run:

```bash
opencode run --help | rg -- '--model|--agent|--file|--dir|--variant'
opencode agent create --help | rg -- '--model|--path|--mode|--tools'
```

Expected: all flags are present.

- [ ] **Step 3: Verify launcher syntax**

Run:

```bash
bash -n /home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_tui_worker.sh
```

Expected: exit 0.

- [ ] **Step 4: Run repo-neutral checks**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 5: Record skipped checks**

Do not run `make check` or `make test-unit` for this plan-only/config-only change unless implementation touches repo runtime code. If those checks are skipped, final report must say they were not relevant to this configuration plan.

## Rollback Plan

- Remove `.opencode/skills/gh-pr-review`.
- Remove `.opencode/agents/pr-worker.md`, `.opencode/agents/pr-review-fix.md`, and `.opencode/agents/complex-escalation.md`.
- Revert the tmux launcher changes to ignore `OPENCODE_AGENT`, `OPENCODE_MODEL`, and `OPENCODE_VARIANT`.
- Revert the tmux swarm docs/contract changes.
- Existing OpenCode default `build` agent remains untouched.
