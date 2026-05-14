# Swarm Wake-Up Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace copied tmux wake-up snippets with a canonical helper that reads worker signal JSON, validates the frozen orchestrator window route, submits `[DONE]`, `[FAILED]`, or `[BLOCKED]`, and writes a receipt.

**Architecture:** Keep the existing `ORCH_TARGET=session:orch-...` route and launch-time window guards. Add a focused Python helper under the `tmux-swarm-orchestration` skill package; workers continue to own signal JSON creation and then call the helper for delivery. Update reusable contracts and prompt validation so new prompts use the helper instead of hand-written tmux wake-up commands.

**Tech Stack:** Python 3 standard library, Bash, tmux, pytest, Markdown skill contracts, OpenCode worker skills.

---

## Scope Check

This plan covers one subsystem: worker completion notification delivery. It does
not redesign the full DONE JSON schema, worker launch mechanics, route-check
nonce flow, or OpenCode runner model.

Run implementation in a dedicated worktree for repo-owned docs if desired. The
main implementation target is outside the repo:

- `/home/USER/.codex/skills/tmux-swarm-orchestration`
- `/home/USER/.codex/skills/swarm-worker-contract`
- `/home/USER/.config/opencode/skills/swarm-pr-finish`

The plan file and design spec are in the `rag-fresh` repo:

- `docs/superpowers/specs/2026-05-13-swarm-wakeup-helper-design.md`
- `docs/superpowers/plans/2026-05-13-swarm-wakeup-helper.md`

Do not commit global skill files unless the operator has a separate plugin/skill
repository for them. Verify with tests and record evidence in swarm feedback.

## File Structure

### New Helper

- Create: `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py`
  - CLI entrypoint for worker wake-up delivery.
  - Parses existing signal JSON.
  - Maps `status` to wake-up tag.
  - Validates live tmux target window identity.
  - Sends the wake-up through `ORCH_TARGET`.
  - Writes `.signals/wakeup-W-name.json` receipt.

### Tests

- Create: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_notify_orchestrator.py`
  - Unit tests for JSON parsing, status mapping, route guard failures, tmux command sequence, and receipt writing.
  - Use fake `tmux` executable in a temp directory so tests do not need a live tmux session.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
  - Replace raw `tmux send-keys` wake-up contract assertions with helper-path assertions.
  - Keep identity guard and status mapping assertions, now pointing at the helper and docs.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`
  - Add a prompt validation fixture that rejects new full worker prompts containing raw wake-up `tmux send-keys` snippets.
  - Add a fixture that accepts helper invocation.

### Contract Docs And Worker Skills

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`
  - Replace inline wake-up bash function with helper invocation.
  - Keep signal JSON skeleton and status/tag mapping description.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/infrastructure.md`
  - Update Signals section to identify the helper as the source of truth for wake-up delivery.
  - Keep unique window-name routing, route-check, launch metadata, and event-driven wait rules.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
  - Tell workers to write signal JSON atomically and call the helper.
  - Remove hand-written tmux wake-up commands from the finish contract.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
  - Replace wake-up snippets with helper invocation.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/worker-prompt.md`
  - Replace raw wake-up instructions with helper invocation.

- Modify: `/home/USER/.config/opencode/skills/swarm-pr-finish/SKILL.md`
  - Replace raw wake-up snippet with helper invocation.
  - Keep worker-owned JSON creation, validation, commit/push/PR rules, and docs impact rules.

- Modify: `/home/USER/.codex/skills/swarm-worker-contract/SKILL.md`
  - Replace raw wake-up snippet with helper invocation.

- Modify: `/home/USER/.codex/skills/swarm-feedback-maintenance/references/forward-testing.md`
  - Update wake-up forward-test guidance to verify helper invocation and receipt.

### Feedback Log

- Modify: `/home/USER/.codex/swarm-feedback/rag-fresh.md`
  - Append evidence, fix summary, tests, live smoke result, and residual risk.

## Task 1: Add Failing Helper Unit Tests

**Files:**
- Create: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_notify_orchestrator.py`
- Test command: `uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_notify_orchestrator.py`

- [ ] **Step 1: Create the test file with helper imports**

Add this test scaffold:

```python
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
HELPER = SKILL_ROOT / "scripts" / "swarm_notify_orchestrator.py"


def _write_fake_tmux(tmp_path: Path, script: str) -> Path:
    tmux = tmp_path / "tmux"
    tmux.write_text(script, encoding="utf-8")
    tmux.chmod(0o755)
    return tmux


def _run_helper(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    return subprocess.run(
        ["python3", str(HELPER), *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
```

- [ ] **Step 2: Add a status-to-tag success test**

Append:

```python
def test_done_signal_sends_done_and_writes_receipt(tmp_path: Path) -> None:
    signal = tmp_path / ".signals" / "W-test.json"
    signal.parent.mkdir()
    signal.write_text(json.dumps({"worker": "W-test", "status": "done"}) + "\n", encoding="utf-8")
    sent = tmp_path / "sent.jsonl"
    _write_fake_tmux(
        tmp_path,
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            if [ "$1" = "display-message" ]; then
              case "${{@: -1}}" in
                "#{{window_id}}") echo "@16" ;;
                "#{{window_name}}") echo "orch-test-20260513T000000-abcd" ;;
                "#{{session_name}}") echo "claude" ;;
                *) echo "unexpected format: ${{@: -1}}" >&2; exit 9 ;;
              esac
              exit 0
            fi
            if [ "$1" = "send-keys" ]; then
              printf '%s\\n' "$(printf '%q ' "$@")" >> {sent}
              exit 0
            fi
            echo "unexpected tmux command: $*" >&2
            exit 9
            """
        ),
    )

    result = _run_helper(
        tmp_path,
        "--signal", str(signal),
        "--worker", "W-test",
        "--target", "claude:orch-test-20260513T000000-abcd",
        "--window-id", "@16",
        "--window-name", "orch-test-20260513T000000-abcd",
        "--session", "claude",
        "--pane", "%16",
    )

    assert result.returncode == 0, result.stderr
    sent_text = sent.read_text(encoding="utf-8")
    assert "\\[DONE\\]\\ W-test" in sent_text
    assert "Enter" in sent_text
    assert "C-j" in sent_text
    receipt = signal.parent / "wakeup-W-test.json"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["tag"] == "DONE"
    assert data["status"] == "done"
    assert data["target"] == "claude:orch-test-20260513T000000-abcd"
    assert data["submit_sequence"] == ["literal", "Enter", "C-j"]
```

- [ ] **Step 3: Add invalid status and missing file tests**

Append:

```python
def test_invalid_status_fails_before_tmux_send(tmp_path: Path) -> None:
    signal = tmp_path / ".signals" / "W-test.json"
    signal.parent.mkdir()
    signal.write_text(json.dumps({"worker": "W-test", "status": "weird"}) + "\n", encoding="utf-8")
    sent = tmp_path / "sent.jsonl"
    _write_fake_tmux(tmp_path, "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> '" + str(sent) + "'\n")

    result = _run_helper(
        tmp_path,
        "--signal", str(signal),
        "--worker", "W-test",
        "--target", "claude:orch-test",
        "--window-id", "@16",
        "--window-name", "orch-test",
        "--session", "claude",
    )

    assert result.returncode == 2
    assert "invalid status" in result.stderr
    assert not sent.exists()


def test_missing_signal_file_fails_before_tmux_send(tmp_path: Path) -> None:
    sent = tmp_path / "sent.jsonl"
    _write_fake_tmux(tmp_path, "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> '" + str(sent) + "'\n")

    result = _run_helper(
        tmp_path,
        "--signal", str(tmp_path / ".signals" / "missing.json"),
        "--worker", "W-test",
        "--target", "claude:orch-test",
        "--window-id", "@16",
        "--window-name", "orch-test",
        "--session", "claude",
    )

    assert result.returncode == 2
    assert "signal file not found" in result.stderr
    assert not sent.exists()
```

- [ ] **Step 4: Add route guard mismatch test**

Append:

```python
def test_window_guard_mismatch_fails_before_send(tmp_path: Path) -> None:
    signal = tmp_path / ".signals" / "W-test.json"
    signal.parent.mkdir()
    signal.write_text(json.dumps({"worker": "W-test", "status": "failed"}) + "\n", encoding="utf-8")
    sent = tmp_path / "sent.jsonl"
    _write_fake_tmux(
        tmp_path,
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            if [ "$1" = "display-message" ]; then
              case "${{@: -1}}" in
                "#{{window_id}}") echo "@99" ;;
                "#{{window_name}}") echo "wrong-window" ;;
                "#{{session_name}}") echo "claude" ;;
              esac
              exit 0
            fi
            if [ "$1" = "send-keys" ]; then
              printf '%s\\n' "$*" >> {sent}
              exit 0
            fi
            exit 9
            """
        ),
    )

    result = _run_helper(
        tmp_path,
        "--signal", str(signal),
        "--worker", "W-test",
        "--target", "claude:orch-test",
        "--window-id", "@16",
        "--window-name", "orch-test",
        "--session", "claude",
    )

    assert result.returncode == 2
    assert "orchestrator window mismatch" in result.stderr
    assert not sent.exists()
```

- [ ] **Step 5: Run tests and confirm failure**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_notify_orchestrator.py
```

Expected: FAIL because `swarm_notify_orchestrator.py` does not exist.

## Task 2: Implement The Notification Helper

**Files:**
- Create: `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_notify_orchestrator.py`

- [ ] **Step 1: Create the helper with CLI parsing and JSON loading**

Create:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_TO_TAG = {"done": "DONE", "failed": "FAILED", "blocked": "BLOCKED"}
SUBMIT_SEQUENCE = ["literal", "Enter", "C-j"]


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 2


def load_signal(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"signal file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid signal JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("signal JSON must be an object")
    return data
```

- [ ] **Step 2: Add tmux helpers**

Append:

```python
def tmux_display(target: str, fmt: str) -> str:
    result = subprocess.run(
        ["tmux", "display-message", "-p", "-t", target, fmt],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"tmux display-message failed for {target}")
    return result.stdout.strip()


def tmux_send(target: str, line: str, submit_delay: float, fallback_delay: float) -> None:
    subprocess.run(["tmux", "send-keys", "-t", target, "-l", line], check=True)
    if submit_delay > 0:
        subprocess.run(["sleep", str(submit_delay)], check=True)
    subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], check=True)
    if fallback_delay > 0:
        subprocess.run(["sleep", str(fallback_delay)], check=True)
    subprocess.run(["tmux", "send-keys", "-t", target, "C-j"], check=True)
```

- [ ] **Step 3: Add validation and receipt writing**

Append:

```python
def validate_worker(signal_data: dict[str, Any], worker: str) -> None:
    signal_worker = signal_data.get("worker")
    if signal_worker is not None and signal_worker != worker:
        raise ValueError(f"worker mismatch: signal={signal_worker} requested={worker}")


def resolve_tag(signal_data: dict[str, Any]) -> tuple[str, str]:
    status = signal_data.get("status")
    if not isinstance(status, str):
        raise ValueError("signal status must be a string")
    tag = STATUS_TO_TAG.get(status)
    if tag is None:
        raise ValueError(f"invalid status: {status}")
    return status, tag


def validate_route(args: argparse.Namespace) -> dict[str, str]:
    actual = {
        "window_id": tmux_display(args.target, "#{window_id}"),
        "window_name": tmux_display(args.target, "#{window_name}"),
        "session_name": tmux_display(args.target, "#{session_name}"),
    }
    if (
        actual["window_id"] != args.window_id
        or actual["window_name"] != args.window_name
        or actual["session_name"] != args.session
    ):
        raise ValueError(
            "orchestrator window mismatch: "
            f"target={args.target} expected={args.session}/{args.window_id}/{args.window_name} "
            f"actual={actual['session_name']}/{actual['window_id']}/{actual['window_name']}"
        )
    if args.pane:
        try:
            pane_window_id = tmux_display(args.pane, "#{window_id}")
        except RuntimeError:
            pane_window_id = ""
        if pane_window_id and pane_window_id != args.window_id:
            raise ValueError(
                f"orchestrator pane guard mismatch: target={args.target} pane={args.pane} "
                f"expected_window={args.window_id} actual_window={pane_window_id}"
            )
    return actual


def write_receipt(
    signal_path: Path,
    worker: str,
    status: str,
    tag: str,
    args: argparse.Namespace,
    actual: dict[str, str],
) -> Path:
    receipt = signal_path.parent / f"wakeup-{worker}.json"
    data = {
        "worker": worker,
        "status": status,
        "tag": tag,
        "signal_file": str(signal_path),
        "target": args.target,
        "expected": {
            "window_id": args.window_id,
            "window_name": args.window_name,
            "session_name": args.session,
            "pane": args.pane or "",
        },
        "actual": actual,
        "submit_sequence": SUBMIT_SEQUENCE,
        "fallback_attempted": False,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt
```

- [ ] **Step 4: Add main entrypoint**

Append:

```python
def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify Codex orchestrator about a swarm worker signal.")
    parser.add_argument("--signal", required=True, type=Path)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--window-id", required=True)
    parser.add_argument("--window-name", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--pane", default="")
    parser.add_argument("--submit-delay", type=float, default=0.25)
    parser.add_argument("--fallback-delay", type=float, default=0.25)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        signal_data = load_signal(args.signal)
        validate_worker(signal_data, args.worker)
        status, tag = resolve_tag(signal_data)
        actual = validate_route(args)
        line = f"[{tag}] {args.worker} {args.signal}"
        tmux_send(args.target, line, args.submit_delay, args.fallback_delay)
        receipt = write_receipt(args.signal, args.worker, status, tag, args, actual)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        return fail(str(exc))
    print(str(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Make the script executable**

Run:

```bash
chmod +x /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py
```

- [ ] **Step 6: Run helper tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_notify_orchestrator.py
```

Expected: PASS.

## Task 3: Update Contract Tests For Helper-Based Wake-Up

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
- Test command: `uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`

- [ ] **Step 1: Replace wake-up snippet assertions**

In `test_wakeup_contract_requires_submit_after_buffer_paste`, replace raw
`tmux send-keys` assertions with:

```python
    helper_path = "scripts/swarm_notify_orchestrator.py"

    assert helper_path in signal_schema
    assert helper_path in infrastructure
    assert helper_path in opencode_finish
    assert "wakeup-" in signal_schema
    assert "receipt" in signal_schema
    assert 'tmux send-keys -t "$ORCH_TARGET" -l "$line"' not in signal_schema
    assert 'tmux send-keys -t "$ORCH_TARGET" Enter' not in opencode_finish
    assert 'tmux send-keys -t "$ORCH_TARGET" C-j' not in opencode_finish
```

- [ ] **Step 2: Replace identity guard assertions**

In `test_wakeup_contract_validates_orchestrator_window_identity`, keep the
field assertions but point them to docs and helper:

```python
    helper = _read("scripts/swarm_notify_orchestrator.py")
    for text in (signal_schema, opencode_finish, helper):
        assert "ORCH_TARGET" in text or "--target" in text
        assert "ORCH_WINDOW_ID" in text or "--window-id" in text
        assert "ORCH_WINDOW_NAME" in text or "--window-name" in text
        assert "ORCH_SESSION_NAME" in text or "--session" in text
        assert "orchestrator window mismatch" in text
```

Do not require OpenCode `swarm-pr-finish` to contain raw `tmux` commands.

- [ ] **Step 3: Add a helper existence test**

Append:

```python
def test_wakeup_helper_is_documented_and_executable() -> None:
    helper = SKILL_ROOT / "scripts" / "swarm_notify_orchestrator.py"
    signal_schema = _read("references/signal-schema.md")
    infrastructure = _read("infrastructure.md")
    opencode_finish = OPENCODE_SWARM_PR_FINISH.read_text(encoding="utf-8")

    assert helper.exists()
    assert helper.stat().st_mode & 0o111
    assert "swarm_notify_orchestrator.py" in signal_schema
    assert "swarm_notify_orchestrator.py" in infrastructure
    assert "swarm_notify_orchestrator.py" in opencode_finish
```

- [ ] **Step 4: Run docs contract tests and confirm failure**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py
```

Expected: FAIL until contract docs and OpenCode skill are updated.

## Task 4: Update Signal And Infrastructure Contracts

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/infrastructure.md`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`

- [ ] **Step 1: Replace inline wake-up function in signal schema**

In `references/signal-schema.md`, replace the `swarm_wake_orchestrator`
function block with this helper invocation:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py" \
  --signal "$SIGNAL_FILE" \
  --worker "W-{NAME}" \
  --target "$ORCH_TARGET" \
  --window-id "$ORCH_WINDOW_ID" \
  --window-name "$ORCH_WINDOW_NAME" \
  --session "$ORCH_SESSION_NAME" \
  --pane "$ORCH_PANE"
```

Keep the JSON-writing rule before this block.

- [ ] **Step 2: Update signal schema prose**

Replace prose about copied `tmux send-keys` snippets with:

```markdown
Writing JSON only is an incomplete worker finish. Wake-up delivery must go
through `scripts/swarm_notify_orchestrator.py`; the helper owns status-to-tag
mapping, tmux route guard checks, submit sequence, fallback behavior, and
`wakeup-W-name.json` receipt writing.

Do not hand-write terminal wake-up snippets in new worker prompts. If wake-up
delivery fails, inspect the helper stderr and any receipt file before scraping
raw OpenCode logs.
```

- [ ] **Step 3: Update infrastructure Signals section**

In `infrastructure.md`, keep unique window routing, but replace the raw
`Enter`/`C-j` guidance with:

```markdown
Workers send wake-ups by invoking
`${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py`
after writing signal JSON. The helper reads `status`, maps the tag, validates
the frozen `ORCH_TARGET=session:window_name` route against launch-time window
guards, submits the wake-up, and writes `.signals/wakeup-W-name.json`.

Prompt authors should not copy tmux `send-keys` commands into new worker
prompts. Change submit mechanics in the helper and tests, not in prompt prose.
```

- [ ] **Step 4: Run focused docs contract tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py::test_wakeup_contract_requires_submit_after_buffer_paste /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py::test_wakeup_contract_validates_orchestrator_window_identity
```

Expected: Still FAIL until worker skills are updated.

## Task 5: Update Worker Contracts And OpenCode Skill

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/worker-prompt.md`
- Modify: `/home/USER/.codex/skills/swarm-worker-contract/SKILL.md`
- Modify: `/home/USER/.config/opencode/skills/swarm-pr-finish/SKILL.md`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`

- [ ] **Step 1: Update `worker-contract.md`**

Replace any finish/wake-up command snippet that runs `tmux send-keys` directly
with the helper invocation:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py" \
  --signal "$SIGNAL_FILE" \
  --worker "$WORKER_NAME" \
  --target "$ORCH_TARGET" \
  --window-id "$ORCH_WINDOW_ID" \
  --window-name "$ORCH_WINDOW_NAME" \
  --session "$ORCH_SESSION_NAME" \
  --pane "$ORCH_PANE"
```

- [ ] **Step 2: Update prompt snippets**

In `references/prompt-snippets.md`, replace raw terminal wake-up instructions
with:

```text
After writing and validating SIGNAL_FILE, invoke the canonical wake-up helper:
python3 "${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py" --signal "$SIGNAL_FILE" --worker "$WORKER_NAME" --target "$ORCH_TARGET" --window-id "$ORCH_WINDOW_ID" --window-name "$ORCH_WINDOW_NAME" --session "$ORCH_SESSION_NAME" --pane "$ORCH_PANE"
```

- [ ] **Step 3: Update full worker prompt reference**

In `references/worker-prompt.md`, replace any instruction to use raw
`tmux send-keys` for wake-up with the same helper invocation and a note:

```text
Do not hand-write tmux wake-up commands; the helper owns delivery and receipt
writing.
```

- [ ] **Step 4: Update Codex `swarm-worker-contract`**

In `/home/USER/.codex/skills/swarm-worker-contract/SKILL.md`, replace the
wake-up gate snippet with the helper invocation. Keep the explanation that JSON
alone is incomplete.

- [ ] **Step 5: Update OpenCode `swarm-pr-finish`**

In `/home/USER/.config/opencode/skills/swarm-pr-finish/SKILL.md`, replace raw
`tmux send-keys` commands with the helper invocation. Keep status validation
requirements and explain that the helper reads `status` itself.

- [ ] **Step 6: Run docs contract tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py
```

Expected: PASS after docs and worker skills consistently reference the helper.

## Task 6: Update Prompt Validator To Block New Raw Wake-Up Snippets

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py`
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`
- Test command: `uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`

- [ ] **Step 1: Add failing validator tests**

In `test_prompt_validator.py`, add:

```python
def test_full_prompt_rejects_raw_tmux_wakeup(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text(
        _valid_full_prompt()
        + "\n```bash\n"
        + 'tmux send-keys -t "$ORCH_TARGET" -l "$line"\n'
        + 'tmux send-keys -t "$ORCH_TARGET" Enter\n'
        + "```\n",
        encoding="utf-8",
    )

    result = _run_validator("--contract", "full", str(prompt))

    assert result.returncode == 1
    assert "raw tmux wake-up snippets are forbidden" in result.stderr


def test_full_prompt_accepts_wakeup_helper(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text(
        _valid_full_prompt()
        + "\nWake with scripts/swarm_notify_orchestrator.py after writing SIGNAL_FILE.\n",
        encoding="utf-8",
    )

    result = _run_validator("--contract", "full", str(prompt))

    assert result.returncode == 0, result.stderr
```

Adjust helper names if the local test utilities use different names.

- [ ] **Step 2: Run validator tests and confirm failure**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py
```

Expected: FAIL until validator blocks raw wake-up snippets.

- [ ] **Step 3: Implement validator check**

In `validate_worker_prompt.py`, add a regex check for full prompts:

```python
RAW_WAKEUP_PATTERNS = [
    re.compile(r"tmux\s+send-keys\s+-t\s+['\"]?\$ORCH_TARGET['\"]?\s+-l"),
    re.compile(r"tmux\s+paste-buffer\b[^\n]*\s-t\s+['\"]?\$ORCH_TARGET"),
]
```

In the full-contract validation path:

```python
if any(pattern.search(text) for pattern in RAW_WAKEUP_PATTERNS):
    errors.append(
        "raw tmux wake-up snippets are forbidden in new full worker prompts; "
        "call scripts/swarm_notify_orchestrator.py after writing SIGNAL_FILE"
    )
```

- [ ] **Step 4: Run validator tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py
```

Expected: PASS.

## Task 7: Run Full Skill Test Suite

**Files:**
- All touched skill files.
- Test command: `uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/`

- [ ] **Step 1: Run syntax checks**

Run:

```bash
python3 -m py_compile \
  /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py \
  /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py

bash -n \
  /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/set_orchestrator_pane.sh
```

Expected: no output and exit 0.

- [ ] **Step 2: Run full tmux swarm skill tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/
```

Expected: PASS.

- [ ] **Step 3: Run skill validation if available**

Run:

```bash
python3 /home/USER/.codex/skills/quick_validate.py /home/USER/.codex/skills/tmux-swarm-orchestration
```

If this path does not exist, record that quick validation was unavailable.

## Task 8: Live Smoke Test The Helper

**Files:**
- Create temporary prompt under `/repo/.codex/prompts/worker-wakeup-helper-smoke.md`
- Create temporary worktree `/repo-wt-wakeup-helper-smoke`
- Use launcher: `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`

- [ ] **Step 1: Ensure current orchestrator marker is fresh**

Run from the intended Codex orchestrator pane:

```bash
ORCH_MARKER="/repo/.signals/orchestrator-pane.json" \
/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/set_orchestrator_pane.sh --ensure-window-name wakeup-helper-smoke
```

Expected: `.signals/orchestrator-pane.json` points to the current pane and a
unique `orch-wakeup-helper-smoke-...` window name.

- [ ] **Step 2: Send route-check nonce with helper-compatible submit sequence**

Run:

```bash
target="$(python3 - <<'PY'
import json
from pathlib import Path
m=json.loads(Path('/repo/.signals/orchestrator-pane.json').read_text())
print(f"{m['orchestrator_session_name']}:{m['orchestrator_window_name']}")
PY
)"
nonce="route-wakeup-helper-smoke-$(date +%s)-$RANDOM"
tmux send-keys -t "$target" -l "[ROUTE-CHECK] W-wakeup-helper-smoke $nonce"
sleep 0.25
tmux send-keys -t "$target" Enter
sleep 0.25
tmux send-keys -t "$target" C-j
printf '%s\n' "$nonce"
```

Expected: operator sees the route-check line as a submitted chat event.

- [ ] **Step 3: Create smoke worktree**

Run:

```bash
git worktree add /repo-wt-wakeup-helper-smoke -b swarm/wakeup-helper-smoke HEAD
```

Expected: worktree created on new branch.

- [ ] **Step 4: Create smoke prompt**

Create `/repo/.codex/prompts/worker-wakeup-helper-smoke.md`
with:

```markdown
WORKER MODEL: opencode-go/deepseek-v4-pro

Required OpenCode skills: none

Task: smoke test canonical swarm_notify_orchestrator.py wake-up helper.

Constraints:
- Do not edit repository source files.
- Do not run tests.
- Do not use webfetch, websearch, Exa, Context7, or external network.
- Docs lookup policy: forbidden

Expected behavior:
1. Write `/repo-wt-wakeup-helper-smoke/.signals/W-wakeup-helper-smoke.json`.
2. Invoke `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py`.
3. Stop after helper invocation.

Signal JSON:
```json
{"worker":"W-wakeup-helper-smoke","status":"done","summary":"Helper smoke signal written.","checks":[],"files_changed":[],"docs_impact":"none"}
```

Routing:
- ORCH_TARGET={{ORCH_TARGET}}
- ORCH_PANE={{ORCH_PANE}}
- ORCH_WINDOW_ID={{ORCH_WINDOW_ID}}
- ORCH_WINDOW_NAME={{ORCH_WINDOW_NAME}}
- ORCH_SESSION_NAME={{ORCH_SESSION_NAME}}
- ORCH_WINDOW_INDEX={{ORCH_WINDOW_INDEX}}
```

Tell the worker to call:

```bash
python3 /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py --signal /repo-wt-wakeup-helper-smoke/.signals/W-wakeup-helper-smoke.json --worker W-wakeup-helper-smoke --target "{{ORCH_TARGET}}" --window-id "{{ORCH_WINDOW_ID}}" --window-name "{{ORCH_WINDOW_NAME}}" --session "{{ORCH_SESSION_NAME}}" --pane "{{ORCH_PANE}}"
```

- [ ] **Step 5: Launch smoke worker**

Run:

```bash
ORCH_MARKER="/repo/.signals/orchestrator-pane.json" \
OPENCODE_AGENT=pr-review \
OPENCODE_MODEL=opencode-go/deepseek-v4-pro \
OPENCODE_VARIANT= \
OPENCODE_REQUIRED_SKILLS= \
SWARM_LOCAL_ONLY=1 \
SWARM_ROUTE_CHECK_CONFIRMED=1 \
SWARM_ROUTE_CHECK_NONCE="<nonce from step 2>" \
/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  W-wakeup-helper-smoke \
  /repo-wt-wakeup-helper-smoke \
  /repo/.codex/prompts/worker-wakeup-helper-smoke.md
```

Expected: launcher prints `window=W-wakeup-helper-smoke`, launch metadata path,
and `prompt_delivery=prompt_file_link_tui`.

- [ ] **Step 6: Verify live result**

Run:

```bash
test -f /repo-wt-wakeup-helper-smoke/.signals/W-wakeup-helper-smoke.json
test -f /repo-wt-wakeup-helper-smoke/.signals/wakeup-W-wakeup-helper-smoke.json
tmux capture-pane -p -t "$(python3 - <<'PY'
import json
from pathlib import Path
m=json.loads(Path('/repo/.signals/orchestrator-pane.json').read_text())
print(f"{m['orchestrator_session_name']}:{m['orchestrator_window_name']}")
PY
)" -S -120 | rg '\[DONE\] W-wakeup-helper-smoke'
```

Expected: both JSON files exist and `[DONE] W-wakeup-helper-smoke ...` appears
as a submitted chat event, not only as buffered input.

- [ ] **Step 7: Cleanup smoke worker**

Run:

```bash
tmux kill-window -t W-wakeup-helper-smoke 2>/dev/null || true
git worktree remove /repo-wt-wakeup-helper-smoke --force
git branch -D swarm/wakeup-helper-smoke
rm -f /repo/.codex/prompts/worker-wakeup-helper-smoke.md
```

Expected: no smoke window, worktree, branch, or prompt remains.

## Task 9: Record Maintenance Evidence

**Files:**
- Modify: `/home/USER/.codex/swarm-feedback/rag-fresh.md`

- [ ] **Step 1: Append feedback entry**

Append:

```markdown
## 2026-05-13TXX:XX:XX+00:00 — Canonical wake-up helper

- Evidence: previous live smoke proved raw `C-m` wake-up could leave `[DONE]`
  buffered in Codex input. The new helper centralizes wake-up delivery behind a
  tested script.
- Classification: `launcher_or_tmux`.
- Fix: added `scripts/swarm_notify_orchestrator.py`, updated swarm contracts
  and OpenCode `swarm-pr-finish` to call the helper, and updated prompt
  validation to reject new raw tmux wake-up snippets.
- Validation: list exact pytest, py_compile, bash -n, quick_validate, and live
  smoke results.
- Residual risk: already-launched workers may still use old prompt snippets;
  process their signal JSON manually if wake-up remains buffered.
```

- [ ] **Step 2: Run final status checks**

Run:

```bash
git status --short -- docs/superpowers/specs/2026-05-13-swarm-wakeup-helper-design.md docs/superpowers/plans/2026-05-13-swarm-wakeup-helper.md
tmux list-windows -a -F '#{window_name}' | rg '^W-wakeup-helper-smoke' || true
git worktree list | rg 'wakeup-helper-smoke' || true
```

Expected: only intended repo docs are dirty in the repo check; no smoke worker
or worktree remains.

## Task 10: Handoff Summary

**Files:**
- No file changes.

- [ ] **Step 1: Summarize implementation outcome**

Report:

- helper path;
- tests run and exact pass/fail results;
- live smoke result;
- files changed outside the repo;
- repo docs changed;
- residual risk for already-launched workers.

- [ ] **Step 2: Do not claim merge readiness for global skill files**

Because most changes live under `/home/USER/.codex` and `/home/USER/.config`,
do not present this as a normal repo PR unless the operator explicitly asks to
package those skill changes into a repo or plugin.
