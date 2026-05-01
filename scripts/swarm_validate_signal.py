#!/usr/bin/env python3
"""Validator for swarm worker DONE JSON signals.

Reads an active-worker registry JSONL and a worker signal JSON,
validates the signal against the registry entry, and exits with:
  0 = valid
  1 = validation errors
  2 = usage/file parse errors
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path


def load_registry(path: Path) -> dict[str, dict]:
    """Load worker registry from JSONL."""
    registry: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            worker = entry.get("worker")
            if worker:
                registry[worker] = entry
    return registry


def _match_reserved(file_path: str, reserved_patterns: list[str]) -> bool:
    """Check if file_path matches any reserved pattern (supports wildcards)."""
    return any(fnmatch.fnmatch(file_path, pattern) for pattern in reserved_patterns)


def validate_signal(entry: dict, signal: dict, signal_path: Path) -> list[str]:
    """Validate signal dict against registry entry.

    Returns a list of error strings prefixed with ``ERROR:``.
    Empty list means valid.
    """
    errors: list[str] = []

    # signal path mismatch
    registry_signal_file = Path(entry.get("signal_file", ""))
    try:
        if signal_path.resolve() != registry_signal_file.resolve():
            errors.append(f"ERROR: signal path mismatch: {signal_path} != {registry_signal_file}")
    except OSError:
        errors.append(f"ERROR: signal path mismatch: {signal_path} != {registry_signal_file}")

    # signal file outside registered worktree .signals/
    worktree = Path(entry.get("worktree", ""))
    expected_signals_dir = (worktree / ".signals").resolve()
    try:
        resolved_signal = signal_path.resolve()
        if not (
            resolved_signal == expected_signals_dir
            or expected_signals_dir in resolved_signal.parents
        ):
            errors.append(
                f"ERROR: signal file outside registered worktree .signals/: {signal_path}"
            )
    except OSError:
        errors.append(f"ERROR: signal file outside registered worktree .signals/: {signal_path}")

    # field mismatches
    fields = [
        ("branch", signal.get("branch"), entry.get("branch")),
        ("base", signal.get("base"), entry.get("base")),
        ("agent", signal.get("agent"), entry.get("agent")),
        ("model", signal.get("model"), entry.get("model")),
        ("prompt_sha256", signal.get("prompt_sha256"), entry.get("prompt_sha256")),
    ]
    for name, sig_val, reg_val in fields:
        if sig_val != reg_val:
            errors.append(f"ERROR: {name} mismatch: signal={sig_val} registry={reg_val}")

    # changed_files / pr_files outside reserved_files
    reserved = entry.get("reserved_files", [])
    for field_name in ("changed_files", "pr_files"):
        files = signal.get(field_name, []) or []
        for f in files:
            if not _match_reserved(f, reserved):
                errors.append(f"ERROR: {field_name} file outside reserved files: {f}")

    # commands structure
    commands = signal.get("commands", [])
    if not isinstance(commands, list):
        errors.append("ERROR: commands must be a list")
    else:
        for idx, cmd in enumerate(commands):
            if not isinstance(cmd, dict):
                errors.append(f"ERROR: commands[{idx}] is not an object")
                continue
            # every command must have exit, status, required, summary
            for key in ("exit", "status", "required", "summary"):
                if key not in cmd:
                    errors.append(f"ERROR: command '{cmd.get('cmd')}' missing '{key}'")
            # required command skipped or failed
            is_required = cmd.get("required") is True
            if is_required:
                status = cmd.get("status", "").lower()
                exit_code = cmd.get("exit")
                if status == "skipped":
                    errors.append(f"ERROR: required command '{cmd.get('cmd')}' was skipped")
                elif status == "failed" or (exit_code is not None and exit_code != 0):
                    errors.append(f"ERROR: required command '{cmd.get('cmd')}' failed")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate swarm worker signal JSON")
    parser.add_argument("--registry", required=True, help="Path to active workers JSONL")
    parser.add_argument("--signal", required=True, help="Path to worker signal JSON")
    args = parser.parse_args(argv)

    registry_path = Path(args.registry)
    signal_path = Path(args.signal)

    try:
        registry = load_registry(registry_path)
    except Exception as exc:
        print(f"ERROR: failed to load registry: {exc}", file=sys.stderr)
        return 2

    try:
        signal = json.loads(signal_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: failed to load signal: {exc}", file=sys.stderr)
        return 2

    worker_id = signal.get("worker")
    entry = registry.get(worker_id)
    if not entry:
        print(f"ERROR: worker {worker_id} not registered", file=sys.stderr)
        return 1

    errors = validate_signal(entry, signal, signal_path)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    print(f"OK: {worker_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
