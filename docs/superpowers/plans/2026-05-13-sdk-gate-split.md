# SDK Gate Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `sdk-research` produce worker-ready SDK/custom baselines while `tmux-swarm-orchestration` enforces those baselines at worker launch and acceptance.

**Architecture:** Keep `tmux-swarm-orchestration` as the thin launch and acceptance control plane. Move SDK/API/runtime knowledge acquisition into `sdk-research`, then tighten tmux swarm references and validators so SDK-sensitive implementation cannot launch or pass without an explicit baseline, and inconclusive baselines block implementation.

**Tech Stack:** Markdown skill contracts, Python 3 standard library CLI validators, pytest, MCP Context7 policy text, OpenCode worker prompts.

---

## Scope Check

This plan covers one connected subsystem: the SDK-native gate used before and
after tmux swarm worker execution. It touches two skill packages:

- `/home/USER/.codex/skills/sdk-research`
- `/home/USER/.codex/skills/tmux-swarm-orchestration`

The plan file and approved spec live in the `rag-fresh` repo:

- Spec: `docs/superpowers/specs/2026-05-13-sdk-gate-split-design.md`
- Plan: `docs/superpowers/plans/2026-05-13-sdk-gate-split.md`

Do not redesign general project knowledge management in this iteration. Do not
move tmux launch, active-worker registry, prompt SHA, signal JSON, or DONE JSON
ownership into `sdk-research`.

Global skill files under `/home/USER/.codex/skills/...` may not be part of this
repo's normal git history. For global skill changes, run tests and report exact
diffs/evidence unless the operator provides a separate skill repository.

## File Structure

### Knowledge Producer

- Modify: `/home/USER/.codex/skills/sdk-research/SKILL.md`
  - Add explicit output classifications: `sdk_sensitive`, `not_applicable`,
    `inconclusive`.
  - Add worker-ready `SDK/custom decision` output format with evidence,
    version assumptions, required shape, forbidden custom, allowed glue,
    worker docs lookup policy, and DONE JSON expectations.
  - Define `inconclusive` as "implementation workers must not launch".
  - Keep Context7 optional and scoped to version-sensitive or missing local
    behavior.

### Orchestration Enforcement

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/SKILL.md`
  - Tighten Default Flow step 4 and Runner Contract around `sdk-research`
    output.
  - Preserve router brevity; point detailed rules to `references/sdk-native.md`.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/sdk-native.md`
  - Make the SDK gate the source of truth for classification, baseline format,
    inconclusive blocking, worker blocked contract, and acceptance rules.
  - Replace the older loose decision block with the approved baseline fields.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/worker-prompt.md`
  - Require full prompts to carry the worker-ready baseline or
    `sdk_native_check:not_applicable` with a reason.
  - State that workers block when SDK-sensitive baseline is missing or
    inconclusive.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
  - Update implementation/review/review-fix snippets to use the new baseline
    format and blocked contract.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`
  - Document the blocked reason and SDK evidence expectations.
  - Keep the existing strict DONE JSON fields unchanged unless validator tests
    require a new optional field.

### Validators And Tests

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py`
  - Validate `SDK/custom decision` classification when the block is present.
  - Reject full prompts with `classification: inconclusive`.
  - Require core baseline fields for `classification: sdk_sensitive`.
  - Accept `classification: not_applicable` or existing
    `sdk_native_check:not_applicable` for non-SDK prompts.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py`
  - Keep the current `sdk_native_check` enum.
  - Add machine-checkable validation for `status:"blocked"` with
    `block_reason:"missing_or_insufficient_sdk_baseline"` when a worker reports
    SDK baseline insufficiency.
  - Add optional `--prompt` validation so acceptance can compare DONE JSON
    fields to the SDK/custom decision that launched the worker.
  - Do not require new fields for all blocked signals unless tests show current
    workers already provide a compatible shape.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`
  - Add tests for `sdk_sensitive`, `not_applicable`, and `inconclusive`
    prompt behavior.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py`
  - Add tests for accepted and rejected SDK-baseline blocked signals.

- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
  - Add text-contract assertions for the split between `sdk-research` and
    `tmux-swarm-orchestration`.

## Task 1: Add Prompt Validator Tests For Baseline Classifications

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`

- [ ] **Step 1: Add a helper for replacing the SDK decision block**

Append this helper after `_valid_full_prompt()`:

```python
def _replace_sdk_decision(prompt: str, decision: str) -> str:
    old = (
        "SDK/custom decision: orchestrator sdk-research result; use repo-native "
        "SDK/API first; SDK registry match: no_match; existing project pattern: "
        "not_applicable; Context7 baseline supplied by orchestrator: "
        "not_applicable; custom code allowed only for not_applicable; block "
        "with custom_justification instead of inventing custom transport/model.\n"
    )
    return prompt.replace(old, decision)
```

- [ ] **Step 2: Add a passing `sdk_sensitive` baseline test**

Append:

```python
def test_prompt_validator_accepts_worker_ready_sdk_sensitive_baseline(tmp_path: Path) -> None:
    decision = """SDK/custom decision:
classification: sdk_sensitive
registry_source: docs/engineering/sdk-registry.md
local_pattern: src/retrieval/qdrant.py::build_client
sdk_docs_evidence:
- local: src/retrieval/qdrant.py::build_client
- registry: docs/engineering/sdk-registry.md
- docs: Context7 /qdrant/qdrant-client
version_assumption:
- known_version: qdrant-client==1.15.1
required_shape:
- use AsyncQdrantClient with api_key
forbidden_custom:
- custom HTTP auth headers
allowed_custom:
- DTO-to-SDK glue only
worker_docs_lookup_policy: forbidden
done_json_expectation:
- sdk_native_check=native_used
- custom_justification=
- sdk_docs_evidence=<array>
"""
    prompt = _replace_sdk_decision(_valid_full_prompt(), decision)

    result = _run(_write_prompt(tmp_path, prompt))

    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3: Add a passing `not_applicable` baseline test**

Append:

```python
def test_prompt_validator_accepts_not_applicable_sdk_baseline(tmp_path: Path) -> None:
    decision = """SDK/custom decision:
classification: not_applicable
registry_source: not_found
local_pattern: not_found
sdk_docs_evidence:
- local: docs-only README link update
version_assumption:
- unknown_version: not needed for docs-only work
required_shape:
- no SDK/API/runtime behavior changes
forbidden_custom:
- SDK/API/runtime behavior changes
allowed_custom:
- local documentation edits only
worker_docs_lookup_policy: forbidden
done_json_expectation:
- sdk_native_check=not_applicable
- custom_justification=
- sdk_docs_evidence=[]
"""
    prompt = _replace_sdk_decision(_valid_full_prompt(), decision)

    result = _run(_write_prompt(tmp_path, prompt))

    assert result.returncode == 0, result.stderr
```

- [ ] **Step 4: Add an `inconclusive` rejection test**

Append:

```python
def test_prompt_validator_rejects_inconclusive_for_implementation_launch(tmp_path: Path) -> None:
    decision = """SDK/custom decision:
classification: inconclusive
registry_source: docs/engineering/sdk-registry.md
local_pattern: not_found
sdk_docs_evidence:
- registry: docs/engineering/sdk-registry.md
version_assumption:
- unknown_version: qdrant-client version not found
required_shape:
- missing
forbidden_custom:
- custom SDK behavior
allowed_custom:
- none
worker_docs_lookup_policy: forbidden
done_json_expectation:
- sdk_native_check=blocker
- custom_justification=
- sdk_docs_evidence=<array>
"""
    prompt = _replace_sdk_decision(_valid_full_prompt(), decision)

    result = _run(_write_prompt(tmp_path, prompt))

    assert result.returncode != 0
    assert "inconclusive SDK/custom decision blocks implementation launch" in result.stderr
```

- [ ] **Step 5: Add a rejection test for the old unclassified one-line decision**

Append:

```python
def test_prompt_validator_rejects_unclassified_sdk_decision_block(tmp_path: Path) -> None:
    result = _run(_write_prompt(tmp_path, _valid_full_prompt()))

    assert result.returncode != 0
    assert "SDK/custom decision missing classification" in result.stderr
```

- [ ] **Step 6: Add a passing legacy-free full prompt fixture test**

Append:

```python
def test_prompt_validator_accepts_current_full_source_prompt_with_not_applicable_baseline(tmp_path: Path) -> None:
    decision = """SDK/custom decision:
classification: not_applicable
registry_source: not_found
local_pattern: not_found
sdk_docs_evidence:
- local: not needed for docs-only test fixture
version_assumption:
- unknown_version: not needed for docs-only test fixture
required_shape:
- no SDK/API/runtime behavior changes
forbidden_custom:
- SDK/API/runtime behavior changes
allowed_custom:
- prompt fixture only
worker_docs_lookup_policy: forbidden
done_json_expectation:
- sdk_native_check=not_applicable
- custom_justification=
- sdk_docs_evidence=[]
"""
    prompt = _replace_sdk_decision(_valid_full_prompt(), decision)

    result = _run(_write_prompt(tmp_path, prompt))

    assert result.returncode == 0, result.stderr
```

- [ ] **Step 7: Add a missing required field rejection test**

Append:

```python
def test_prompt_validator_rejects_sdk_sensitive_baseline_missing_required_shape(tmp_path: Path) -> None:
    decision = """SDK/custom decision:
classification: sdk_sensitive
registry_source: docs/engineering/sdk-registry.md
local_pattern: src/retrieval/qdrant.py::build_client
sdk_docs_evidence:
- local: src/retrieval/qdrant.py::build_client
version_assumption:
- known_version: qdrant-client==1.15.1
forbidden_custom:
- custom HTTP auth headers
allowed_custom:
- DTO-to-SDK glue only
worker_docs_lookup_policy: forbidden
done_json_expectation:
- sdk_native_check=native_used
"""
    prompt = _replace_sdk_decision(_valid_full_prompt(), decision)

    result = _run(_write_prompt(tmp_path, prompt))

    assert result.returncode != 0
    assert "SDK/custom decision missing required field: required_shape:" in result.stderr
```

- [ ] **Step 8: Update the old acceptance test**

Either remove `test_prompt_validator_accepts_current_full_source_prompt` or
change it to use the new `not_applicable` baseline fixture above. The old
one-line `SDK/custom decision` must no longer pass full-prompt validation.

- [ ] **Step 9: Run the prompt validator tests and confirm failure**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py
```

Expected: the new tests fail because `validate_worker_prompt.py` does not yet
parse baseline classifications or required fields.

## Task 2: Implement Prompt Baseline Validation

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py`

- [ ] **Step 1: Add baseline constants near `DOCS_POLICIES`**

```python
SDK_BASELINE_CLASSIFICATIONS = {"sdk_sensitive", "not_applicable", "inconclusive"}
SDK_BASELINE_REQUIRED_FIELDS = (
    "classification:",
    "registry_source:",
    "local_pattern:",
    "sdk_docs_evidence:",
    "version_assumption:",
    "required_shape:",
    "forbidden_custom:",
    "allowed_custom:",
    "worker_docs_lookup_policy:",
    "done_json_expectation:",
)
```

- [ ] **Step 2: Add an SDK decision block extractor below `has_any`**

```python
def sdk_decision_block(text: str) -> str | None:
    marker = "SDK/custom decision:"
    start = text.find(marker)
    if start < 0:
        return None
    rest = text[start:]
    next_heading = re.search(r"\n##\s+", rest)
    if next_heading:
        return rest[: next_heading.start()]
    return rest
```

- [ ] **Step 3: Add baseline validation helper**

```python
def validate_sdk_decision(text: str, errors: list[str]) -> None:
    block = sdk_decision_block(text)
    if block is None:
        return
    match = re.search(r"(?im)^\s*classification:\s*([a-z_]+)\s*$", block)
    if not match:
        errors.append("SDK/custom decision missing classification")
        return
    classification = match.group(1)
    if classification not in SDK_BASELINE_CLASSIFICATIONS:
        errors.append(f"SDK/custom decision classification is invalid: {classification}")
        return
    if classification == "inconclusive":
        errors.append("inconclusive SDK/custom decision blocks implementation launch")
        return
    for field in SDK_BASELINE_REQUIRED_FIELDS:
        if field not in block:
            errors.append(f"SDK/custom decision missing required field: {field}")
```

- [ ] **Step 4: Call the helper from `validate`**

Add this near the end of `validate`, before `return errors`:

```python
    validate_sdk_decision(text, errors)
```

- [ ] **Step 5: Run the focused prompt validator tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py
```

Expected: all tests in `test_prompt_validator.py` pass.

- [ ] **Step 6: Commit the validator test and implementation**

```bash
git -C /home/USER/.codex/skills/tmux-swarm-orchestration status --short
git -C /home/USER/.codex/skills/tmux-swarm-orchestration add tests/test_prompt_validator.py scripts/validate_worker_prompt.py
git -C /home/USER/.codex/skills/tmux-swarm-orchestration commit -m "test: enforce sdk baseline prompt contract"
```

If `/home/USER/.codex/skills/tmux-swarm-orchestration` is not a git repo, skip
the commit and record `git status --short` plus the test output in the final
implementation report.

## Task 3: Add Signal Validator Tests For SDK Baseline Blocking

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py`

- [ ] **Step 1: Extend `_run` to accept an optional prompt**

Update the helper signature and body:

```python
def _run(
    tmp_path: Path,
    signal: dict,
    launch: dict | None = None,
    role: str = "pr-review",
    prompt: str | None = None,
    extra: list[str] | None = None,
):
    signal_path = _write_json(tmp_path / "signal.json", signal)
    cmd = ["python3", str(VALIDATOR), "--role", role, "--signal", str(signal_path)]
    if launch is not None:
        launch_path = _write_json(tmp_path / "launch.json", launch)
        cmd.extend(["--launch", str(launch_path)])
    if prompt is not None:
        prompt_path = tmp_path / "worker-prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        cmd.extend(["--prompt", str(prompt_path)])
    if extra:
        cmd.extend(extra)
    return subprocess.run(cmd, text=True, capture_output=True, check=False)
```

- [ ] **Step 2: Add prompt baseline fixtures**

Append near the test helpers:

```python
def _sdk_sensitive_prompt(
    *,
    docs_used: bool = False,
    expected_sdk_check: str = "native_used",
) -> str:
    docs_line = "- docs: Context7 /qdrant/qdrant-client\n" if docs_used else ""
    return f"""SDK/custom decision:
classification: sdk_sensitive
registry_source: docs/engineering/sdk-registry.md
local_pattern: src/retrieval/qdrant.py::build_client
sdk_docs_evidence:
- local: src/retrieval/qdrant.py::build_client
{docs_line}version_assumption:
- known_version: qdrant-client==1.15.1
required_shape:
- use AsyncQdrantClient with api_key
forbidden_custom:
- custom HTTP auth headers
allowed_custom:
- DTO-to-SDK glue only
worker_docs_lookup_policy: forbidden
done_json_expectation:
- sdk_native_check={expected_sdk_check}
- custom_justification=
- sdk_docs_evidence=<array>
"""


def _not_applicable_prompt() -> str:
    return """SDK/custom decision:
classification: not_applicable
registry_source: not_found
local_pattern: not_found
sdk_docs_evidence:
- local: docs-only work
version_assumption:
- unknown_version: not needed
required_shape:
- no SDK/API/runtime behavior changes
forbidden_custom:
- SDK/API/runtime behavior changes
allowed_custom:
- local documentation only
worker_docs_lookup_policy: forbidden
done_json_expectation:
- sdk_native_check=not_applicable
- custom_justification=
- sdk_docs_evidence=[]
"""
```

- [ ] **Step 3: Add a passing blocked signal test**

Append:

```python
def test_blocked_signal_accepts_missing_sdk_baseline_contract(tmp_path: Path) -> None:
    signal = _base_signal()
    signal["status"] = "blocked"
    signal["review_decision"] = "escalate"
    signal["sdk_native_check"] = "blocker"
    signal["block_reason"] = "missing_or_insufficient_sdk_baseline"
    signal["needed_from_orchestrator"] = (
        "sdk/custom decision with required_shape and forbidden_custom"
    )
    signal["summary"] = "blocked on missing SDK baseline"
    signal["next_action"] = "orchestrator must supply SDK/custom decision"

    result = _run(
        tmp_path,
        signal,
        _launch(),
        role="delivery",
        prompt=_sdk_sensitive_prompt(expected_sdk_check="blocker"),
    )

    assert result.returncode == 0, result.stderr
```

- [ ] **Step 4: Add a rejection test for incomplete blocked contract**

Append:

```python
def test_blocked_signal_rejects_incomplete_missing_sdk_baseline_contract(tmp_path: Path) -> None:
    signal = _base_signal()
    signal["status"] = "blocked"
    signal["review_decision"] = "escalate"
    signal["sdk_native_check"] = "blocker"
    signal["block_reason"] = "missing_or_insufficient_sdk_baseline"
    signal["needed_from_orchestrator"] = ""

    result = _run(
        tmp_path,
        signal,
        _launch(),
        role="delivery",
        prompt=_sdk_sensitive_prompt(expected_sdk_check="blocker"),
    )

    assert result.returncode != 0
    assert "needed_from_orchestrator must describe required SDK baseline" in result.stderr
```

- [ ] **Step 5: Add acceptance rejection tests for baseline mismatches**

Append:

```python
def test_sdk_sensitive_prompt_rejects_not_applicable_signal(tmp_path: Path) -> None:
    signal = _base_signal()
    signal["sdk_native_check"] = "not_applicable"

    result = _run(tmp_path, signal, _launch(), role="pr-review", prompt=_sdk_sensitive_prompt())

    assert result.returncode != 0
    assert "sdk_sensitive baseline requires sdk_native_check native_used|custom_justified|blocker" in result.stderr


def test_sdk_native_check_must_match_done_json_expectation(tmp_path: Path) -> None:
    signal = _base_signal()
    signal["sdk_native_check"] = "blocker"

    result = _run(tmp_path, signal, _launch(), role="pr-review", prompt=_sdk_sensitive_prompt())

    assert result.returncode != 0
    assert "sdk_native_check must match prompt done_json_expectation:native_used" in result.stderr


def test_not_applicable_prompt_rejects_sdk_sensitive_signal(tmp_path: Path) -> None:
    signal = _base_signal()
    signal["sdk_native_check"] = "native_used"

    result = _run(tmp_path, signal, _launch(), role="pr-review", prompt=_not_applicable_prompt())

    assert result.returncode != 0
    assert "not_applicable baseline requires sdk_native_check:not_applicable" in result.stderr


def test_context7_baseline_requires_sdk_docs_evidence(tmp_path: Path) -> None:
    signal = _base_signal()
    signal["sdk_native_check"] = "native_used"
    signal["sdk_docs_evidence"] = []

    result = _run(
        tmp_path,
        signal,
        _launch(),
        role="pr-review",
        prompt=_sdk_sensitive_prompt(docs_used=True),
    )

    assert result.returncode != 0
    assert "Context7/official docs baseline requires sdk_docs_evidence" in result.stderr


def test_custom_justified_requires_custom_justification(tmp_path: Path) -> None:
    signal = _base_signal()
    signal["sdk_native_check"] = "custom_justified"
    signal["custom_justification"] = ""

    result = _run(
        tmp_path,
        signal,
        _launch(),
        role="pr-review",
        prompt=_sdk_sensitive_prompt(expected_sdk_check="custom_justified"),
    )

    assert result.returncode != 0
    assert "custom_justified requires custom_justification" in result.stderr
```

- [ ] **Step 6: Run the signal validator tests and confirm failure**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py
```

Expected: the new prompt-aware SDK gate tests fail until the validator supports
`--prompt` and baseline comparison.

## Task 4: Implement Signal Blocked Contract Validation

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py`

- [ ] **Step 1: Add optional blocked-contract fields**

Add these near `STRING_FIELDS`:

```python
OPTIONAL_STRING_FIELDS = {
    "block_reason",
    "needed_from_orchestrator",
}
```

- [ ] **Step 2: Validate optional string field types**

In `validate_common`, after the `STRING_FIELDS` loop, add:

```python
    for field in OPTIONAL_STRING_FIELDS:
        if field in data and not isinstance(data.get(field), str):
            fail(errors, f"{field} must be a string")
```

- [ ] **Step 3: Add a blocked SDK baseline validator**

Add after `validate_decision_consistency`:

```python
def validate_blocked_sdk_baseline(data: dict[str, Any], errors: list[str]) -> None:
    if data.get("status") != "blocked":
        return
    if data.get("block_reason") != "missing_or_insufficient_sdk_baseline":
        return
    if data.get("sdk_native_check") != "blocker":
        fail(errors, "missing_or_insufficient_sdk_baseline requires sdk_native_check:blocker")
    needed = data.get("needed_from_orchestrator")
    if not isinstance(needed, str) or "sdk/custom decision" not in needed or "required_shape" not in needed:
        fail(errors, "needed_from_orchestrator must describe required SDK baseline")
```

- [ ] **Step 4: Add prompt baseline parsing**

Add after `validate_blocked_sdk_baseline`:

```python
def load_prompt_baseline(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    marker = "SDK/custom decision:"
    start = text.find(marker)
    if start < 0:
        return {}
    block = text[start:]
    heading = re.search(r"\n##\s+", block)
    if heading:
        block = block[: heading.start()]
    match = re.search(r"(?im)^\s*classification:\s*([a-z_]+)\s*$", block)
    classification = match.group(1) if match else ""
    docs_used = bool(re.search(r"(?im)^\s*-\s*docs:\s*(Context7|official)", block))
    sdk_check_match = re.search(r"(?im)^\s*-\s*sdk_native_check=([^\s]+)\s*$", block)
    expected_sdk_check = sdk_check_match.group(1) if sdk_check_match else ""
    custom_match = re.search(r"(?im)^\s*-\s*custom_justification=(.*)$", block)
    expected_custom = custom_match.group(1).strip() if custom_match else ""
    docs_evidence_match = re.search(r"(?im)^\s*-\s*sdk_docs_evidence=(.*)$", block)
    expected_docs_evidence = docs_evidence_match.group(1).strip() if docs_evidence_match else ""
    return {
        "classification": classification,
        "docs_used": docs_used,
        "expected_sdk_check": expected_sdk_check,
        "expected_custom": expected_custom,
        "expected_docs_evidence": expected_docs_evidence,
    }
```

- [ ] **Step 5: Add prompt baseline consistency validation**

Add after `load_prompt_baseline`:

```python
def validate_prompt_sdk_baseline(
    data: dict[str, Any],
    baseline: dict[str, Any],
    errors: list[str],
) -> None:
    classification = baseline.get("classification")
    if not classification:
        return
    sdk_check = data.get("sdk_native_check")
    if classification == "inconclusive":
        fail(errors, "inconclusive SDK/custom decision blocks implementation acceptance")
    if classification == "sdk_sensitive":
        if sdk_check not in {"native_used", "custom_justified", "blocker"}:
            fail(errors, "sdk_sensitive baseline requires sdk_native_check native_used|custom_justified|blocker")
        expected_sdk_check = baseline.get("expected_sdk_check")
        if isinstance(expected_sdk_check, str) and expected_sdk_check and "|" not in expected_sdk_check:
            if sdk_check != expected_sdk_check:
                fail(errors, f"sdk_native_check must match prompt done_json_expectation:{expected_sdk_check}")
        if baseline.get("docs_used") and not data.get("sdk_docs_evidence"):
            fail(errors, "Context7/official docs baseline requires sdk_docs_evidence")
    if classification == "not_applicable":
        if sdk_check != "not_applicable":
            fail(errors, "not_applicable baseline requires sdk_native_check:not_applicable")
        if data.get("custom_justification"):
            fail(errors, "not_applicable baseline requires empty custom_justification")
    if sdk_check == "custom_justified" and not data.get("custom_justification"):
        fail(errors, "custom_justified requires custom_justification")
```

- [ ] **Step 6: Add `--prompt` CLI argument**

In `main`, add:

```python
    parser.add_argument("--prompt", type=Path)
```

Initialize `prompt_baseline = {}` before the `try` block, then load it inside
the `try` block:

```python
        prompt_baseline = load_prompt_baseline(args.prompt) if args.prompt else {}
```

- [ ] **Step 7: Call the validators from `validate_common` and `main`**

Add this before `validate_decision_consistency(data, errors)`:

```python
    validate_blocked_sdk_baseline(data, errors)
```

After `validate_role(args.role, signal, errors)` in `main`, add:

```python
        validate_prompt_sdk_baseline(signal, prompt_baseline, errors)
```

- [ ] **Step 8: Run the focused signal validator tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py
```

Expected: all tests in `test_signal_validator.py` pass.

- [ ] **Step 9: Commit the signal validator changes**

```bash
git -C /home/USER/.codex/skills/tmux-swarm-orchestration add tests/test_signal_validator.py scripts/validate_worker_signal.py
git -C /home/USER/.codex/skills/tmux-swarm-orchestration commit -m "test: enforce sdk baseline blocked signal"
```

If the skill package is not a git repo, skip the commit and record the focused
test output.

## Task 5: Update `sdk-research` To Produce Worker-Ready Baselines

**Files:**
- Modify: `/home/USER/.codex/skills/sdk-research/SKILL.md`

- [ ] **Step 1: Replace the old recommendation format with the approved baseline**

In `/home/USER/.codex/skills/sdk-research/SKILL.md`, replace `## Формат рекомендации`
with:

````markdown
## Формат рекомендации

Return a worker-ready block that can be pasted into a tmux swarm prompt:

```text
SDK/custom decision:
classification: sdk_sensitive | not_applicable | inconclusive
registry_source: docs/engineering/sdk-registry.md or not_found
local_pattern: src/foo.py::bar or not_found
sdk_docs_evidence:
- local: src/foo.py::bar
- registry: docs/engineering/sdk-registry.md
- docs: Context7 /org/library, if used
version_assumption:
- known_version: package==x.y.z or image tag, if known
- unknown_version: package/runtime version not found, if unknown
required_shape:
- use the repo-native or SDK-native API shape
forbidden_custom:
- custom clients, transports, parsers, lifecycle handling, auth, retries,
  pagination, vector/search wrappers, or runtime behavior that duplicates the
  SDK/framework
allowed_custom:
- thin glue explicitly listed here
worker_docs_lookup_policy: forbidden unless a scoped Context7 refresh is
  explicitly required
done_json_expectation:
- sdk_native_check=native_used | custom_justified | blocker | not_applicable
- custom_justification=<empty unless custom_justified>
- sdk_docs_evidence=<array>
```

Use `classification: not_applicable` when the SDK gate was checked and the task
does not affect SDK/API/framework/runtime behavior.

Use `classification: inconclusive` when local registry, current code, and
allowed docs lookup cannot produce a safe baseline. Inconclusive means
implementation workers must not launch; run research/docs-maintenance/registry
update first.

Keep the existing `## SDK Coverage` table only as optional human-readable
support after the worker-ready block.
````

- [ ] **Step 2: Update process text to mention the three classifications**

Add this under `## Процесс`:

```markdown
Every run ends with exactly one classification:

- `sdk_sensitive`: return the full worker-ready baseline.
- `not_applicable`: state why no SDK/API/framework/runtime behavior is affected.
- `inconclusive`: state what knowledge is missing; implementation workers must not launch.
```

- [ ] **Step 3: Update Common Mistakes**

Add:

```markdown
| Вернуть обычный совет вместо worker-ready baseline | Всегда начинай ответ с `SDK/custom decision:` |
| Запустить implementation worker при `inconclusive` | Сначала research/docs-maintenance/registry update |
```

- [ ] **Step 4: Review the skill text for stale contradictions**

Run:

```bash
rg -n "Кастом допустим|Формат рекомендации|inconclusive|SDK/custom decision" /home/USER/.codex/skills/sdk-research/SKILL.md
```

Expected: no remaining text implies "no match means custom is freely allowed"
without Context7/local-pattern caveats.

- [ ] **Step 5: Commit or record evidence**

```bash
git -C /home/USER/.codex/skills/sdk-research status --short
git -C /home/USER/.codex/skills/sdk-research add SKILL.md
git -C /home/USER/.codex/skills/sdk-research commit -m "docs: return worker-ready sdk baselines"
```

If the skill package is not a git repo, skip the commit and record the diff
with:

```bash
git diff -- /home/USER/.codex/skills/sdk-research/SKILL.md
```

## Task 6: Update tmux Swarm SDK Gate Contract Text

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/SKILL.md`
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/sdk-native.md`
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/worker-prompt.md`
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`

- [ ] **Step 1: Tighten the router text without expanding it**

In `/home/USER/.codex/skills/tmux-swarm-orchestration/SKILL.md`, update Default
Flow step 4 so it says:

```markdown
For SDK/API/framework/runtime-sensitive work, run `$sdk-research` before
implementation launch and paste its worker-ready `SDK/custom decision` into the
prompt. `classification: inconclusive` blocks implementation launch. Workers
use `Docs lookup policy: forbidden` unless the prompt scopes Context7 to a
named library/question.
```

- [ ] **Step 2: Replace the `sdk-native.md` decision block**

In `/home/USER/.codex/skills/tmux-swarm-orchestration/references/sdk-native.md`,
replace `## SDK/Custom Decision Block` with the baseline format from the spec.
Also add:

```markdown
`classification: inconclusive` is a hard launch blocker for implementation
workers. Start a research/docs-maintenance/registry-update task instead.
```

- [ ] **Step 3: Add the blocked contract to `sdk-native.md`**

Under `## Worker Prompt Section`, add:

````markdown
When SDK context is missing or insufficient, workers must write blocked DONE
JSON with:

```json
{
  "status": "blocked",
  "block_reason": "missing_or_insufficient_sdk_baseline",
  "needed_from_orchestrator": "sdk/custom decision with required_shape and forbidden_custom",
  "sdk_native_check": "blocker"
}
```
````

- [ ] **Step 4: Update worker prompt reference**

In `/home/USER/.codex/skills/tmux-swarm-orchestration/references/worker-prompt.md`,
replace the SDK section text with:

```markdown
For SDK-sensitive work, include the orchestrator's `$sdk-research` result as a
worker-ready `SDK/custom decision` block. Implementation prompts must not carry
`classification: inconclusive`; that classification blocks launch. Workers use
the supplied baseline and block with
`missing_or_insufficient_sdk_baseline` if it is absent or insufficient.
```

- [ ] **Step 5: Update prompt snippets**

In `/home/USER/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`,
replace old one-line `SDK/custom decision` examples with:

```text
SDK/custom decision:
classification: <sdk_sensitive|not_applicable>
registry_source: <path or not_found>
local_pattern: <file::symbol or not_found>
sdk_docs_evidence:
- <local/registry/docs evidence>
version_assumption:
- <known_version or unknown_version>
required_shape:
- <required SDK/native shape>
forbidden_custom:
- <custom code workers must not write>
allowed_custom:
- <thin glue only, or none>
worker_docs_lookup_policy: forbidden
done_json_expectation:
- sdk_native_check=<native_used|custom_justified|blocker|not_applicable>
- custom_justification=<empty unless custom_justified>
- sdk_docs_evidence=<array>
```

- [ ] **Step 6: Update signal schema**

In `/home/USER/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`,
document:

```markdown
For SDK baseline blockers, use:
`status:"blocked"`, `sdk_native_check:"blocker"`,
`block_reason:"missing_or_insufficient_sdk_baseline"`, and
`needed_from_orchestrator:"sdk/custom decision with required_shape and forbidden_custom"`.
```

- [ ] **Step 7: Run docs contract tests and confirm any failures**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py
```

Expected: this may fail until Task 7 adds/update assertions for the new text.

## Task 7: Add Documentation Contract Assertions

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py`

- [ ] **Step 1: Extend `test_sdk_docs_and_bug_disposition_gates_are_still_present`**

Add these assertions near the existing SDK assertions:

```python
    assert "classification: sdk_sensitive | not_applicable | inconclusive" in sdk
    assert "classification: inconclusive" in sdk
    assert "implementation workers must not launch" in sdk
    assert "missing_or_insufficient_sdk_baseline" in sdk
    assert "needed_from_orchestrator" in sdk
    assert "worker-ready `SDK/custom decision`" in worker_prompt
    assert "classification: inconclusive" in worker_prompt
```

- [ ] **Step 2: Add an sdk-research contract test if the package is readable**

If `test_skill_docs_contract.py` already reads external OpenCode skill paths,
add:

```python
SDK_RESEARCH = Path("/home/USER/.codex/skills/sdk-research/SKILL.md")
```

Then add a focused test:

```python
def test_sdk_research_returns_worker_ready_baseline() -> None:
    text = SDK_RESEARCH.read_text(encoding="utf-8")

    assert "SDK/custom decision:" in text
    assert "classification: sdk_sensitive | not_applicable | inconclusive" in text
    assert "worker_docs_lookup_policy" in text
    assert "version_assumption" in text
    assert "implementation workers must not launch" in text
```

- [ ] **Step 3: Run docs contract tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py
```

Expected: pass.

- [ ] **Step 4: Commit or record contract doc changes**

```bash
git -C /home/USER/.codex/skills/tmux-swarm-orchestration add SKILL.md references/sdk-native.md references/worker-prompt.md references/prompt-snippets.md references/signal-schema.md tests/test_skill_docs_contract.py
git -C /home/USER/.codex/skills/tmux-swarm-orchestration commit -m "docs: enforce sdk gate split contract"
```

If the skill package is not a git repo, skip the commit and record the diff and
test output.

## Task 8: Run Focused Regression Checks

**Files:**
- Test-only task.

- [ ] **Step 1: Run all tmux swarm orchestration skill tests**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests
```

Expected: pass.

- [ ] **Step 2: Validate representative prompt fixtures manually**

Create a temporary prompt with `classification: sdk_sensitive` and run:

```bash
python3 /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py --contract full /tmp/sdk-sensitive-worker-prompt.md
```

Expected: `valid`.

Create a temporary prompt with `classification: inconclusive` and run the same
command.

Expected: non-zero exit and
`inconclusive SDK/custom decision blocks implementation launch`.

- [ ] **Step 3: Validate representative blocked signal manually**

Create `/tmp/sdk-blocked-signal.json` with a full signal based on
`_base_signal()` plus:

```json
{
  "status": "blocked",
  "review_decision": "escalate",
  "sdk_native_check": "blocker",
  "block_reason": "missing_or_insufficient_sdk_baseline",
  "needed_from_orchestrator": "sdk/custom decision with required_shape and forbidden_custom"
}
```

Run:

```bash
python3 /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py --role delivery --signal /tmp/sdk-blocked-signal.json --prompt /tmp/sdk-sensitive-worker-prompt.md
```

Expected: `valid`.

- [ ] **Step 4: Check for stale contradictory SDK text**

Run:

```bash
rg -n "check Context7 as needed|Кастом допустим|invent|inconclusive|missing_or_insufficient_sdk_baseline|worker-ready" /home/USER/.codex/skills/sdk-research /home/USER/.codex/skills/tmux-swarm-orchestration
```

Expected:

- no generic "check Context7 as needed" prompt language remains for workers;
- no text says custom code is freely allowed when SDK registry has no match;
- new `inconclusive` and blocked-contract terms appear in the intended files.

## Final Verification

Run these commands before claiming implementation complete:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_prompt_validator.py
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_signal_validator.py
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests
```

Report:

- changed files under `/home/USER/.codex/skills/sdk-research`;
- changed files under `/home/USER/.codex/skills/tmux-swarm-orchestration`;
- whether those skill directories were git repos and whether commits were made;
- exact verification commands and pass/fail status;
- any residual risk around existing worker prompts that predate this gate.
