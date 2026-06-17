#!/usr/bin/env python3
"""LEGACY — strict_json mode only. Validate Kiro swarm worker signal JSON.

Markdown-first workers do not use this validator. It runs only when
``KIRO_STRICT_REPORT=1`` is set (legacy / explicit strict machine handoff);
otherwise it is a no-op that exits 0. See
``.kiro/skills/shared/strict-json-policy.md`` (#2305 P3).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from route_constants import RECOMMENDED_ROUTE_MODELS, SECRETARY_AGENT_MODELS  # noqa: E402


STATUSES = {"done", "failed", "blocked"}
COMMAND_STATUSES = {"passed", "failed", "skipped", "timeout"}
VERIFICATION_BUDGETS = {"focused_only", "broad_owner", "runtime_owner"}
PYTEST_OPTIONS_WITH_VALUE = {
    "-k",
    "-m",
    "-n",
    "--capture",
    "--cov",
    "--cov-report",
    "--dist",
    "--ignore",
    "--ignore-glob",
    "--junitxml",
    "--maxfail",
    "--rootdir",
    "--tb",
}
REVIEW_DECISIONS = {"not_reviewed", "clean", "blockers", "fixed", "escalate"}
SDK_CHECKS = {"not_applicable", "native_used", "custom_justified", "blocker"}
STATUS_TO_WAKEUP_TAG = {"done": "DONE", "failed": "FAILED", "blocked": "BLOCKED"}
INCONCLUSIVE_ALLOWED_WORKER_TYPES = {
    "research",
    "docs-update",
    "docs-only",
    "artifact-check",
    "issue-audit",
    "dependency-verify",
}
SECRETARY_TASK_KINDS = {
    "queue_triage",
    "issue_triage",
    "pr_triage",
    "decomposition",
    "sdk_baseline",
    "artifact_check",
    "prompt_draft",
    "session_forensics",
}
SECRETARY_CONFIDENCE = {"low", "medium", "high"}
SECRETARY_NEXT_ACTIONS = {"launch_next_worker", "ask_user", "escalate", "finish"}
SECRETARY_NEXT_WORKER_TYPES = {
    "secretary-pro",
    "implementation",
    "pr-review",
    "review-fix",
    "local-verification",
    "blocked",
    "finish",
}
ARRAY_FIELDS = {
    "changed_files",
    "pr_files",
    "reserved_files",
    "required_skills",
    "skills_loaded",
    "findings",
    "blockers_found",
    "blockers_resolved",
    "new_bugs",
    "bug_disposition_recommendations",
    "autofix_commits",
    "sdk_docs_evidence",
    "commands",
    "superpowers_used",
    "skipped_superpowers",
    "tests_run",
    "verification_evidence",
}
STRING_FIELDS = {
    "worker",
    "branch",
    "head_ref",
    "head_sha",
    "pr",
    "base",
    "agent",
    "model",
    "variant",
    "prompt_sha256",
    "custom_justification",
    "pushed_sha",
    "summary",
    "next_action",
    "ts",
}
OPTIONAL_STRING_FIELDS = {
    "block_reason",
    "needed_from_orchestrator",
}
BOOL_FIELDS = {"worktree_clean", "pushed"}
QUICK_ARRAY_FIELDS = {
    "changed_files",
    "required_skills",
    "skills_loaded",
    "commands",
    "superpowers_used",
    "skipped_superpowers",
    "tests_run",
    "verification_evidence",
}
QUICK_STRING_FIELDS = {
    "worker",
    "mode",
    "runner",
    "agent",
    "model",
    "variant",
    "branch",
    "summary",
    "next_action",
    "ts",
}
REGISTRY_COMPARE_FIELDS = ("base", "branch", "prompt_sha256", "required_skills", "reserved_files")
REGISTRY_METADATA_UPDATE_STATUSES = {
    "launch_metadata_prompt_sha_corrected",
}
LEGACY_TOP_LEVEL_FIELDS = {
    "files_changed": "files_changed is legacy; use changed_files",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_registry_worker(path: Path, worker: str) -> dict[str, Any] | None:
    merged: dict[str, Any] | None = None
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("worker") != worker:
                continue
            previous = merged or {}
            next_row = {**previous, **row}
            if row.get("status") in REGISTRY_METADATA_UPDATE_STATUSES and "status" in previous:
                next_row["status"] = previous["status"]
            merged = next_row
    return merged


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_legacy_fields(data: dict[str, Any], errors: list[str]) -> None:
    for field, message in LEGACY_TOP_LEVEL_FIELDS.items():
        if field in data:
            fail(errors, message)


def same_signal_path(recorded: object, expected: Path) -> bool:
    if not isinstance(recorded, str) or not recorded:
        return False
    if recorded == str(expected):
        return True
    recorded_path = Path(recorded)
    if not recorded_path.is_absolute():
        candidate = expected.parent.parent / recorded_path
        try:
            if candidate.resolve() == expected.resolve():
                return True
        except OSError:
            pass
    try:
        return recorded_path.resolve() == expected.resolve()
    except OSError:
        return False


def validate_wakeup_receipt(signal_path: Path, data: dict[str, Any], errors: list[str]) -> None:
    worker = data.get("worker")
    status = data.get("status")
    if not isinstance(worker, str) or not worker:
        fail(errors, "wakeup receipt cannot be checked without signal worker")
        return
    if status not in STATUS_TO_WAKEUP_TAG:
        fail(errors, "wakeup receipt cannot be checked without valid signal status")
        return

    receipt_path = signal_path.parent / f"wakeup-{worker}.json"
    try:
        receipt = load_json(receipt_path)
    except Exception as exc:
        fail(errors, f"missing or invalid wake-up receipt {receipt_path}: {exc}")
        return

    if receipt.get("worker") != worker:
        fail(errors, "wake-up receipt worker mismatch")
    if receipt.get("status") != status:
        fail(errors, "wake-up receipt status mismatch")
    if receipt.get("tag") != STATUS_TO_WAKEUP_TAG[status]:
        fail(errors, "wake-up receipt tag mismatch")
    if not same_signal_path(receipt.get("signal_file"), signal_path):
        fail(errors, "wake-up receipt signal_file mismatch")
    if not receipt.get("sent_at"):
        fail(errors, "wake-up receipt missing sent_at")


def validate_commands(data: dict[str, Any], errors: list[str]) -> None:
    for index, command in enumerate(data.get("commands") or []):
        if not isinstance(command, dict):
            fail(errors, f"commands[{index}] must be an object")
            continue
        for key in ("cmd", "exit", "status", "required", "summary"):
            if key not in command:
                fail(errors, f"commands[{index}] missing {key}")
        status = command.get("status")
        exit_code = command.get("exit")
        required = command.get("required")
        if status not in COMMAND_STATUSES:
            fail(errors, f"commands[{index}].status must be one of passed|failed|skipped|timeout")
        if "required" in command and not isinstance(required, bool):
            fail(errors, f"commands[{index}].required must be a boolean")
        if status in {"passed", "failed", "timeout"} and not isinstance(exit_code, int):
            fail(errors, f"commands[{index}].exit must be an integer for passed|failed|timeout")
        if status == "skipped" and exit_code is not None:
            fail(errors, f"commands[{index}].exit must be null for skipped")
        if status == "skipped" and required is True:
            fail(errors, f"commands[{index}] required command cannot be skipped")


def command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def command_has_pytest(command: str) -> bool:
    return "pytest" in command_tokens(command)


def pytest_positional_targets(command: str) -> list[str]:
    tokens = command_tokens(command)
    if "pytest" not in tokens:
        return []
    pytest_index = tokens.index("pytest")
    targets: list[str] = []
    skip_next = False
    for token in tokens[pytest_index + 1 :]:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            option = token.split("=", 1)[0]
            skip_next = "=" not in token and option in PYTEST_OPTIONS_WITH_VALUE
            continue
        targets.append(token)
    return targets


def pytest_target_is_focused(target: str) -> bool:
    return "::" in target or target.endswith(".py")


def command_has_focused_pytest_target(command: str) -> bool:
    targets = pytest_positional_targets(command)
    return bool(targets) and all(pytest_target_is_focused(target) for target in targets)


def is_runtime_command(command: str) -> bool:
    return bool(
        re.search(
            r"(?i)(^|[;&|]\s*)docker\s+compose\s+(?:up|build|restart)\b",
            command,
        )
    )


def is_broad_command(command: str) -> bool:
    if re.search(r"(?i)(^|[;&|]\s*)make\s+(?:test|test-unit)\b", command):
        return True
    tokens = command_tokens(command)
    if "pytest" not in tokens:
        return False
    if re.search(r"(?i)(^|[;&|]\s*)pytest\s*(?:$|[;&|])", command):
        return True
    if re.search(r"(?i)(^|[;&|]\s*)(?:uv\s+run\s+)?pytest(?:\s+-q)?\s*$", command):
        return True
    for index, token in enumerate(tokens):
        if token == "-n" and index + 1 < len(tokens) and tokens[index + 1] == "auto":  # nosec B105
            return True
        if token == "-n=auto":  # nosec B105
            return True
        if token == "--dist=worksteal":  # nosec B105
            return True
        if token == "--dist" and index + 1 < len(tokens) and tokens[index + 1] == "worksteal":  # nosec B105
            return True
    return command_has_pytest(command) and not command_has_focused_pytest_target(command)


def validate_verification_budget(data: dict[str, Any], errors: list[str]) -> None:
    budget = data.get("verification_budget", "focused_only")
    if not isinstance(budget, str) or budget not in VERIFICATION_BUDGETS:
        fail(errors, "verification_budget must be one of focused_only|broad_owner|runtime_owner")
        budget = "focused_only"
    for index, command in enumerate(data.get("commands") or []):
        if not isinstance(command, dict) or not isinstance(command.get("cmd"), str):
            continue
        cmd = command["cmd"]
        if is_runtime_command(cmd) and budget != "runtime_owner":
            fail(
                errors,
                f"commands[{index}] runtime verification command requires verification_budget:runtime_owner",
            )
        if is_broad_command(cmd) and budget != "broad_owner":
            fail(
                errors,
                f"commands[{index}] broad verification command requires verification_budget:broad_owner",
            )


def has_focused_command_evidence(data: dict[str, Any]) -> bool:
    for command in data.get("commands") or []:
        if not isinstance(command, dict):
            continue
        if command.get("status") != "passed" or command.get("required") is not True:
            continue
        cmd = str(command.get("cmd", ""))
        if command_has_focused_pytest_target(cmd):
            return True
        haystack = f"{cmd} {command.get('summary', '')}".lower()
        if "focused" in haystack:
            return True
    return False


def has_required_passed_command(data: dict[str, Any]) -> bool:
    for command in data.get("commands") or []:
        if not isinstance(command, dict):
            continue
        if command.get("required") is True and command.get("status") == "passed":
            return True
    return False


def validate_code_producing_evidence(data: dict[str, Any], errors: list[str]) -> None:
    tests_run = data.get("tests_run")
    if not isinstance(tests_run, list) or not tests_run:
        fail(errors, "tests_run must be non-empty for code-producing done")
        tests_run = []
    verification_evidence = data.get("verification_evidence")
    if not isinstance(verification_evidence, list) or not verification_evidence:
        fail(errors, "verification_evidence must be non-empty for code-producing done")
    if not has_required_passed_command(data):
        fail(errors, "code-producing done requires at least one required passed command")

    command_values = {
        command.get("cmd")
        for command in data.get("commands") or []
        if isinstance(command, dict) and isinstance(command.get("cmd"), str)
    }
    if tests_run and any(
        not isinstance(item, str) or item not in command_values for item in tests_run
    ):
        fail(errors, "tests_run entries must match commands[].cmd evidence")


def validate_decision_consistency(data: dict[str, Any], errors: list[str]) -> None:
    decision = data.get("review_decision")
    if decision == "clean" and data.get("blockers_found"):
        fail(errors, "review_decision clean requires no blockers_found")
    if decision == "fixed":
        if not data.get("blockers_found"):
            fail(errors, "review_decision fixed requires blockers_found")
        if not data.get("blockers_resolved"):
            fail(errors, "review_decision fixed requires blockers_resolved")
        if not has_focused_command_evidence(data):
            fail(errors, "review_decision fixed requires focused command evidence")


def validate_blocked_sdk_baseline(data: dict[str, Any], errors: list[str]) -> None:
    if data.get("status") != "blocked":
        return
    if data.get("block_reason") != "missing_or_insufficient_sdk_baseline":
        return
    if data.get("sdk_native_check") != "blocker":
        fail(errors, "missing_or_insufficient_sdk_baseline requires sdk_native_check:blocker")
    needed = data.get("needed_from_orchestrator")
    if (
        not isinstance(needed, str)
        or "sdk/custom decision" not in needed
        or "required_shape" not in needed
    ):
        fail(errors, "needed_from_orchestrator must describe required SDK baseline")


def load_prompt_baseline(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    worker_type_match = re.search(r"(?im)^\s*Worker type:\s*([a-z0-9_-]+)", text)
    worker_type = worker_type_match.group(1) if worker_type_match else ""
    marker = "SDK/custom decision:"
    start = text.find(marker)
    if start < 0:
        return {"worker_type": worker_type} if worker_type else {}
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
        "worker_type": worker_type,
        "docs_used": docs_used,
        "expected_sdk_check": expected_sdk_check,
        "expected_custom": expected_custom,
        "expected_docs_evidence": expected_docs_evidence,
    }


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
        if baseline.get("worker_type") not in INCONCLUSIVE_ALLOWED_WORKER_TYPES:
            fail(errors, "inconclusive SDK/custom decision blocks implementation acceptance")
        if sdk_check != "blocker":
            fail(errors, "inconclusive baseline requires sdk_native_check:blocker")
    if classification == "sdk_sensitive":
        if sdk_check not in {"native_used", "custom_justified", "blocker"}:
            fail(
                errors,
                "sdk_sensitive baseline requires sdk_native_check native_used|custom_justified|blocker",
            )
        expected_sdk_check = baseline.get("expected_sdk_check")
        if (
            isinstance(expected_sdk_check, str)
            and expected_sdk_check
            and "|" not in expected_sdk_check
            and sdk_check != expected_sdk_check
        ):
            fail(
                errors,
                f"sdk_native_check must match prompt done_json_expectation:{expected_sdk_check}",
            )
        if baseline.get("docs_used") and not data.get("sdk_docs_evidence"):
            fail(errors, "Context7/official docs baseline requires sdk_docs_evidence")
    if classification == "not_applicable":
        if sdk_check != "not_applicable":
            fail(errors, "not_applicable baseline requires sdk_native_check:not_applicable")
        if data.get("custom_justification"):
            fail(errors, "not_applicable baseline requires empty custom_justification")
    if sdk_check == "custom_justified" and not data.get("custom_justification"):
        fail(errors, "custom_justified requires custom_justification")


def validate_common(data: dict[str, Any], errors: list[str]) -> None:
    validate_legacy_fields(data, errors)
    if data.get("status") not in STATUSES:
        fail(errors, "status must be one of done|failed|blocked")
    if data.get("runner") != "kiro":
        fail(errors, "runner must be kiro")
    if data.get("review_decision") not in REVIEW_DECISIONS:
        fail(errors, "review_decision is invalid")
    if data.get("sdk_native_check") not in SDK_CHECKS:
        fail(errors, "sdk_native_check is invalid")
    if not isinstance(data.get("issue"), int) and data.get("issue") is not None:
        fail(errors, "issue must be int or null")

    for field in STRING_FIELDS:
        if not isinstance(data.get(field), str):
            fail(errors, f"{field} must be a string")
    if not data.get("prompt_sha256"):
        fail(errors, "prompt_sha256 must be non-empty")

    for field in OPTIONAL_STRING_FIELDS:
        if field in data and not isinstance(data.get(field), str):
            fail(errors, f"{field} must be a string")

    for field in BOOL_FIELDS:
        if not isinstance(data.get(field), bool):
            fail(errors, f"{field} must be a boolean")

    for field in ARRAY_FIELDS:
        if not isinstance(data.get(field), list):
            fail(errors, f"{field} must be an array")

    docs = data.get("docs_impact")
    if not isinstance(docs, dict):
        fail(errors, "docs_impact must be an object")
    else:
        if docs.get("checked") is not True:
            fail(errors, "docs_impact.checked must be true")
        if not isinstance(docs.get("used_docs"), list):
            fail(errors, "docs_impact.used_docs must be an array")
        if not isinstance(docs.get("impacted"), bool):
            fail(errors, "docs_impact.impacted must be a boolean")
        if not isinstance(docs.get("proposals"), list):
            fail(errors, "docs_impact.proposals must be an array")

    validate_commands(data, errors)
    validate_verification_budget(data, errors)

    required = data.get("required_skills") or []
    loaded = set(data.get("skills_loaded") or [])
    for skill in required:
        if skill not in loaded:
            fail(errors, f"skills_loaded must include required skill: {skill}")
    validate_blocked_sdk_baseline(data, errors)
    validate_decision_consistency(data, errors)


def validate_quick(data: dict[str, Any], errors: list[str]) -> None:
    validate_legacy_fields(data, errors)
    if data.get("status") not in STATUSES:
        fail(errors, "status must be one of done|failed|blocked")
    if data.get("mode") != "quick":
        fail(errors, "mode must be quick")
    if data.get("runner") != "kiro":
        fail(errors, "runner must be kiro")

    for field in QUICK_STRING_FIELDS:
        if not isinstance(data.get(field), str):
            fail(errors, f"{field} must be a string")

    for field in QUICK_ARRAY_FIELDS:
        if not isinstance(data.get(field), list):
            fail(errors, f"{field} must be an array")

    validate_commands(data, errors)
    validate_verification_budget(data, errors)

    required = data.get("required_skills") or []
    loaded = set(data.get("skills_loaded") or [])
    for skill in required:
        if skill not in loaded:
            fail(errors, f"skills_loaded must include required skill: {skill}")


def validate_secretary(data: dict[str, Any], errors: list[str]) -> None:
    validate_legacy_fields(data, errors)
    if data.get("status") not in STATUSES:
        fail(errors, "status must be one of done|failed|blocked")
    if data.get("mode") != "secretary":
        fail(errors, "mode must be secretary")
    if data.get("runner") != "kiro":
        fail(errors, "runner must be kiro")
    for field in (
        "worker",
        "agent",
        "model",
        "variant",
        "task_kind",
        "confidence",
        "summary",
        "next_action",
        "ts",
    ):
        if not isinstance(data.get(field), str):
            fail(errors, f"{field} must be a string")
    if data.get("agent") not in {"secretary-flash", "secretary-pro"}:
        fail(errors, "agent must be secretary-flash|secretary-pro")
    expected_model = SECRETARY_AGENT_MODELS.get(data.get("agent"))
    if expected_model and data.get("model") != expected_model:
        fail(errors, f"model must be {expected_model} for agent {data.get('agent')}")
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
        expected_route_model = RECOMMENDED_ROUTE_MODELS.get(route.get("next_worker_type"))
        if expected_route_model and route.get("model") != expected_route_model:
            fail(
                errors,
                "recommended_route.model must be "
                f"{expected_route_model} for next_worker_type {route.get('next_worker_type')}",
            )
    artifact_paths = data.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        fail(errors, "artifact_paths must be an object")
    else:
        markdown_path = artifact_paths.get("markdown")
        if not isinstance(markdown_path, str):
            fail(errors, "artifact_paths.markdown must be a string")
        elif markdown_path == "logs/SECRETARY.md":
            fail(errors, "artifact_paths.markdown must be a unique per-run path")
        prompt_draft = artifact_paths.get("prompt_draft", "")
        if prompt_draft is not None and not isinstance(prompt_draft, str):
            fail(errors, "artifact_paths.prompt_draft must be a string")
        elif prompt_draft == "logs/NEXT_WORKER_PROMPT.md":
            fail(errors, "artifact_paths.prompt_draft must be a unique per-run path")
    validate_commands(data, errors)


def validate_launch(
    data: dict[str, Any],
    launch: dict[str, Any],
    errors: list[str],
    *,
    quick: bool = False,
) -> None:
    required_fields = (
        "worker",
        "runner",
        "agent",
        "model",
        "variant",
        "required_skills",
        "route_check_confirmed",
        "route_check_nonce",
    )
    if not quick:
        required_fields += ("prompt_sha256",)
    for field in required_fields:
        if field not in launch:
            fail(errors, f"launch metadata missing {field}")
    for field in ("worker", "runner", "agent", "model", "variant"):
        if field in launch and not isinstance(launch.get(field), str):
            fail(errors, f"launch metadata {field} must be a string")
    if "prompt_sha256" in launch and not isinstance(launch.get("prompt_sha256"), str):
        fail(errors, "launch metadata prompt_sha256 must be a string")
    if "required_skills" in launch and not isinstance(launch.get("required_skills"), list):
        fail(errors, "launch metadata required_skills must be an array")
    route_confirmed = launch.get("route_check_confirmed")
    route_nonce = launch.get("route_check_nonce")
    if "route_check_confirmed" in launch and route_confirmed not in {"0", "1"}:
        fail(errors, "launch metadata route_check_confirmed must be 0|1")
    if "route_check_nonce" in launch and not isinstance(route_nonce, str):
        fail(errors, "launch metadata route_check_nonce must be a string")
    if route_confirmed == "1" and not route_nonce:
        fail(errors, "launch metadata route_check_nonce required when route_check_confirmed=1")
    if route_nonce and route_confirmed != "1":
        fail(errors, "launch metadata route_check_nonce requires route_check_confirmed=1")

    fields = (
        ("worker", "runner", "agent", "model", "variant")
        if quick
        else (
            "worker",
            "runner",
            "agent",
            "model",
            "variant",
            "prompt_sha256",
        )
    )
    for field in fields:
        if field in launch and data.get(field) != launch.get(field):
            fail(errors, f"{field} differs from launch metadata")
    launch_required = launch.get("required_skills")
    if isinstance(launch_required, list) and data.get("required_skills") != launch_required:
        fail(errors, "required_skills differs from launch metadata")
    signal_budget = data.get("verification_budget", "focused_only")
    launch_budget = launch.get("verification_budget", "focused_only")
    if isinstance(signal_budget, str) and signal_budget in {"broad_owner", "runtime_owner"}:
        if "verification_budget" not in launch:
            fail(errors, f"verification_budget {signal_budget} requires matching launch metadata")
        elif signal_budget != launch_budget:
            fail(errors, "verification_budget differs from launch metadata")


def validate_role(role: str, data: dict[str, Any], errors: list[str]) -> None:
    if role in {"delivery", "review-fix"} and data.get("status") == "done":
        if data.get("worktree_clean") is not True:
            fail(errors, "worktree_clean must be true for code-producing roles")
        if not data.get("head_sha"):
            fail(errors, "head_sha must be non-empty for code-producing roles")
        validate_code_producing_evidence(data, errors)
        if data.get("pushed") is True:
            for field in ("pr", "pushed_sha"):
                if not data.get(field):
                    fail(errors, f"{field} must be non-empty when push is authorized")
            if (
                data.get("head_sha")
                and data.get("pushed_sha")
                and data.get("head_sha") != data.get("pushed_sha")
            ):
                fail(errors, "head_sha must match pushed_sha for pushed code-producing roles")

    if role == "pr-review":
        if data.get("pushed") is not False:
            fail(errors, "pushed must be false for read-only PR review")
        if data.get("changed_files") not in ([], None):
            fail(errors, "changed_files must be empty for read-only PR review")
        if data.get("pr_files") not in ([], None):
            fail(
                errors,
                "pr_files must be empty for read-only PR review; reviewed paths belong in findings, commands, summary, or evidence",
            )
        if data.get("blockers_resolved") not in ([], None):
            fail(errors, "blockers_resolved must be empty for read-only PR review")
        if data.get("autofix_commits") not in ([], None):
            fail(errors, "autofix_commits must be empty for read-only PR review")

    if role in {"artifact-check", "local-verification"} and data.get("pushed") is not False:
        fail(errors, "pushed must be false for artifact-check/local-verification")

    if (
        role == "review-fix"
        and data.get("status") == "done"
        and data.get("review_decision") == "clean"
    ):
        fail(errors, "review-fix done cannot use review_decision clean")


def signal_path_matches_registry(signal_path: Path, registry: dict[str, Any]) -> bool:
    registry_signal = registry.get("signal_file")
    if not isinstance(registry_signal, str) or not registry_signal:
        return True
    if str(signal_path) == registry_signal:
        return True
    # Archived feedback copies move the JSON out of the original worktree. In
    # that case the basename is the stable signal identity; semantic registry
    # fields still catch the important drift.
    return signal_path.name == Path(registry_signal).name


def validate_registry(
    data: dict[str, Any],
    registry: dict[str, Any] | None,
    signal_path: Path,
    worker: str,
    errors: list[str],
) -> None:
    if registry is None:
        fail(errors, f"worker not found in registry: {worker}")
        return
    if data.get("worker") != worker:
        fail(errors, "worker differs from registry audit target")
    for field in REGISTRY_COMPARE_FIELDS:
        if field in registry and data.get(field) != registry.get(field):
            fail(errors, f"{field} differs from registry")
    if registry.get("signal_file") and not signal_path_matches_registry(signal_path, registry):
        fail(errors, "signal_file differs from registry")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--role",
        required=True,
        choices=[
            "delivery",
            "pr-review",
            "review-fix",
            "artifact-check",
            "local-verification",
            "quick",
            "secretary",
        ],
    )
    parser.add_argument("--signal", required=True, type=Path)
    parser.add_argument("--launch", type=Path)
    parser.add_argument("--prompt", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--worker")
    parser.add_argument(
        "--require-wakeup-receipt",
        action="store_true",
        help="Post-wake acceptance mode: require sibling wakeup-<worker>.json receipt.",
    )
    args = parser.parse_args()

    if os.getenv("KIRO_STRICT_REPORT") != "1":
        print(
            "SKIP: legacy strict_json validator (set KIRO_STRICT_REPORT=1 to enable); "
            "Markdown-first is the default path"
        )
        return 0

    if (args.registry is None) != (args.worker is None):
        print("--registry and --worker must be provided together", file=sys.stderr)
        return 2

    errors: list[str] = []
    try:
        signal = load_json(args.signal)
        launch = load_json(args.launch) if args.launch else None
        prompt_baseline = load_prompt_baseline(args.prompt) if args.prompt else {}
        registry = load_registry_worker(args.registry, args.worker) if args.registry else None
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.role == "quick":
        validate_quick(signal, errors)
        if launch is not None:
            validate_launch(signal, launch, errors, quick=True)
    elif args.role == "secretary":
        validate_secretary(signal, errors)
        if launch is not None:
            validate_launch(signal, launch, errors, quick=True)
    else:
        validate_common(signal, errors)
        if launch is not None:
            validate_launch(signal, launch, errors)
        validate_role(args.role, signal, errors)
        validate_prompt_sdk_baseline(signal, prompt_baseline, errors)

    if args.registry is not None:
        validate_registry(signal, registry, args.signal, args.worker, errors)
    if args.require_wakeup_receipt:
        validate_wakeup_receipt(args.signal, signal, errors)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
