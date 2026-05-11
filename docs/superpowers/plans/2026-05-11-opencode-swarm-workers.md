# OpenCode Swarm Workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the tmux swarm worker execution path from Codex `321` workers to OpenCode workers while keeping Codex as the orchestrator.

**Architecture:** Codex remains the control-plane orchestrator and continues to own work selection, decomposition, worktrees, prompt authoring, registry validation, review, verification, merge decisions, and cleanup decisions. OpenCode becomes the only active worker runner through a new tmux launcher, OpenCode agents, OpenCode skills, OpenCode model/variant metadata, and a strict skill availability gate before worker launch.

**Tech Stack:** Bash, tmux, OpenCode CLI `1.3.17`, Markdown OpenCode agents and skills, Python/pytest contract tests, existing Codex skill files under `/home/user/.codex/skills/tmux-swarm-orchestration`, project OpenCode files under `/home/user/projects/rag-fresh/.opencode`.

---

## Scope Check

This plan covers one cohesive subsystem: the swarm worker runtime contract. It touches the operator skill docs/tests/launcher plus the project-local OpenCode agent files needed for those workers to actually run.

Important ownership note:

- `/home/user/.codex/skills/tmux-swarm-orchestration` is not a git repository. Do not invent git commits there; verify with tests and keep a local backup if needed.
- `/home/user/projects/rag-fresh/.opencode` and this plan file are in the `rag-fresh` repository. Commit only those repo-owned files when changed.
- Run implementation in a dedicated git worktree for repo-owned changes. Keep the main dirty worktree untouched.

## File Structure

### Operator Skill Files

- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md`
  - Replace active Codex `321` worker language with Codex-orchestrator/OpenCode-worker language.
  - Keep role boundaries, event-driven wait, worker capacity, issue/PR flow, and review-fix separation.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md`
  - Replace active launch, registry, local-only, model routing, and launch metadata examples with OpenCode equivalents.
  - Keep tmux pane validation, prompt file handoff, wake-up, timeout, and cleanup mechanics.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
  - Add OpenCode load map, required OpenCode skills gate, and OpenCode DONE fields.
  - Keep strict JSON/wake-up rules.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/worker-prompt.md`
  - Replace Codex skill workflow and model block with OpenCode skills and model/variant blocks.
  - Keep docs lookup, SDK, verification, and bug reporting policy.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`
  - Add `runner`, `variant`, `required_skills`, and `skills_loaded`.
  - Replace `reasoning_effort` with `variant` for OpenCode workers.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/worker-types.md`
  - Map worker types to OpenCode agents and required skills.
  - Remove Codex/Spark routing as the active path.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/review-verification.md`
  - Update review acceptance checks from model/reasoning to agent/model/variant/skills.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/red-flags.md`
  - Replace Codex-specific worker drift warnings with OpenCode-specific drift warnings.
- Create: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`
  - Dedicated visible tmux launcher for OpenCode workers.
  - Validates tmux orchestrator pane, worktree, prompt file, OpenCode binary, selected agent, required skills, and prompt placeholder replacement.
  - Writes launch and exit metadata.
- Keep initially: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_codex321_worker.sh`
  - Leave as legacy during migration unless tests require removal. Do not use it in active docs/examples.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`
  - Test the OpenCode launcher and registry contract.
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
  - Replace anti-OpenCode assertions with anti-active-Codex-worker assertions.
  - Add required OpenCode skills and DONE JSON contract assertions.

### Project OpenCode Files

- Create: `/home/user/projects/rag-fresh/.opencode/agents/pr-review.md`
  - Project-local read-only PR review agent so swarm does not depend on global user config.
- Modify: `/home/user/projects/rag-fresh/.opencode/agents/pr-worker.md`
  - Ensure `skill` permission allows required worker skills.
  - Deny or restrict web tools when local-only worker prompts require it.
- Modify: `/home/user/projects/rag-fresh/.opencode/agents/pr-review-fix.md`
  - Ensure `skill` permission allows `gh-pr-review`, `swarm-review-fix`, `project-docs-maintenance`, `swarm-bug-reporting`, and `swarm-pr-finish`.
- Keep: `/home/user/projects/rag-fresh/.opencode/skills/gh-pr-review/SKILL.md`
  - Already project-local.
- Keep or mirror later: global OpenCode skills under `/home/user/.config/opencode/skills/*`
  - `project-docs-maintenance`
  - `swarm-bug-reporting`
  - `swarm-pr-finish`
  - `swarm-review-fix`
  - The launcher may validate global paths, but a future hardening task can mirror them project-local.

## Task 1: Add Failing Launcher Contract Tests

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`
- Test command: `python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py -q`

- [ ] **Step 1: Add tests for the new OpenCode launcher path**

Replace the launcher path under test and add assertions for OpenCode metadata:

```python
def test_opencode_launcher_exists_and_uses_opencode_run() -> None:
    launcher = _read("scripts/launch_opencode_worker.sh")

    assert "opencode run" in launcher
    assert "--agent" in launcher
    assert "--model" in launcher
    assert "--variant" in launcher
    assert "--dir" in launcher
    assert "prompt_file_link" in launcher
    assert "tmux new-window" in launcher
    assert "321" not in launcher
```

- [ ] **Step 2: Add tests for explicit orchestrator pane behavior**

```python
def test_opencode_launcher_requires_explicit_orchestrator_pane_without_fallback() -> None:
    launcher = _read("scripts/launch_opencode_worker.sh")

    assert "ORCH_PANE/SWARM_ORCH_PANE must be set explicitly" in launcher
    assert "refusing to infer from current pane" in launcher
    assert "current tmux pane could not be resolved" not in launcher
```

- [ ] **Step 3: Add tests for required agent and skill validation**

```python
def test_opencode_launcher_validates_agent_and_required_skills() -> None:
    launcher = _read("scripts/launch_opencode_worker.sh")

    assert "OPENCODE_AGENT" in launcher
    assert "OPENCODE_REQUIRED_SKILLS" in launcher
    assert "find_skill_file" in launcher
    assert "find_agent_file" in launcher
    assert "ERROR: OpenCode agent not found" in launcher
    assert "ERROR: required OpenCode skill not found" in launcher
    assert "required_skills" in launcher
    assert "skills_available" in launcher
```

- [ ] **Step 4: Add tests for registry docs**

```python
def test_docs_use_opencode_registry_metadata() -> None:
    infrastructure = _read("infrastructure.md")
    skill = _read("SKILL.md")

    assert '"runner":"opencode"' in infrastructure
    assert '"variant":' in infrastructure
    assert '"required_skills":' in infrastructure
    assert '"skills_loaded":' in infrastructure
    assert "Codex remains the orchestrator" in skill
```

- [ ] **Step 5: Run the launcher contract test and verify failure**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py -q
```

Expected: FAIL because `scripts/launch_opencode_worker.sh` does not exist and docs still use `codex-321`.

## Task 2: Add Failing Skill Documentation Contract Tests

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
- Test command: `python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py -q`

- [ ] **Step 1: Replace the legacy anti-OpenCode tuple**

Remove:

```python
_OPEN = "open"
_CODE = "code"
FORBIDDEN_LEGACY_TERMS = (...)
```

Add a narrower helper that checks active docs do not point workers at Codex `321`:

```python
ACTIVE_DOC_PATHS = (
    "SKILL.md",
    "infrastructure.md",
    "worker-contract.md",
    "references/worker-prompt.md",
    "references/signal-schema.md",
    "references/worker-types.md",
)
```

- [ ] **Step 2: Add OpenCode worker skills contract assertions**

```python
def test_worker_prompts_require_opencode_skills() -> None:
    contract = _contract_bundle()
    skill = _read("SKILL.md")

    assert "REQUIRED OPENCODE SKILLS" in contract
    assert "project-docs-maintenance" in contract
    assert "swarm-bug-reporting" in contract
    assert "swarm-pr-finish" in contract
    assert "gh-pr-review" in contract
    assert "swarm-review-fix" in contract
    assert "skills_loaded" in contract
    assert "required_skills" in contract
    assert "Skill Availability Gate" in skill
```

- [ ] **Step 3: Add OpenCode model/variant contract assertions**

```python
def test_worker_model_block_uses_opencode_agent_model_variant() -> None:
    contract = _contract_bundle()

    assert "Runner: opencode" in contract
    assert "OpenCode agent:" in contract
    assert "OpenCode model:" in contract
    assert "OpenCode variant:" in contract
    assert "reasoning_effort" not in _read("references/worker-prompt.md")
```

- [ ] **Step 4: Add anti-active-Codex-worker assertions**

```python
def test_active_docs_do_not_route_workers_to_codex_321() -> None:
    for path in ACTIVE_DOC_PATHS:
        text = _read(path)
        assert "Default visible Codex `321` launch" not in text, path
        assert "Launch visible Codex workers" not in text, path
        assert "Runner: codex-321" not in text, path
        assert "CODEX_MODEL=" not in text, path
        assert "CODEX_REASONING_EFFORT" not in text, path
```

Allow historical references only in a clearly named legacy note if implementation keeps the old script during migration.

- [ ] **Step 5: Run the docs contract test and verify failure**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py -q
```

Expected: FAIL because active docs still describe Codex `321` workers and do not require OpenCode skills.

## Task 3: Implement the OpenCode tmux Launcher

**Files:**
- Create: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`

- [ ] **Step 1: Start from the existing launcher shape**

Create `launch_opencode_worker.sh` with the same structure as `launch_codex321_worker.sh`: usage, argument validation, tmux checks, prompt copy, placeholder replacement, runner file, inner runner, launch metadata, and printed summary.

- [ ] **Step 2: Add OpenCode environment variables**

Use these defaults:

```bash
opencode_agent="${OPENCODE_AGENT:-pr-worker}"
opencode_model="${OPENCODE_MODEL:-opencode-go/kimi-k2.6}"
opencode_variant="${OPENCODE_VARIANT:-}"
opencode_required_skills="${OPENCODE_REQUIRED_SKILLS:-}"
swarm_local_only="${SWARM_LOCAL_ONLY:-0}"
```

- [ ] **Step 3: Add `find_agent_file`**

```bash
find_agent_file() {
  local agent="$1"
  local candidate
  for candidate in \
    "$wt_path/.opencode/agents/${agent}.md" \
    "${HOME}/.config/opencode/agents/${agent}.md"
  do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}
```

- [ ] **Step 4: Add `find_skill_file`**

```bash
find_skill_file() {
  local skill="$1"
  local candidate
  for candidate in \
    "$wt_path/.opencode/skills/${skill}/SKILL.md" \
    "${HOME}/.config/opencode/skills/${skill}/SKILL.md" \
    "$wt_path/.agents/skills/${skill}/SKILL.md" \
    "${HOME}/.agents/skills/${skill}/SKILL.md" \
    "$wt_path/.claude/skills/${skill}/SKILL.md" \
    "${HOME}/.claude/skills/${skill}/SKILL.md"
  do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}
```

- [ ] **Step 5: Add OpenCode binary validation**

```bash
if ! command -v opencode >/dev/null 2>&1; then
  echo "ERROR: opencode command not found in PATH." >&2
  exit 2
fi
```

- [ ] **Step 6: Validate selected agent**

```bash
agent_file="$(find_agent_file "$opencode_agent" || true)"
if [[ -z "$agent_file" ]]; then
  echo "ERROR: OpenCode agent not found: $opencode_agent" >&2
  exit 2
fi
```

- [ ] **Step 7: Validate required skills and build JSON arrays**

Use a simple comma-separated env var for launch:

```bash
required_skills_json="[]"
skills_available_json="[]"
if [[ -n "$opencode_required_skills" ]]; then
  IFS=',' read -r -a required_skills <<< "$opencode_required_skills"
  for required_skill in "${required_skills[@]}"; do
    required_skill="${required_skill#"${required_skill%%[![:space:]]*}"}"
    required_skill="${required_skill%"${required_skill##*[![:space:]]}"}"
    if [[ ! "$required_skill" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
      echo "ERROR: invalid OpenCode skill name: $required_skill" >&2
      exit 2
    fi
    skill_file="$(find_skill_file "$required_skill" || true)"
    if [[ -z "$skill_file" ]]; then
      echo "ERROR: required OpenCode skill not found: $required_skill" >&2
      exit 2
    fi
    skill_paths+=("${required_skill}=${skill_file}")
  done
fi
```

Then use Python `json.dumps` to serialize `required_skills` and `skill_paths` into launch/exit metadata instead of hand-built JSON.

- [ ] **Step 8: Build the inner runner around `opencode run`**

```bash
if [[ -n "${OPENCODE_VARIANT:-}" ]]; then
  exec opencode run \
    --agent "$OPENCODE_AGENT" \
    --model "$OPENCODE_MODEL" \
    --variant "$OPENCODE_VARIANT" \
    --dir "$WT_PATH" \
    "$PROMPT_LINK"
else
  exec opencode run \
    --agent "$OPENCODE_AGENT" \
    --model "$OPENCODE_MODEL" \
    --dir "$WT_PATH" \
    "$PROMPT_LINK"
fi
```

Keep this in the generated inner runner so the tmux window remains a normal shell surface.

- [ ] **Step 9: Write launch metadata with OpenCode fields**

Launch JSON must include:

```json
{
  "runner": "opencode",
  "agent": "pr-worker",
  "model": "opencode-go/kimi-k2.6",
  "variant": "",
  "required_skills": ["project-docs-maintenance", "swarm-bug-reporting", "swarm-pr-finish"],
  "skills_available": true,
  "skill_paths": ["project-docs-maintenance=/path/SKILL.md"],
  "swarm_local_only": "1"
}
```

- [ ] **Step 10: Run the launcher contract tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py -q
```

Expected: launcher tests pass or fail only on docs not updated yet.

## Task 4: Harden Project OpenCode Agents For Required Skills

**Files:**
- Create: `/home/user/projects/rag-fresh/.opencode/agents/pr-review.md`
- Modify: `/home/user/projects/rag-fresh/.opencode/agents/pr-worker.md`
- Modify: `/home/user/projects/rag-fresh/.opencode/agents/pr-review-fix.md`
- Test command: `opencode agent list`

- [ ] **Step 1: Add project-local `pr-review.md`**

Create `/home/user/projects/rag-fresh/.opencode/agents/pr-review.md`:

```markdown
---
description: Read-only PR review agent for tmux swarm OpenCode workers.
mode: primary
model: opencode-go/deepseek-v4-pro
permission:
  read: allow
  bash: allow
  edit: deny
  webfetch: ask
  websearch: deny
  external_directory: ask
  doom_loop: ask
  skill:
    "*": allow
---

You are a read-only PR review worker in a Codex-orchestrated tmux swarm.

Use the worker prompt as the source of truth. Load required OpenCode skills in
the exact order listed in the prompt. Review against the true merge base, issue
intent, repository contracts, tests, SDK-native fit, and runtime risk.

Do not edit files, commit, push, merge, delete branches, remove worktrees, or
spawn subagents. Persist results only through the requested signal JSON and
short worker-local logs.
```

- [ ] **Step 2: Add `skill` permission to `pr-worker.md`**

Ensure frontmatter contains:

```yaml
permission:
  edit: allow
  bash: allow
  webfetch: ask
  websearch: deny
  external_directory: ask
  doom_loop: ask
  skill:
    "*": allow
```

- [ ] **Step 3: Add `skill` permission to `pr-review-fix.md`**

Ensure frontmatter contains:

```yaml
permission:
  edit: allow
  bash: allow
  webfetch: ask
  websearch: deny
  external_directory: ask
  doom_loop: ask
  skill:
    "*": allow
```

- [ ] **Step 4: Add explicit prose to both mutable agents**

Add:

```markdown
Load the required OpenCode skills from the worker prompt before substantive
work. If any required skill is unavailable, write blocked DONE JSON and wake the
orchestrator.
```

- [ ] **Step 5: Verify OpenCode sees the agents**

Run:

```bash
opencode agent list | rg -n "pr-worker|pr-review|pr-review-fix"
```

Expected: all three agents are listed.

- [ ] **Step 6: Commit repo-owned OpenCode agent changes**

Run from `/home/user/projects/rag-fresh`:

```bash
git add .opencode/agents/pr-worker.md .opencode/agents/pr-review.md .opencode/agents/pr-review-fix.md
git commit -m "chore: configure opencode swarm agents"
```

If the implementation is happening in a dedicated worktree, commit there.

## Task 5: Update Core Skill Documentation To OpenCode Workers

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`

- [ ] **Step 1: Update `SKILL.md` title and opening**

Change:

```markdown
# tmux Swarm Orchestration

Coordinate Codex `321` workers in visible tmux windows.
```

To:

```markdown
# tmux Swarm Orchestration

Coordinate OpenCode workers in visible tmux windows. Codex is the orchestrator:
select work, decompose it, launch isolated OpenCode workers, review artifacts,
verify locally, and report PR status.
```

- [ ] **Step 2: Replace active runner/model hard gates**

Replace the active Codex runner/model bullets with OpenCode rules:

```markdown
- Choose worker runner/model/variant only through launcher env/config, not prompt prose. Runner is OpenCode via `scripts/launch_opencode_worker.sh`; use `OPENCODE_AGENT`, `OPENCODE_MODEL`, `OPENCODE_VARIANT`, and `OPENCODE_REQUIRED_SKILLS`.
- OpenCode skill availability is a launch gate. Do not launch a worker until the selected OpenCode agent exists and every required skill resolves in OpenCode discovery paths.
- Prompt prose must include `REQUIRED OPENCODE SKILLS`; launch metadata must include `required_skills`, `skills_available:true`, and `skill_paths`.
```

- [ ] **Step 3: Replace launch command in `SKILL.md`**

Use:

```bash
ORCH_PANE="$ORCH_PANE" \
OPENCODE_AGENT=pr-worker \
OPENCODE_MODEL=opencode-go/kimi-k2.6 \
OPENCODE_VARIANT= \
OPENCODE_REQUIRED_SKILLS=project-docs-maintenance,swarm-bug-reporting,swarm-pr-finish \
SWARM_LOCAL_ONLY=1 \
/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  "W-{NAME}" "$WT_PATH" "$PROMPT_FILE"
```

- [ ] **Step 4: Update `infrastructure.md` registry example**

Replace `runner:"codex-321"` example with:

```json
{"worker":"W-123","runner":"opencode","worktree":"/abs/wt","branch":"fix/x","base":"dev","signal_file":"/abs/wt/.signals/worker-123.json","prompt_sha256":"...","agent":"pr-worker","model":"opencode-go/kimi-k2.6","variant":"","required_skills":["project-docs-maintenance","swarm-bug-reporting","swarm-pr-finish"],"skills_available":true,"reserved_files":["src/x.py"],"started_at":"ISO-8601","status":"active"}
```

- [ ] **Step 5: Update `infrastructure.md` launch section**

Replace `Default visible Codex 321 launch` with `Default visible OpenCode launch` and include the launch command from Step 3.

- [ ] **Step 6: Update `infrastructure.md` metadata text**

Replace:

```text
records `.signals/launch-*.json` including `orchestrator_pane`, `runner`, `agent`, `model`, `reasoning_effort`, and `prompt_delivery`
```

With:

```text
records `.signals/launch-*.json` including `orchestrator_pane`, `runner`, `agent`, `model`, `variant`, `required_skills`, `skills_available`, `skill_paths`, and `prompt_delivery`
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py -q
```

Expected: remaining failures point to worker contract/reference files not yet updated.

## Task 6: Update Worker Contract And Prompt References

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/worker-prompt.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`

- [ ] **Step 1: Update `worker-contract.md` quick path wording**

Replace Codex-specific quick worker sentence with:

```markdown
Quick path reduces prompt size and review overhead; it does not mean "use the weakest model." Use the OpenCode model selected by the orchestrator for the worker type. Prompt and launch metadata must still agree on `agent`, `model`, `variant`, and required skills.
```

- [ ] **Step 2: Add required skills to `WORKER PROMPT PAYLOAD`**

Change the payload fields to include:

```text
OpenCode runner: runner=opencode, agent, model, variant, and routing reason.
Required OpenCode skills: exact ordered skill names and what to do if one is unavailable.
Skill availability gate: launch metadata path and required `skills_loaded` DONE JSON evidence.
```

- [ ] **Step 3: Update `Step 0 Policy Gate` for OpenCode**

Keep the local-only semantics but describe OpenCode tools:

```markdown
- If `Docs lookup policy: forbidden`, the worker must stay local-only: prompt file, assigned worktree, explicitly allowed repo files, launch metadata, signal files, listed local logs/artifacts, and required OpenCode skills.
- With policy `forbidden`, do not use OpenCode webfetch, websearch, MCP Exa, MCP Context7, official docs, or broad external docs research.
```

- [ ] **Step 4: Replace `Worker Model` block in `references/worker-prompt.md`**

Use:

```text
## WORKER MODEL
Runner: opencode
OpenCode agent: pr-worker|pr-review|pr-review-fix|...
OpenCode model: provider/model
OpenCode variant: provider-specific variant or empty
Task class: docs_light|exact_fix|implementation|runtime_debug|pr_review|review_fix|final_integration
Routing reason: one sentence explaining why this agent/model/variant is appropriate.
Do not change agent, model, or variant from inside the worker. If the task exceeds the selected route, return status="blocked" with evidence.
```

- [ ] **Step 5: Replace `Worker Skills` section**

Use:

```text
## REQUIRED OPENCODE SKILLS
Load skills in this order before substantive work and log each gate to logs/worker-{name}.log:
1. project-docs-maintenance when docs impact or docs review is in scope.
2. swarm-bug-reporting for implementation, PR review, review-fix, runtime/config checks, and verification that can discover bugs.
3. gh-pr-review for PR review and review-fix workers.
4. swarm-review-fix for PR review and review-fix workers.
5. swarm-pr-finish before commit/push/PR/DONE JSON/wake-up in full-contract workers.

If any required skill is unavailable, write status:"blocked" DONE JSON with the missing skill and wake the orchestrator.
DONE JSON must include required_skills and skills_loaded arrays.
```

- [ ] **Step 6: Update `signal-schema.md` full skeleton**

Add fields:

```json
"runner": "opencode",
"variant": "",
"required_skills": [],
"skills_loaded": [],
```

Change:

```json
"agent": "codex-321|planner|reviewer",
"model": "gpt-5.3-codex-spark|gpt-5.3-codex",
"reasoning_effort": "low|medium|high|xhigh",
```

To:

```json
"agent": "pr-worker|pr-review|pr-review-fix|...",
"model": "provider/model",
"variant": "",
```

- [ ] **Step 7: Update anti-drift checklist**

Add:

```markdown
- `runner` is missing or is not `opencode`
- `required_skills` or `skills_loaded` is missing or is not an array
- `skills_loaded` does not include every required skill from launch metadata
- `variant` is missing from a full-contract OpenCode worker signal
```

- [ ] **Step 8: Run docs contract tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py -q
```

Expected: remaining failures point to worker type/review references.

## Task 7: Update Worker Type And Review Verification References

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/worker-types.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/review-verification.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/red-flags.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`

- [ ] **Step 1: Replace implementation worker workflow**

Use OpenCode skills:

```markdown
Required workflow: `project-docs-maintenance when impacted -> swarm-bug-reporting -> implementation/test loop -> local self-review -> swarm-pr-finish`.
```

Do not mention `superpowers:requesting-code-review` inside OpenCode workers.

- [ ] **Step 2: Replace PR review workflow**

Use:

```markdown
Required workflow: `gh-pr-review -> project-docs-maintenance when docs/doc-contract risk exists -> swarm-review-fix review classification -> swarm-bug-reporting -> swarm-pr-finish`.
```

Keep read-only restrictions.

- [ ] **Step 3: Replace review-fix workflow**

Use:

```markdown
Required workflow: `gh-pr-review -> swarm-review-fix -> project-docs-maintenance when impacted -> swarm-bug-reporting -> focused tests -> swarm-pr-finish`.
```

Keep "fix only named blockers" and "same PR branch" requirements.

- [ ] **Step 4: Update operator quick worker model references**

Replace Spark/Codex model mentions with OpenCode agents:

```markdown
Route CI/status polling to a narrow read-only OpenCode agent when available; otherwise use `pr-review` with a prompt that forbids edits.
```

- [ ] **Step 5: Update review verification metadata checks**

In `review-verification.md`, replace model/reasoning checks with:

```markdown
- runner is `opencode`
- agent/model/variant match launch metadata
- required_skills and skills_loaded match launch metadata
- prompt_sha256 matches launch metadata
```

- [ ] **Step 6: Update red flags**

Add OpenCode-specific red flags:

```markdown
- Worker prompt names OpenCode skills but launch metadata lacks `required_skills`.
- OpenCode DONE JSON omits `skills_loaded`.
- Worker used webfetch/websearch under `Docs lookup policy: forbidden`.
- PR review worker runs with an edit-capable agent or edits files.
- Launch relies on global `pr-review` when project-local `pr-review` is expected.
```

- [ ] **Step 7: Run docs contract tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py -q
```

Expected: pass or only narrow failures in tests that need updated wording.

## Task 8: Update Tests To Lock The New Contract

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`

- [ ] **Step 1: Remove obsolete anti-OpenCode assertions**

Delete any assertion that forbids:

- `opencode`
- `open-code`
- `.config/opencode`
- `launch_opencode`
- current OpenCode models used by project agents

- [ ] **Step 2: Keep anti-legacy assertions scoped**

Use assertions that block active Codex worker routes, not historical filenames:

```python
assert "Default visible Codex `321` launch" not in infrastructure
assert "Launch visible Codex workers" not in skill
assert "Runner: codex-321" not in contract
```

Do not fail just because the legacy script file exists.

- [ ] **Step 3: Add positive OpenCode assertions across docs**

```python
assert "launch_opencode_worker.sh" in skill
assert "launch_opencode_worker.sh" in infrastructure
assert "OPENCODE_REQUIRED_SKILLS" in infrastructure
assert "REQUIRED OPENCODE SKILLS" in contract
assert "skills_loaded" in contract
assert "project-docs-maintenance" in contract
```

- [ ] **Step 4: Add launcher no-extra-registry-automation assertion**

Keep:

```python
assert "SWARM_ACTIVE_REGISTRY" not in launcher
assert "append_registry_entry" not in launcher
assert "validate_json_array" not in launcher
```

The launcher validates inputs and writes launch metadata, but it does not own the active registry.

- [ ] **Step 5: Run all skill contract tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests -q
```

Expected: all tests pass.

## Task 9: Smoke Test A Minimal OpenCode Worker

**Files:**
- Create temporary prompt: `/home/user/projects/rag-fresh/.codex/prompts/worker-opencode-smoke.md`
- Create temporary worktree: `/home/user/projects/rag-fresh-wt-opencode-smoke`
- Signal artifact: `/home/user/projects/rag-fresh-wt-opencode-smoke/.signals/worker-opencode-smoke.json`
- Launcher: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`

- [ ] **Step 1: Ensure this runs inside tmux**

Run:

```bash
tmux display-message -p '#{pane_id} #{pane_dead}'
```

Expected: output like `%12 0`. If not inside tmux, stop and run this smoke only from a tmux orchestrator pane.

- [ ] **Step 2: Create a temporary worktree**

Run:

```bash
cd /home/user/projects/rag-fresh
git worktree add /home/user/projects/rag-fresh-wt-opencode-smoke -b test/opencode-smoke-$(date +%Y%m%d%H%M%S)
mkdir -p .codex/prompts /home/user/projects/rag-fresh-wt-opencode-smoke/.signals /home/user/projects/rag-fresh-wt-opencode-smoke/logs
```

Expected: worktree created.

- [ ] **Step 3: Write minimal smoke prompt**

Create `/home/user/projects/rag-fresh/.codex/prompts/worker-opencode-smoke.md` with:

```markdown
# OpenCode Smoke Worker

## TASK

Load required OpenCode skills, write compact DONE JSON, and wake the orchestrator.
Do not edit repository files.

## REQUIRED OPENCODE SKILLS

Load in order:
1. project-docs-maintenance
2. swarm-bug-reporting
3. swarm-pr-finish

If any skill is unavailable, write blocked JSON.

## SIGNALING

WORKER: W-opencode-smoke
SIGNAL_FILE: /home/user/projects/rag-fresh-wt-opencode-smoke/.signals/worker-opencode-smoke.json
ORCH_PANE: {{ORCH_PANE}}

DONE JSON must include:
- status
- worker
- runner:"opencode"
- agent
- model
- variant
- required_skills
- skills_loaded
- commands array with objects
- summary
- ts

After writing valid JSON, submit `[DONE] W-opencode-smoke /home/user/projects/rag-fresh-wt-opencode-smoke/.signals/worker-opencode-smoke.json` to ORCH_PANE with tmux `send-keys -l`, sleep 0.25, then `C-m`.
```

- [ ] **Step 4: Launch worker**

Run:

```bash
ORCH_PANE="$(tmux display-message -p '#{pane_id}')" \
OPENCODE_AGENT=pr-worker \
OPENCODE_MODEL=opencode-go/kimi-k2.6 \
OPENCODE_VARIANT= \
OPENCODE_REQUIRED_SKILLS=project-docs-maintenance,swarm-bug-reporting,swarm-pr-finish \
SWARM_LOCAL_ONLY=1 \
/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  W-opencode-smoke \
  /home/user/projects/rag-fresh-wt-opencode-smoke \
  /home/user/projects/rag-fresh/.codex/prompts/worker-opencode-smoke.md
```

Expected: launcher prints `runner=opencode`, `agent=pr-worker`, `skills_available=true`, prompt path, launch metadata path, and tmux window id.

- [ ] **Step 5: Validate signal JSON after wake-up**

After `[DONE]` arrives, run:

```bash
python3 -m json.tool /home/user/projects/rag-fresh-wt-opencode-smoke/.signals/worker-opencode-smoke.json >/dev/null
python3 - <<'PY'
import json
from pathlib import Path
p = Path("/home/user/projects/rag-fresh-wt-opencode-smoke/.signals/worker-opencode-smoke.json")
d = json.loads(p.read_text())
assert d["status"] == "done"
assert d["runner"] == "opencode"
assert d["agent"] == "pr-worker"
assert isinstance(d["required_skills"], list)
assert isinstance(d["skills_loaded"], list)
assert set(d["required_skills"]) <= set(d["skills_loaded"])
assert isinstance(d["commands"], list)
PY
```

Expected: exits 0.

- [ ] **Step 6: Close worker window and remove smoke resources**

Run:

```bash
TMUX="" tmux kill-window -t W-opencode-smoke 2>/dev/null || true
git -C /home/user/projects/rag-fresh worktree remove /home/user/projects/rag-fresh-wt-opencode-smoke
git -C /home/user/projects/rag-fresh branch --list 'test/opencode-smoke-*'
```

If the smoke branch remains and has no useful commits:

```bash
git -C /home/user/projects/rag-fresh branch -D test/opencode-smoke-YYYYMMDDHHMMSS
```

- [ ] **Step 7: Record smoke result**

Append a short note to `${CODEX_HOME:-$HOME/.codex}/swarm-feedback/rag-fresh.md` with:

- timestamp;
- launcher command;
- OpenCode version;
- agent/model/variant;
- skills loaded;
- wake-up success/failure;
- any drift found.

## Task 10: Final Verification And Handoff

**Files:**
- Verify all modified files listed above.

- [ ] **Step 1: Run skill contract tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run repo check for repo-owned OpenCode changes**

Run from `/home/user/projects/rag-fresh` or the dedicated worktree:

```bash
make check
```

Expected: pass. If unrelated pre-existing failures occur, capture exact failing command and evidence.

- [ ] **Step 3: Check OpenCode agent discovery**

Run:

```bash
opencode agent list | rg -n "pr-worker|pr-review|pr-review-fix"
```

Expected: all three agents listed.

- [ ] **Step 4: Check required skill files exist**

Run:

```bash
test -f /home/user/projects/rag-fresh/.opencode/skills/gh-pr-review/SKILL.md
test -f /home/user/.config/opencode/skills/project-docs-maintenance/SKILL.md
test -f /home/user/.config/opencode/skills/swarm-bug-reporting/SKILL.md
test -f /home/user/.config/opencode/skills/swarm-pr-finish/SKILL.md
test -f /home/user/.config/opencode/skills/swarm-review-fix/SKILL.md
```

Expected: all commands exit 0.

- [ ] **Step 5: Run the real smoke test evidence check**

Confirm Task 9 passed and record the signal path and launch metadata path.

- [ ] **Step 6: Review operator-skill diff manually**

Because `/home/user/.codex/skills/tmux-swarm-orchestration` is not a git repo, inspect changed files directly:

```bash
rg -n "codex-321|Codex `321`|CODEX_MODEL|CODEX_REASONING_EFFORT|Runner: codex-321|Default visible Codex" /home/user/.codex/skills/tmux-swarm-orchestration
rg -n "opencode|REQUIRED OPENCODE SKILLS|skills_loaded|required_skills|launch_opencode_worker.sh" /home/user/.codex/skills/tmux-swarm-orchestration
```

Expected: no active Codex worker routing remains; OpenCode worker contract appears in the active docs.

- [ ] **Step 7: Commit remaining repo-owned changes**

Run:

```bash
cd /home/user/projects/rag-fresh
git status --short .opencode docs/superpowers/plans/2026-05-11-opencode-swarm-workers.md
git add .opencode/agents/pr-worker.md .opencode/agents/pr-review.md .opencode/agents/pr-review-fix.md docs/superpowers/plans/2026-05-11-opencode-swarm-workers.md
git commit -m "chore: migrate swarm agents to opencode"
```

Skip already committed files. Do not stage unrelated dirty files.

- [ ] **Step 8: Final report**

Report:

- changed operator skill files;
- changed repo files and commit hashes;
- tests run and results;
- smoke test result;
- remaining risks, especially local-only enforcement strategy and global skill dependencies.
