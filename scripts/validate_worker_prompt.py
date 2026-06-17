#!/usr/bin/env python3
"""Validate new tmux swarm worker prompt source files before launch."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from route_constants import CANONICAL_WORKER_ROUTES, SECRETARY_AGENT_MODELS  # noqa: E402


HARD_CODED_PANE_PATTERNS = (
    re.compile(r"Orchestrator pane for wake-up:\s*%[0-9]+\b"),
    re.compile(r"wake the orchestrator at\s+`%[0-9]+`"),
    re.compile(r"ORCH_PANE:\s*%[0-9]+\b"),
    re.compile(r"tmux\s+send-keys\b[^\n]*\s-t\s+['\"]?%[0-9]+\b"),
    re.compile(r"tmux\s+paste-buffer\b[^\n]*\s-t\s+['\"]?%[0-9]+\b"),
)

RAW_WAKEUP_PATTERNS = (
    re.compile(r"tmux\s+send-keys\b[^\n]*(?:\$\{ORCH_PANE[^}]*\}|\$ORCH_PANE)"),
    re.compile(r"tmux\s+paste-buffer\b[^\n]*(?:\$\{ORCH_PANE[^}]*\}|\$ORCH_PANE)"),
)

WINDOW_WAKEUP_PATTERNS = (
    re.compile(
        r"tmux\s+send-keys\s+-t\s+['\"]?(?:\$\{ORCH_TARGET[^}]*\}|\$ORCH_TARGET)['\"]?\s+-l\s+.+"
    ),
)

PASTE_BUFFER_WINDOW_WAKEUP_PATTERNS = (
    re.compile(r"tmux\s+paste-buffer\b[^\n]*\s-t\s+['\"]?(?:\$\{ORCH_TARGET[^}]*\}|\$ORCH_TARGET)"),
)

FULL_RAW_WAKEUP_PATTERNS = (
    re.compile(r"tmux\s+send-keys\s+-t\s+['\"]?(?:\$\{ORCH_TARGET[^}]*\}|\$ORCH_TARGET)['\"]?"),
    re.compile(r"tmux\s+paste-buffer\b[^\n]*\s-t\s+['\"]?(?:\$\{ORCH_TARGET[^}]*\}|\$ORCH_TARGET)"),
)

CJ_SUBMIT_PATTERNS = (
    re.compile(r"tmux\s+send-keys\b[^\n]*\bC-j\b"),
    re.compile(r"tmux\s+send-keys\b[^\n]*\bC-J\b"),
)

ENTER_SUBMIT_PATTERNS = (
    re.compile(
        r"tmux\s+send-keys\s+-t\s+['\"]?(?:\$\{ORCH_TARGET[^}]*\}|\$ORCH_TARGET)['\"]?\s+Enter\b"
    ),
)

CM_SUBMIT_PATTERNS = (
    re.compile(
        r"tmux\s+send-keys\s+-t\s+['\"]?(?:\$\{ORCH_TARGET[^}]*\}|\$ORCH_TARGET)['\"]?\s+C-m\b"
    ),
)

DOCS_POLICIES = (
    "forbidden",
    "context7_allowed",
    "context7_required",
    "official_docs_required",
    "exa_allowed_as_fallback",
)
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
IMPLEMENTATION_BLOCKED_WORKER_TYPES = {
    "implementation",
    "plan-execution",
    "review-fix",
    "pr-review",
    "local-verification",
}
CODE_CHANGING_WORKER_TYPES = {
    "implementation",
    "plan-execution",
    "quick",
    "review-fix",
}
FORBIDDEN_WORKER_SUPERPOWERS = {
    "superpowers:using-superpowers",
    "superpowers/using-superpowers",
    "superpowers:using-git-worktrees",
    "superpowers/using-git-worktrees",
    "superpowers:finishing-a-development-branch",
    "superpowers/finishing-a-development-branch",
}
FINISH_REPORT_SUPERPOWERS_FIELDS = (
    "superpowers_used",
    "skipped_superpowers",
    "tests_run",
    "verification_evidence",
    "evidence_commands",
)
INCONCLUSIVE_ALLOWED_WORKER_TYPES = {
    "research",
    "docs-update",
    "docs-only",
    "artifact-check",
    "issue-audit",
    "dependency-verify",
}
KNOWN_WORKER_TYPES = (
    CODE_CHANGING_WORKER_TYPES
    | INCONCLUSIVE_ALLOWED_WORKER_TYPES
    | {
        "ci-status",
        "cleanup",
        "complex-solo",
        "local-verification",
        "planner",
        "pr-review",
        "production-ops",
    }
)
ROUTE_OVERRIDE_MARKER = "Routing override: worker_route_noncanonical approved_by_user=true"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a worker prompt source template. Run before "
            "launch_kiro_worker.sh resolves ORCH placeholders."
        )
    )
    parser.add_argument("prompt", type=Path)
    parser.add_argument(
        "--contract",
        choices=("markdown", "full", "quick", "strict_json"),
        default="markdown",
        help="Prompt contract to validate. Markdown is default; strict_json/full require SIGNAL_FILE and JSON finish sections.",
    )
    return parser.parse_args()


def has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


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


def worker_type(text: str) -> str:
    match = re.search(r"(?im)^\s*Worker type:\s*([a-z0-9_-]+)", text)
    return match.group(1) if match else ""


def worker_field(text: str, field: str) -> str:
    match = re.search(rf"(?im)^\s*Worker {re.escape(field)}:\s*(.+?)\s*$", text)
    if not match:
        return ""
    return match.group(1).strip().strip('"')


def is_secretary_prompt(text: str) -> bool:
    return bool(re.search(r"(?im)^\s*Worker agent:\s*secretary-(flash|pro)\s*$", text))


def validate_secretary_artifact_paths(text: str, errors: list[str]) -> None:
    stable_paths = (
        "logs/SECRETARY.md",
        ".signals/secretary.json",
        "logs/NEXT_WORKER_PROMPT.md",
    )
    for path in stable_paths:
        if path in text:
            errors.append(
                "secretary prompt must use unique per-run artifact paths, not stable path: " + path
            )


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
    task_type = worker_type(text)
    if classification == "inconclusive" and task_type not in INCONCLUSIVE_ALLOWED_WORKER_TYPES:
        errors.append("inconclusive SDK/custom decision blocks implementation launch")
        return
    for field in SDK_BASELINE_REQUIRED_FIELDS:
        if field not in block:
            errors.append(f"SDK/custom decision missing required field: {field}")


def validate_canonical_worker_route(text: str, errors: list[str]) -> None:
    task_type = worker_type(text)
    if not task_type or task_type not in CANONICAL_WORKER_ROUTES:
        return
    expected_agent, expected_model = CANONICAL_WORKER_ROUTES[task_type]
    actual_agent = worker_field(text, "agent")
    actual_model = worker_field(text, "model")
    if (actual_agent, actual_model) == (expected_agent, expected_model):
        return
    if ROUTE_OVERRIDE_MARKER in text:
        return
    errors.append(
        "non-canonical worker route for "
        f"{task_type}: expected Worker agent {expected_agent} with model {expected_model}; "
        f"got agent {actual_agent or '<missing>'} with model {actual_model or '<missing>'}. "
        f"Use {ROUTE_OVERRIDE_MARKER} only for an explicit user-approved override."
    )


def validate_secretary_route(text: str, errors: list[str]) -> None:
    actual_agent = worker_field(text, "agent")
    if actual_agent not in SECRETARY_AGENT_MODELS:
        return
    actual_model = worker_field(text, "model")
    expected_model = SECRETARY_AGENT_MODELS[actual_agent]
    if actual_model == expected_model:
        return
    errors.append(
        "non-canonical secretary route: "
        f"expected Worker agent {actual_agent} with model {expected_model}; "
        f"got model {actual_model or '<missing>'}."
    )


def line_value(text: str, label: str) -> str | None:
    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", text)
    return match.group(1).strip() if match else None


def block_value(text: str, label: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(rf"(?i)^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        values = [match.group(1).strip()]
        for following in lines[index + 1 :]:
            if re.match(r"^\s*#{1,6}\s+", following):
                break
            if re.match(r"^\s*[A-Z][A-Za-z ]+\s*:", following):
                break
            if not following.strip():
                break
            if re.match(r"^\s*(-|\*|\d+\.)\s+", following) or following.startswith((" ", "\t")):
                values.append(following.strip())
                continue
            break
        return "\n".join(value for value in values if value)
    return None


def block_has_literal(text: str, label: str, literal: str) -> bool:
    block = block_value(text, label)
    if block is None:
        return False
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(literal)}(?![A-Za-z0-9_])", block) is not None


_CONTENT_SAFETY_METADATA_PATTERN = re.compile(
    r"(?im)^\s*(WORKER_NAME|REPORT_FILE|Worker type|Worker agent|Worker model|SWARM_CONTRACT):\s*"
)

_CONTENT_SAFETY_WAKEUP_PATTERN = re.compile(r"(?im)^\s*\[(DONE|FAILED|BLOCKED)\]\s+")

_CONTENT_SAFETY_TMUX_PATTERN = re.compile(r"(?im)^\s*tmux\s+send-keys\b")

_CONTENT_SAFETY_SECTION_HEADER_PATTERN = re.compile(
    r"(?im)^\s*##\s+(ROLE|TASK|REQUIRED\s*SKILLS|ANTI-REGRESSION\s*CONTRACT|FINISH\s*CONTRACT)"
)


def _find_task_section_range(text: str) -> tuple[int, int] | None:
    """Return (start, end) character offsets of the ## Task descriptive section.

    Returns None if ## Task heading is not found. The end offset is determined
    by the next structural field (Required Superpowers:, Forbidden
    Superpowers:, ## Required Skills, etc.) or end of text.
    """
    task_heading = re.search(r"(?im)^\s*##\s+Task\s*$", text)
    if not task_heading:
        return None

    start = task_heading.end()
    remaining = text[start:]

    terminator_pattern = re.compile(
        r"(?im)^\s*("
        r"Required Superpowers:|Forbidden Superpowers:|Finish Report Must Include:|"
        r"SDK/custom decision:|## RESOLVED REQUIRED SKILL|## Validation|"
        r"## Wake-Up|## Required Report Fields|"
        r"ANTI-REGRESSION CONTRACT)"
    )
    terminator_match = terminator_pattern.search(remaining)
    end = start + terminator_match.start() if terminator_match else len(text)

    return (start, end)


def validate_content_safety(text: str) -> list[str]:
    """Check the untrusted ## Task body for prompt-injection patterns.

    Returns warnings (not hard errors). The orchestrator should acknowledge
    warnings but the prompt is not blocked.
    """
    warnings: list[str] = []
    task_range = _find_task_section_range(text)
    if task_range is None:
        return warnings

    start, end = task_range
    task_body = text[start:end]

    for match in _CONTENT_SAFETY_METADATA_PATTERN.finditer(task_body):
        field = match.group(1)
        warnings.append(
            f"content_safety warning: metadata field '{field}' appears "
            "in untrusted task body — possible prompt injection"
        )

    if _CONTENT_SAFETY_WAKEUP_PATTERN.search(task_body):
        warnings.append(
            "content_safety warning: wake-up status line [DONE|FAILED|BLOCKED] "
            "appears in untrusted task body — possible prompt injection"
        )

    if _CONTENT_SAFETY_TMUX_PATTERN.search(task_body):
        warnings.append(
            "content_safety warning: 'tmux send-keys' appears "
            "in untrusted task body — possible command injection"
        )

    if _CONTENT_SAFETY_SECTION_HEADER_PATTERN.search(task_body):
        warnings.append(
            "content_safety warning: markdown section heading (## ROLE|TASK|etc.) "
            "appears in untrusted task body — possible section injection"
        )

    return warnings


def validate_superpowers_policy(text: str, errors: list[str]) -> None:
    task_type = worker_type(text)
    required = block_value(text, "Required Superpowers")
    skipped = block_value(text, "Skipped Superpowers")

    if not task_type:
        errors.append("missing Worker type")
    elif task_type not in KNOWN_WORKER_TYPES:
        errors.append(f"unknown Worker type: {task_type}")

    if required:
        for forbidden in FORBIDDEN_WORKER_SUPERPOWERS:
            if forbidden in required:
                errors.append(
                    f"forbidden worker Superpowers skill in Required Superpowers: {forbidden}"
                )

    if task_type in CODE_CHANGING_WORKER_TYPES:
        if required is None:
            errors.append("code-changing worker prompt requires Required Superpowers")
        else:
            if "superpowers:executing-plans" not in required:
                errors.append("code-changing worker prompt requires superpowers:executing-plans")
            if "superpowers:test-driven-development" not in required:
                errors.append(
                    "code-changing worker prompt requires superpowers:test-driven-development"
                )
            if "superpowers:verification-before-completion" not in required:
                errors.append(
                    "code-changing worker prompt requires superpowers:verification-before-completion"
                )

        if line_value(text, "Forbidden Superpowers") is None:
            errors.append("code-changing worker prompt requires Forbidden Superpowers")

        for field in FINISH_REPORT_SUPERPOWERS_FIELDS:
            if not block_has_literal(text, "Finish Report Must Include", field):
                errors.append(f"code-changing worker prompt finish report must include {field}")

    if required and required.lower() == "none":
        if skipped is None:
            errors.append("Skipped Superpowers must explain why Required Superpowers is none")
        elif "superpowers:test-driven-development" in skipped and " - " not in skipped:
            errors.append(
                "Skipped Superpowers must include a reason for skipping test-driven-development"
            )


def validate(text: str, *, contract: str) -> list[str]:
    errors: list[str] = []

    for pattern in HARD_CODED_PANE_PATTERNS:
        match = pattern.search(text)
        if match:
            errors.append(
                "hard-coded tmux pane target is forbidden in prompt sources; "
                "use {{ORCH_TARGET}} for wake-up and let the launcher resolve it: " + match.group(0)
            )

    if re.search(r"(?im)^\s*Worker variant:\s*empty\s*$", text):
        errors.append('Worker variant must be "" or "empty string", not literal "empty"')
    if re.search(r"(?im)^\s*variant:\s*empty\s*$", text):
        errors.append('variant must be "" or "empty string", not literal "empty"')
    if any(pattern.search(text) for pattern in CJ_SUBMIT_PATTERNS):
        errors.append("prompt source must not use C-j as submit; Kiro TUI treats Ctrl+J as newline")
    if any(pattern.search(text) for pattern in ENTER_SUBMIT_PATTERNS):
        errors.append("prompt source must not use Enter as submit; Kiro TUI requires isolated C-m")

    docs_policy_match = re.search(r"(?im)^\s*Docs lookup policy:\s*([a-z0-9_]+)", text)
    docs_policy = docs_policy_match.group(1) if docs_policy_match else None
    if docs_policy and docs_policy not in DOCS_POLICIES:
        errors.append(f"unknown docs lookup policy: {docs_policy}")

    if docs_policy == "forbidden":
        if "## STEP 0 POLICY GATE" not in text:
            errors.append("forbidden docs policy requires ## STEP 0 POLICY GATE")
        if "POLICY_ACK docs_lookup=forbidden local_only=true" not in text:
            errors.append(
                "forbidden docs policy requires POLICY_ACK docs_lookup=forbidden local_only=true"
            )

    if docs_policy == "context7_required":
        if "Use Context7 only for" not in text:
            errors.append(
                "context7_required requires a scoped 'Use Context7 only for <library>/<question>' instruction"
            )
        if "Do not use web search/Exa" not in text:
            errors.append("context7_required requires 'Do not use web search/Exa'")
        if "sdk_docs_evidence" not in text:
            errors.append("context7_required requires sdk_docs_evidence recording")

    if contract == "markdown":
        if "WORKER_NAME" not in text:
            errors.append("markdown prompt must define WORKER_NAME")
        if "REPORT_FILE" not in text:
            errors.append("markdown prompt must define REPORT_FILE")
        if not re.search(r"REPORT_FILE=.*logs/.*\.md", text):
            errors.append("markdown prompt must assign REPORT_FILE to a logs/*.md path")
        wakeup_ok = any(
            re.search(r"\[(DONE|FAILED|BLOCKED)\]", line)
            and "WORKER_NAME" in line
            and "REPORT_FILE" in line
            for line in text.splitlines()
        )
        if not wakeup_ok:
            errors.append(
                "markdown prompt must show a plain [DONE|FAILED|BLOCKED] wake-up line with WORKER_NAME and REPORT_FILE"
            )
        if any(pattern.search(text) for pattern in RAW_WAKEUP_PATTERNS):
            errors.append("markdown prompt wake-up must target $ORCH_TARGET, not $ORCH_PANE")
        if any(pattern.search(text) for pattern in PASTE_BUFFER_WINDOW_WAKEUP_PATTERNS):
            errors.append(
                'markdown prompt wake-up must use `tmux send-keys -t "$ORCH_TARGET" -l ...`, not paste-buffer'
            )
        if not any(pattern.search(text) for pattern in WINDOW_WAKEUP_PATTERNS):
            errors.append(
                'markdown prompt must execute wake-up against $ORCH_TARGET with `tmux send-keys -t "$ORCH_TARGET" -l ...`'
            )
        if not any(pattern.search(text) for pattern in CM_SUBMIT_PATTERNS):
            errors.append("markdown prompt must submit wake-up with isolated C-m")
        if "SWARM_CONTRACT=strict_json" in text:
            errors.append("markdown prompt must not opt into SWARM_CONTRACT=strict_json")

    if contract in {"full", "strict_json"}:
        if any(pattern.search(text) for pattern in RAW_WAKEUP_PATTERNS + FULL_RAW_WAKEUP_PATTERNS):
            errors.append(
                "raw tmux wake-up snippets are forbidden in new full worker prompts; "
                'use tmux send-keys -t "$ORCH_TARGET" after writing SIGNAL_FILE'
            )

        required_markers = (
            "## WORKER MODEL",
            "## REQUIRED KIRO SKILLS",
            "## WORKER PROMPT PAYLOAD",
            "## VERIFICATION BUDGET",
            "## FINISH CONTRACT",
        )
        for marker in required_markers:
            if marker not in text:
                errors.append(f"full prompt missing required section: {marker}")

        if not has_any(text, ("{{ORCH_PANE}}", "__ORCH_PANE__")):
            errors.append("full prompt source must include {{ORCH_PANE}} or __ORCH_PANE__")
        if not has_any(text, ("{{ORCH_TARGET}}", "__ORCH_TARGET__")):
            errors.append("full prompt source must include {{ORCH_TARGET}} or __ORCH_TARGET__")
        if not has_any(text, ("{{ORCH_WINDOW_ID}}", "__ORCH_WINDOW_ID__")):
            errors.append(
                "full prompt source must include {{ORCH_WINDOW_ID}} or __ORCH_WINDOW_ID__"
            )
        if not has_any(text, ("{{ORCH_WINDOW_NAME}}", "__ORCH_WINDOW_NAME__")):
            errors.append(
                "full prompt source must include {{ORCH_WINDOW_NAME}} or __ORCH_WINDOW_NAME__"
            )
        if not has_any(text, ("{{ORCH_SESSION_NAME}}", "__ORCH_SESSION_NAME__")):
            errors.append(
                "full prompt source must include {{ORCH_SESSION_NAME}} or __ORCH_SESSION_NAME__"
            )
        if not has_any(text, ("{{ORCH_WINDOW_INDEX}}", "__ORCH_WINDOW_INDEX__")):
            errors.append(
                "full prompt source must include {{ORCH_WINDOW_INDEX}} or __ORCH_WINDOW_INDEX__"
            )

        if "Signal path:" not in text and "SIGNAL_FILE" not in text:
            errors.append("full prompt must state Signal path or SIGNAL_FILE")
        if "verification_budget:" not in text:
            errors.append("full prompt must state verification_budget")
        if "Docs lookup policy:" not in text:
            errors.append("full prompt must state Docs lookup policy")
        if "SDK/custom decision:" not in text and "sdk_native_check:not_applicable" not in text:
            errors.append(
                "full prompt must state SDK/custom decision or sdk_native_check:not_applicable"
            )

    if is_secretary_prompt(text):
        if "## SECRETARY PROMPT PAYLOAD" not in text:
            errors.append("secretary prompt missing ## SECRETARY PROMPT PAYLOAD")
        for marker in (
            "Task kind:",
            "Expected artifacts:",
            "Recommended route fields:",
            "Confidence policy:",
        ):
            if marker not in text:
                errors.append(f"secretary prompt missing {marker}")
        if not has_any(text, ("{{ORCH_TARGET}}", "__ORCH_TARGET__")):
            errors.append("secretary prompt source must include {{ORCH_TARGET}} or __ORCH_TARGET__")
        if contract in {"full", "strict_json"} and "SIGNAL_FILE" not in text:
            errors.append("secretary prompt must state SIGNAL_FILE")
        validate_secretary_artifact_paths(text, errors)
        validate_secretary_route(text, errors)

    validate_sdk_decision(text, errors)
    validate_canonical_worker_route(text, errors)
    validate_superpowers_policy(text, errors)

    # Content-safety: only fires when a ## Task section exists.
    # Warnings are informational; the prompt is not blocked.
    errors.extend(validate_content_safety(text))

    return errors


def main() -> int:
    args = parse_args()
    try:
        text = args.prompt.read_text(encoding="utf-8")
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    errors = validate(text, contract=args.contract)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
