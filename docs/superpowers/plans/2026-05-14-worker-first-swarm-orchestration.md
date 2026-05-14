# Worker-First Swarm Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `$tmux-swarm-orchestration` from orchestrator-heavy analysis to a worker-first control plane with DeepSeek V4 Flash/Pro secretary routes.

**Architecture:** Add first-class `secretary-flash` and `secretary-pro` OpenCode agents, secretary prompt/signal contracts, and launcher model integrity checks. Update routing docs so GPT-5.5 only performs high-value decisions while Flash/Pro secretary workers prepare issue/PR facts, decomposition, artifact validation, and next-worker prompts.

**Tech Stack:** Markdown skill docs, OpenCode agent frontmatter, Python 3 validators, Bash tmux launcher, pytest contract tests.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-14-worker-first-swarm-orchestration-design.md`
- Skill root: `/home/user/.codex/skills/tmux-swarm-orchestration`
- Repo OpenCode agents: `/home/user/projects/rag-fresh/.opencode/agents`
- Global OpenCode agents: `/home/user/.config/opencode/agents`

## File Structure

Create:

- `/home/user/projects/rag-fresh/.opencode/agents/secretary-flash.md`
  - Read-mostly low-cost secretary agent using `opencode-go/deepseek-v4-flash`.
- `/home/user/projects/rag-fresh/.opencode/agents/secretary-pro.md`
  - Read-mostly stronger secretary agent using `opencode-go/deepseek-v4-pro`.

Modify:

- `/home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md`
  - Add worker-first rule, secretary routes, secretary-first default flow.
- `/home/user/.codex/skills/tmux-swarm-orchestration/classification.md`
  - Add secretary-first routing decisions and worker-chain decomposition.
- `/home/user/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
  - Add secretary quick contract and prompt draft rules.
- `/home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md`
  - Document secretary agents, launch examples, model integrity checks.
- `/home/user/.codex/skills/tmux-swarm-orchestration/red-flags.md`
  - Add red flags for GPT-5.5 doing routine raw analysis.
- `/home/user/.codex/skills/tmux-swarm-orchestration/references/worker-types.md`
  - Add Secretary Flash and Secretary Pro role sections.
- `/home/user/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
  - Add secretary prompt snippets.
- `/home/user/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`
  - Add secretary schema details and validation command.
- `/home/user/.codex/skills/tmux-swarm-orchestration/references/review-verification.md`
  - Move semantic diff review from orchestrator to PR review workers.
- `/home/user/.codex/skills/tmux-swarm-orchestration/references/sdk-native.md`
  - Delegate SDK baseline production to secretary-pro/research workers.
- `/home/user/.codex/skills/tmux-swarm-orchestration/references/knowledge-freshness.md`
  - Delegate docs/research baseline phases.
- `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`
  - Validate selected OpenCode agent frontmatter model equals requested model.
- `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py`
  - Add `--role secretary` and schema validation.
- `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py`
  - Validate secretary prompt sections.
- `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`
  - Add model mismatch and secretary route contract tests.
- `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py`
  - Add secretary signal validation tests.
- `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`
  - Add secretary prompt validation tests.
- `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
  - Update route/model expectations and worker-first docs assertions.
- `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_knowledge_freshness_workflow.py`
  - Update SDK/docs baseline ownership tests.

Do not modify unrelated repo files. Treat the dirty repo worktree as user-owned.

## Task 1: Add Secretary Agent Files

**Files:**
- Create: `/home/user/projects/rag-fresh/.opencode/agents/secretary-flash.md`
- Create: `/home/user/projects/rag-fresh/.opencode/agents/secretary-pro.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`

- [ ] **Step 1: Write failing tests for secretary agent discovery**

Add a test asserting the repo contains both agent files and that each has the expected frontmatter model and safety denies:

```python
def test_repo_secretary_agents_exist_with_expected_models() -> None:
    flash = Path("/home/user/projects/rag-fresh/.opencode/agents/secretary-flash.md").read_text(encoding="utf-8")
    pro = Path("/home/user/projects/rag-fresh/.opencode/agents/secretary-pro.md").read_text(encoding="utf-8")

    assert "model: opencode-go/deepseek-v4-flash" in flash
    assert "model: opencode-go/deepseek-v4-pro" in pro
    for text in (flash, pro):
        assert "webfetch: deny" in text
        assert "websearch: deny" in text
        assert "external_directory: ask" in text
        assert "context7:" in text
        assert "enabled: false" in text
        assert "exa:" in text
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py::test_repo_secretary_agents_exist_with_expected_models -q
```

Expected: FAIL because the secretary agent files do not exist.

- [ ] **Step 3: Create `secretary-flash.md`**

Create `/home/user/projects/rag-fresh/.opencode/agents/secretary-flash.md`:

```markdown
---
description: Low-cost secretary worker for issue intake, queue triage, artifact checks, prompt drafts, and bounded read-only scans.
mode: primary
model: opencode-go/deepseek-v4-flash
permission:
  read: allow
  bash: allow
  edit: allow
  webfetch: deny
  websearch: deny
  external_directory: ask
  doom_loop: ask
  skill:
    "*": allow
mcp:
  context7:
    enabled: false
  exa:
    enabled: false
---

You are a low-cost secretary worker in a Codex-orchestrated tmux swarm.

Use the worker prompt as the source of truth. Do bounded issue/PR discovery,
artifact validation, route recommendations, and next-worker prompt drafts that
save orchestrator context. Persist results only through the requested logs,
prompt drafts, and signal JSON. Do not launch workers, merge PRs, alter issues,
or edit product files unless the prompt explicitly reserves those files.
```

- [ ] **Step 4: Create `secretary-pro.md`**

Create `/home/user/projects/rag-fresh/.opencode/agents/secretary-pro.md`:

```markdown
---
description: Strong secretary analyst for complex decomposition, SDK/runtime baselines, conflicting artifacts, and prompt refinement.
mode: primary
model: opencode-go/deepseek-v4-pro
permission:
  read: allow
  bash: allow
  edit: allow
  webfetch: deny
  websearch: deny
  external_directory: ask
  doom_loop: ask
  skill:
    "*": allow
mcp:
  context7:
    enabled: false
  exa:
    enabled: false
---

You are a stronger secretary analyst in a Codex-orchestrated tmux swarm.

Use the worker prompt as the source of truth. Do complex decomposition,
SDK/runtime baseline preparation, report reconciliation, and refined
next-worker prompt drafting. Persist results only through requested logs,
prompt drafts, and signal JSON. Do not launch workers, merge PRs, alter issues,
or edit product files unless the prompt explicitly reserves those files.
```

- [ ] **Step 5: Run the test again**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py::test_repo_secretary_agents_exist_with_expected_models -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add /home/user/projects/rag-fresh/.opencode/agents/secretary-flash.md /home/user/projects/rag-fresh/.opencode/agents/secretary-pro.md
git commit -m "feat(swarm): add secretary opencode agents"
```

## Task 2: Add Launcher Model Integrity Guard

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`

- [ ] **Step 1: Write failing docs/script contract test**

Add a test that requires the launcher to parse the selected agent frontmatter model and reject mismatches:

```python
def test_launcher_rejects_agent_frontmatter_model_mismatch() -> None:
    launcher = _read("scripts/launch_opencode_worker.sh")
    infrastructure = _read("infrastructure.md")
    red_flags = _read("red-flags.md")

    assert "agent_frontmatter_model" in launcher
    assert "OpenCode agent model mismatch" in launcher
    assert "model differs from selected agent frontmatter" in launcher
    assert "agent frontmatter model must match OPENCODE_MODEL" in infrastructure
    assert "launch metadata model differs from actual agent model" in red_flags
```

- [ ] **Step 2: Run failing test**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py::test_launcher_rejects_agent_frontmatter_model_mismatch -q
```

Expected: FAIL.

- [ ] **Step 3: Implement frontmatter model parsing in launcher**

In `launch_opencode_worker.sh`, immediately after `agent_file` is found, add:

```bash
agent_frontmatter_model="$(
  python3 - "$agent_file" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.match(r"\A---\n(?P<frontmatter>.*?)\n---", text, re.S)
frontmatter = match.group("frontmatter") if match else text
model_match = re.search(r"(?m)^\s*model:\s*([^\s#]+)\s*$", frontmatter)
print(model_match.group(1) if model_match else "")
PY
)"
if [[ -n "$agent_frontmatter_model" && "$agent_frontmatter_model" != "$opencode_model" ]]; then
  echo "ERROR: OpenCode agent model mismatch: OPENCODE_MODEL=$opencode_model agent=$opencode_agent agent_file=$agent_file frontmatter_model=$agent_frontmatter_model. The model differs from selected agent frontmatter; create/select an agent whose frontmatter model matches OPENCODE_MODEL." >&2
  exit 2
fi
```

- [ ] **Step 4: Record frontmatter model in launch metadata**

Add `AGENT_FRONTMATTER_MODEL="$agent_frontmatter_model"` to the launch metadata environment and write:

```python
"agent_frontmatter_model": os.environ["AGENT_FRONTMATTER_MODEL"],
```

Also include it in the final `printf` output:

```text
agent_frontmatter_model=%s
```

- [ ] **Step 5: Update docs for the guard**

In `infrastructure.md`, add:

```markdown
The launcher validates that the selected OpenCode agent frontmatter model must
match OPENCODE_MODEL. Do not reuse `pr-review` for Flash secretary work; create
or select a secretary agent with `model: opencode-go/deepseek-v4-flash`.
```

In `red-flags.md`, add:

```markdown
- Launch metadata model differs from actual agent model or selected agent
  frontmatter. Stop and create/select the correct OpenCode agent.
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add /home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh /home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md /home/user/.codex/skills/tmux-swarm-orchestration/red-flags.md /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py
git commit -m "fix(swarm): reject opencode model route mismatches"
```

## Task 3: Add Secretary Signal Validation

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py`

- [ ] **Step 1: Write failing secretary signal tests**

Add a `_secretary_signal()` fixture:

```python
def _secretary_signal() -> dict:
    return {
        "status": "done",
        "worker": "W-secretary",
        "mode": "secretary",
        "runner": "opencode",
        "agent": "secretary-flash",
        "model": "opencode-go/deepseek-v4-flash",
        "variant": "",
        "task_kind": "issue_triage",
        "confidence": "high",
        "summary": "issue triaged",
        "facts": [],
        "risks": [],
        "recommended_route": {
            "next_worker_type": "implementation",
            "agent": "pr-worker",
            "model": "opencode-go/kimi-k2.6",
            "contract": "full",
            "reason": "low-risk implementation",
        },
        "reserved_files": ["telegram_bot/bot.py"],
        "focused_checks": ["uv run pytest tests/unit/handlers/test_clear.py -q"],
        "needs_user": [],
        "artifact_paths": {
            "markdown": "logs/SECRETARY.md",
            "prompt_draft": "logs/NEXT_WORKER_PROMPT.md",
        },
        "commands": [
            {"cmd": "gh issue view 123 --json number,title", "exit": 0, "status": "passed", "required": True, "summary": "issue metadata read"}
        ],
        "next_action": "launch_next_worker",
        "ts": "2026-05-14T00:00:00Z",
    }
```

Add tests:

```python
def test_secretary_role_accepts_secretary_signal(tmp_path: Path) -> None:
    result = _run(tmp_path, _secretary_signal(), role="secretary")
    assert result.returncode == 0, result.stderr

def test_secretary_role_rejects_invalid_confidence(tmp_path: Path) -> None:
    signal = _secretary_signal()
    signal["confidence"] = "certain"
    result = _run(tmp_path, signal, role="secretary")
    assert result.returncode == 1
    assert "confidence must be one of low|medium|high" in result.stderr
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py::test_secretary_role_accepts_secretary_signal /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py::test_secretary_role_rejects_invalid_confidence -q
```

Expected: FAIL because `--role secretary` is not supported.

- [ ] **Step 3: Implement secretary role constants**

In `validate_worker_signal.py`, add:

```python
SECRETARY_TASK_KINDS = {
    "queue_triage",
    "issue_triage",
    "pr_triage",
    "decomposition",
    "sdk_baseline",
    "artifact_check",
    "prompt_draft",
}
SECRETARY_CONFIDENCE = {"low", "medium", "high"}
SECRETARY_NEXT_ACTIONS = {"launch_next_worker", "ask_user", "escalate", "finish"}
SECRETARY_NEXT_WORKER_TYPES = {
    "secretary-pro",
    "implementation",
    "pr-review",
    "review-fix",
    "runtime-verify",
    "blocked",
    "finish",
}
```

- [ ] **Step 4: Implement `validate_secretary`**

Add:

```python
def validate_secretary(data: dict[str, Any], errors: list[str]) -> None:
    validate_legacy_fields(data, errors)
    if data.get("status") not in STATUSES:
        fail(errors, "status must be one of done|failed|blocked")
    if data.get("mode") != "secretary":
        fail(errors, "mode must be secretary")
    if data.get("runner") != "opencode":
        fail(errors, "runner must be opencode")
    for field in ("worker", "agent", "model", "variant", "task_kind", "confidence", "summary", "next_action", "ts"):
        if not isinstance(data.get(field), str):
            fail(errors, f"{field} must be a string")
    if data.get("agent") not in {"secretary-flash", "secretary-pro"}:
        fail(errors, "agent must be secretary-flash|secretary-pro")
    if data.get("task_kind") not in SECRETARY_TASK_KINDS:
        fail(errors, "task_kind is invalid")
    if data.get("confidence") not in SECRETARY_CONFIDENCE:
        fail(errors, "confidence must be one of low|medium|high")
    if data.get("next_action") not in SECRETARY_NEXT_ACTIONS:
        fail(errors, "next_action is invalid")
    for field in ("facts", "risks", "reserved_files", "focused_checks", "needs_user", "commands"):
        if not isinstance(data.get(field), list):
            fail(errors, f"{field} must be an array")
    route = data.get("recommended_route")
    if not isinstance(route, dict):
        fail(errors, "recommended_route must be an object")
    else:
        if route.get("next_worker_type") not in SECRETARY_NEXT_WORKER_TYPES:
            fail(errors, "recommended_route.next_worker_type is invalid")
        for field in ("agent", "model", "contract", "reason"):
            if not isinstance(route.get(field), str):
                fail(errors, f"recommended_route.{field} must be a string")
        if route.get("contract") not in {"quick", "full"}:
            fail(errors, "recommended_route.contract must be quick|full")
    artifact_paths = data.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        fail(errors, "artifact_paths must be an object")
    else:
        if not isinstance(artifact_paths.get("markdown"), str):
            fail(errors, "artifact_paths.markdown must be a string")
        prompt_draft = artifact_paths.get("prompt_draft", "")
        if prompt_draft is not None and not isinstance(prompt_draft, str):
            fail(errors, "artifact_paths.prompt_draft must be a string")
    validate_commands(data, errors)
```

- [ ] **Step 5: Add CLI role**

Add `"secretary"` to the `--role` choices and route:

```python
if args.role == "secretary":
    validate_secretary(signal, errors)
```

- [ ] **Step 6: Document secretary schema**

In `references/signal-schema.md`, add a `Secretary Signal` section with the JSON skeleton from the spec and validation command:

```bash
python3 ${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py --role secretary --signal "$SIGNAL_FILE" --launch "$LAUNCH_FILE"
```

- [ ] **Step 7: Run secretary signal tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py::test_secretary_role_accepts_secretary_signal /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py::test_secretary_role_rejects_invalid_confidence -q
```

Expected: PASS.

- [ ] **Step 8: Run all signal validator tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add /home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py /home/user/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py
git commit -m "feat(swarm): validate secretary worker signals"
```

## Task 4: Add Secretary Prompt Validation

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`

- [ ] **Step 1: Write failing prompt validator tests**

Add a `_valid_secretary_prompt()` helper:

```python
def _valid_secretary_prompt() -> str:
    return """## STEP 0 POLICY GATE
Before any tool call or command, acknowledge:
`POLICY_ACK docs_lookup=forbidden local_only=true`.

## WORKER MODEL
Runner: opencode
OpenCode agent: secretary-flash
OpenCode model: opencode-go/deepseek-v4-flash
OpenCode variant: ""
Routing reason: cheap issue intake.

## SECRETARY PROMPT PAYLOAD
Target: issue #123.
Secretary type: secretary-flash.
Task kind: issue_triage.
Allowed scope: WORKTREE=/tmp/wt, logs/signals/prompt drafts only.
Docs lookup policy: forbidden
Expected artifacts: logs/SECRETARY.md, .signals/secretary.json, optional logs/NEXT_WORKER_PROMPT.md.
Recommended route fields: next_worker_type, agent, model, contract, reason.
Confidence policy: low|medium|high; use low when route is uncertain.

## ORCHESTRATOR ROUTING
ORCH_TARGET: {{ORCH_TARGET}}
ORCH_PANE: {{ORCH_PANE}}
ORCH_WINDOW_ID: {{ORCH_WINDOW_ID}}
ORCH_WINDOW_NAME: {{ORCH_WINDOW_NAME}}
ORCH_SESSION_NAME: {{ORCH_SESSION_NAME}}
ORCH_WINDOW_INDEX: {{ORCH_WINDOW_INDEX}}

SIGNAL_FILE=/tmp/wt/.signals/secretary.json
"""
```

Add:

```python
def test_quick_prompt_accepts_secretary_payload(tmp_path: Path) -> None:
    result = _run(_write_prompt(tmp_path, _valid_secretary_prompt()), contract="quick")
    assert result.returncode == 0, result.stderr

def test_secretary_prompt_requires_secretary_payload(tmp_path: Path) -> None:
    prompt = _valid_secretary_prompt().replace("## SECRETARY PROMPT PAYLOAD", "## OTHER")
    result = _run(_write_prompt(tmp_path, prompt), contract="quick")
    assert result.returncode == 1
    assert "secretary prompt missing ## SECRETARY PROMPT PAYLOAD" in result.stderr
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py::test_quick_prompt_accepts_secretary_payload /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py::test_secretary_prompt_requires_secretary_payload -q
```

Expected: FAIL.

- [ ] **Step 3: Implement secretary prompt validation**

In `validate_worker_prompt.py`, add:

```python
def is_secretary_prompt(text: str) -> bool:
    return bool(re.search(r"(?im)^\s*OpenCode agent:\s*secretary-(flash|pro)\s*$", text))
```

In `validate`, add for quick and full contracts:

```python
if is_secretary_prompt(text):
    if "## SECRETARY PROMPT PAYLOAD" not in text:
        errors.append("secretary prompt missing ## SECRETARY PROMPT PAYLOAD")
    for marker in ("Task kind:", "Expected artifacts:", "Recommended route fields:", "Confidence policy:"):
        if marker not in text:
            errors.append(f"secretary prompt missing {marker}")
    if not has_any(text, ("{{ORCH_TARGET}}", "__ORCH_TARGET__")):
        errors.append("secretary prompt source must include {{ORCH_TARGET}} or __ORCH_TARGET__")
    if "SIGNAL_FILE" not in text:
        errors.append("secretary prompt must state SIGNAL_FILE")
```

- [ ] **Step 4: Add prompt snippets**

In `references/prompt-snippets.md`, add `## Secretary Prompt` with a compact template using `secretary-flash`, `SECRETARY.md`, `secretary.json`, `NEXT_WORKER_PROMPT.md`, and `swarm_notify_orchestrator.py`.

- [ ] **Step 5: Add worker contract docs**

In `worker-contract.md`, add `## Secretary Worker Fast Path`:

- quick by default;
- writes `SECRETARY.md`;
- writes secretary signal JSON;
- may write `NEXT_WORKER_PROMPT.md`;
- does not launch workers;
- does not make merge decisions;
- uses `confidence` and `recommended_route`.

- [ ] **Step 6: Run prompt validator tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add /home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py /home/user/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md /home/user/.codex/skills/tmux-swarm-orchestration/worker-contract.md /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py
git commit -m "feat(swarm): add secretary prompt contract"
```

## Task 5: Rewrite Routing Docs To Worker-First

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/classification.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/worker-types.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/red-flags.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`

- [ ] **Step 1: Write failing docs contract tests**

Add tests requiring the new model routes:

```python
def test_worker_first_secretary_routes_are_documented() -> None:
    skill = _read("SKILL.md")
    classification = _read("classification.md")
    worker_types = _read("references/worker-types.md")
    infrastructure = _read("infrastructure.md")
    red_flags = _read("red-flags.md")
    bundle = _squash("\n".join([skill, classification, worker_types, infrastructure, red_flags]))

    assert "## Worker-First Orchestrator Rule" in skill
    assert "secretary-flash" in bundle
    assert "opencode-go/deepseek-v4-flash" in bundle
    assert "secretary-pro" in bundle
    assert "opencode-go/deepseek-v4-pro" in bundle
    assert "secretary_first" in classification
    assert "secretary_pro_escalation" in classification
    assert "GPT-5.5 high cannot be used for routine raw issue, PR, diff, or artifact analysis" in red_flags
```

- [ ] **Step 2: Run failing test**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py::test_worker_first_secretary_routes_are_documented -q
```

Expected: FAIL.

- [ ] **Step 3: Update `SKILL.md`**

Replace `## Thin Orchestrator Rule` with `## Worker-First Orchestrator Rule`.

Add:

```markdown
Codex is the decision plane, not the analyst by default. Workers do discovery,
classification evidence, decomposition drafts, SDK/runtime baselines, prompt
drafts, implementation, review, review-fix, artifact validation, and runtime
evidence. Codex launches, validates contracts, resolves high-risk ambiguity,
asks the user for safety/product/access decisions, and makes final merge/no-merge
judgments from accepted artifacts.
```

Add default routes:

```markdown
- Secretary intake, cheap scans, artifact checks, and prompt drafts:
  `secretary-flash` with `opencode-go/deepseek-v4-flash`.
- Complex decomposition, SDK/runtime baseline, conflicting artifact analysis:
  `secretary-pro` with `opencode-go/deepseek-v4-pro`.
- Implementation, plan slices, docs, quick smokes:
  `pr-worker` with `opencode-go/kimi-k2.6`.
- PR review, complex review-fix, runtime verification, escalation analysis:
  `pr-review`, `pr-review-fix`, or `complex-escalation` with
  `opencode-go/deepseek-v4-pro`.
```

Change default flow to:

```markdown
1. Intake: if no accepted `SECRETARY_BRIEF` exists and task is not tiny, launch `secretary-flash`.
2. Secretary validation: validate secretary signal and artifact paths.
3. Escalate to `secretary-pro` when risk/confidence requires it.
4. Launch delivery/review workers from accepted artifacts.
5. Final decision from validated implementation and review artifacts.
```

- [ ] **Step 4: Update `classification.md`**

Add decisions:

```markdown
| `secretary_first` | default when issue/PR/queue/decomposition facts are not already compacted |
| `secretary_pro_escalation` | Flash confidence is low, SDK/runtime risk exists, or reports conflict |
| `worker_chain` | accepted secretary artifact defines sequential workers |
```

Add rule:

```markdown
Do not make GPT-5.5 read raw issue bodies, PR diffs, SDK docs, long logs, or
worker transcripts for routine classification. Launch a secretary worker unless
the task is tiny or a safety/product decision is required.
```

- [ ] **Step 5: Update `infrastructure.md`**

Add secretary rows to OpenCode routing table:

```markdown
| secretary intake / cheap scan | `secretary-flash` | `opencode-go/deepseek-v4-flash`; logs/signals/prompt drafts only | 1 |
| secretary pro decomposition / SDK baseline | `secretary-pro` | `opencode-go/deepseek-v4-pro`; no product edits unless docs phase reserves docs files | 1 |
```

- [ ] **Step 6: Update `worker-types.md`**

Add `### Secretary Flash` and `### Secretary Pro` sections with allowed actions, forbidden actions, and artifact outputs.

- [ ] **Step 7: Update `red-flags.md`**

Add:

```markdown
- GPT-5.5 high is about to perform routine raw issue, PR, diff, or artifact
  analysis before a secretary worker artifact exists.
- A worker prompt is hand-written from raw issue context when a secretary prompt
  draft exists and validates.
```

- [ ] **Step 8: Run docs contract tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py -q
```

Expected: PASS after updating old route expectations to allow secretary routes.

- [ ] **Step 9: Commit**

```bash
git add /home/user/.codex/skills/tmux-swarm-orchestration/SKILL.md /home/user/.codex/skills/tmux-swarm-orchestration/classification.md /home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md /home/user/.codex/skills/tmux-swarm-orchestration/references/worker-types.md /home/user/.codex/skills/tmux-swarm-orchestration/red-flags.md /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py
git commit -m "docs(swarm): make secretary-first routing default"
```

## Task 6: Delegate Review, SDK, And Knowledge Gates

**Files:**
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/review-verification.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/sdk-native.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/knowledge-freshness.md`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
- Test: `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_knowledge_freshness_workflow.py`

- [ ] **Step 1: Write failing review delegation test**

Add:

```python
def test_semantic_review_and_sdk_baselines_are_delegated() -> None:
    review = _read("references/review-verification.md")
    sdk = _read("references/sdk-native.md")
    freshness = _read("references/knowledge-freshness.md")

    assert "Semantic diff review belongs to PR review workers" in review
    assert "Orchestrator diff review is bounded artifact sanity" in review
    assert "secretary-pro or a dedicated research worker produces the SDK/custom decision" in sdk
    assert "The orchestrator validates and accepts the baseline artifact" in sdk
    assert "Launch secretary-pro or a docs/research worker" in freshness
```

- [ ] **Step 2: Run failing test**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py::test_semantic_review_and_sdk_baselines_are_delegated -q
```

Expected: FAIL.

- [ ] **Step 3: Update review verification**

In `review-verification.md`, replace the mandatory deep diff review section with:

```markdown
## Semantic Review

Semantic diff review belongs to PR review workers. Orchestrator diff review is
bounded artifact sanity: verify PR files, reserved scope, head/base metadata,
signal validity, and disputed slices only. Do not read full diffs by default
when a valid current-head PR review artifact exists.
```

Retain the requirement that runtime/code PRs need a current-head read-only review worker before merge.

- [ ] **Step 4: Update SDK gate**

In `sdk-native.md`, replace “orchestrator owns docs lookup by default” language with:

```markdown
`secretary-pro` or a dedicated research worker produces the SDK/custom decision
when SDK/API/runtime behavior matters. The orchestrator validates and accepts
the baseline artifact, then freezes it into implementation/review prompts.
```

Keep workers blocked on inconclusive baselines.

- [ ] **Step 5: Update knowledge freshness**

In `knowledge-freshness.md`, change docs/research loop to prefer:

```markdown
Launch secretary-pro or a docs/research worker when reusable local truth is
missing, stale, or contradictory. The orchestrator validates evidence and
accepts or rejects the artifact.
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_knowledge_freshness_workflow.py -q
```

Expected: PASS after updating tests that assert old orchestrator-owned SDK wording.

- [ ] **Step 7: Commit**

```bash
git add /home/user/.codex/skills/tmux-swarm-orchestration/references/review-verification.md /home/user/.codex/skills/tmux-swarm-orchestration/references/sdk-native.md /home/user/.codex/skills/tmux-swarm-orchestration/references/knowledge-freshness.md /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py /home/user/.codex/skills/tmux-swarm-orchestration/tests/test_knowledge_freshness_workflow.py
git commit -m "docs(swarm): delegate review and SDK baselines to workers"
```

## Task 7: End-To-End Secretary Smoke Prompts

**Files:**
- Create: `/home/user/projects/rag-fresh/.codex/prompts/worker-secretary-flash-smoke.md`
- Create: `/home/user/projects/rag-fresh/.codex/prompts/worker-secretary-pro-smoke.md`
- Modify: `/home/user/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
- Test: live tmux smoke, not committed test output

- [ ] **Step 1: Create secretary-flash smoke prompt**

Create `/home/user/projects/rag-fresh/.codex/prompts/worker-secretary-flash-smoke.md` using the secretary prompt snippet. It should:

- target `gh issue list --state open --limit 10`;
- write `logs/SECRETARY.md`;
- write `.signals/secretary-flash-smoke.json`;
- recommend one next route;
- write optional `logs/NEXT_WORKER_PROMPT.md`;
- use `agent=secretary-flash`, `model=opencode-go/deepseek-v4-flash`.

- [ ] **Step 2: Validate secretary-flash prompt**

Run:

```bash
python3 /home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py --contract quick /home/user/projects/rag-fresh/.codex/prompts/worker-secretary-flash-smoke.md
```

Expected: `valid`.

- [ ] **Step 3: Create secretary-pro smoke prompt**

Create `/home/user/projects/rag-fresh/.codex/prompts/worker-secretary-pro-smoke.md`. It should:

- read the Flash artifact path from the prompt;
- assess whether deeper decomposition is needed;
- write `logs/SECRETARY-PRO.md`;
- write `.signals/secretary-pro-smoke.json`;
- use `agent=secretary-pro`, `model=opencode-go/deepseek-v4-pro`.

- [ ] **Step 4: Validate secretary-pro prompt**

Run:

```bash
python3 /home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py --contract quick /home/user/projects/rag-fresh/.codex/prompts/worker-secretary-pro-smoke.md
```

Expected: `valid`.

- [ ] **Step 5: Run Flash live smoke**

From the intended orchestrator tmux pane:

```bash
PROJECT_ROOT=/home/user/projects/rag-fresh
WT_PATH=/home/user/projects/rag-fresh-wt-secretary-flash-smoke
git worktree add "$WT_PATH" -b secretary/flash-smoke dev
mkdir -p "$WT_PATH/logs" "$WT_PATH/.signals" "$WT_PATH/.codex/prompts"
cp /home/user/projects/rag-fresh/.codex/prompts/worker-secretary-flash-smoke.md "$WT_PATH/.codex/prompts/"
ORCH_MARKER="$PROJECT_ROOT/.signals/orchestrator-pane.json" \
  /home/user/.codex/skills/tmux-swarm-orchestration/scripts/set_orchestrator_pane.sh --ensure-window-name secretary-flash-smoke
ORCH_MARKER="$PROJECT_ROOT/.signals/orchestrator-pane.json" \
OPENCODE_AGENT=secretary-flash \
OPENCODE_MODEL=opencode-go/deepseek-v4-flash \
OPENCODE_REQUIRED_SKILLS= \
SWARM_LOCAL_ONLY=0 \
  /home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  W-secretary-flash-smoke "$WT_PATH" "$WT_PATH/.codex/prompts/worker-secretary-flash-smoke.md"
```

Expected:

- OpenCode UI shows `Secretary Flash` and `DeepSeek V4 Flash`.
- Signal validates:

```bash
python3 /home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py --role secretary --signal "$WT_PATH/.signals/secretary-flash-smoke.json"
```

- [ ] **Step 6: Run Pro live smoke**

Repeat with `secretary-pro`, `opencode-go/deepseek-v4-pro`, and the Pro smoke prompt.

Expected:

- OpenCode UI shows `Secretary Pro` and `DeepSeek V4 Pro`.
- Signal validates with `--role secretary`.

- [ ] **Step 7: Record smoke notes**

Append a compact note to the implementation PR or issue. Do not paste raw logs.

- [ ] **Step 8: Commit smoke prompt snippets if they remain useful**

If smoke prompts are kept as reusable examples, commit them:

```bash
git add /home/user/projects/rag-fresh/.codex/prompts/worker-secretary-flash-smoke.md /home/user/projects/rag-fresh/.codex/prompts/worker-secretary-pro-smoke.md /home/user/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md
git commit -m "test(swarm): add secretary smoke prompts"
```

If not reusable, delete the smoke prompt files and do not commit them.

## Task 8: Full Verification And Cleanup

**Files:**
- All touched files from Tasks 1-7

- [ ] **Step 1: Run full tmux-swarm skill tests**

Run:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests -q
```

Expected: PASS.

- [ ] **Step 2: Inspect changed skill package files**

Run:

```bash
git -C /home/user/projects/rag-fresh status --short
git -C /home/user/projects/rag-fresh diff -- .opencode/agents .codex/prompts
git -C /home/user/.codex/skills/tmux-swarm-orchestration diff --stat
```

Expected:

- repo changes limited to secretary agents and optional smoke prompts;
- skill changes limited to planned files;
- no unrelated dirty files staged.

- [ ] **Step 3: Check launcher model mismatch manually**

Run a negative manual check with `OPENCODE_AGENT=pr-review` and `OPENCODE_MODEL=opencode-go/deepseek-v4-flash` against a dummy prompt/worktree.

Expected: launcher exits 2 with `OpenCode agent model mismatch`.

- [ ] **Step 4: Check secretary route manually**

Run launcher with `OPENCODE_AGENT=secretary-flash` and `OPENCODE_MODEL=opencode-go/deepseek-v4-flash`.

Expected: launch succeeds and UI shows DeepSeek V4 Flash.

- [ ] **Step 5: Update final docs if any smoke finding changed the contract**

If smoke testing reveals different OpenCode UI/model behavior, update:

- `/home/user/.codex/skills/tmux-swarm-orchestration/infrastructure.md`
- `/home/user/.codex/skills/tmux-swarm-orchestration/red-flags.md`
- `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launcher_registry_contract.py`

- [ ] **Step 6: Final commit**

If Task 8 produced docs/test changes:

```bash
git add <exact touched files>
git commit -m "docs(swarm): finalize worker-first secretary routing"
```

- [ ] **Step 7: Final report**

Report:

- commits created;
- tests run and results;
- live smoke outcomes;
- any skipped checks;
- residual risks.

## Implementation Notes

- Use `apply_patch` for manual edits.
- Do not edit user-owned dirty repo files.
- The skill package is outside the repo; verify its git status separately if it is under git. If it is not under git, still keep commits for repo-owned agent files and report skill-package file changes clearly.
- Do not run production, VPS, SSH, cloud, or real CRM actions.
- Do not copy `.env` or secrets into worktrees.
- Do not let secretary workers launch other workers.
- Do not normalize malformed worker JSON in the orchestrator. Fix the worker contract or validator instead.
