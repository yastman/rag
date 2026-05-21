"""Contract test for Mini App frontend test-typecheck gate (#1616).

Asserts four structural invariants that close the gap where Vitest tests
under ``mini_app/frontend/src/__tests__/`` are excluded from
``tsc --noEmit`` (so stale API assertions drift from runtime types):

1. ``mini_app/frontend/tsconfig.test.json`` exists and is valid JSON
   (with comments stripped — TypeScript JSONC is allowed).

2. ``tsconfig.test.json`` includes the test glob patterns
   ``src/**/__tests__/**`` and/or ``src/**/*.test.*`` so the test files
   are actually covered by ``tsc``.

3. ``mini_app/frontend/package.json`` declares a ``typecheck:test`` script
   that invokes ``tsc --noEmit`` against ``tsconfig.test.json``.

4. ``mini_app/frontend/src/__tests__/api.test.ts`` no longer references the
   stale ``thread_id`` field — the live ``StartExpertResponse`` shape
   (see ``mini_app/expert_start.py``) returns ``start_link``,
   ``expert_name``, ``status``, and contains no ``thread_id`` member.

The check uses static parsing (regex / JSON load) — no Node toolchain is
invoked, so it runs identically on developer machines and in CI.

Refs #1616.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "mini_app" / "frontend"
TSCONFIG_TEST = FRONTEND_DIR / "tsconfig.test.json"
PACKAGE_JSON = FRONTEND_DIR / "package.json"
API_TEST = FRONTEND_DIR / "src" / "__tests__" / "api.test.ts"


def _strip_jsonc(text: str) -> str:
    """Strip ``//`` line and ``/* */`` block comments from JSONC text.

    Implemented as a tiny string-aware scanner so glob patterns like
    ``src/**/*.test.*`` inside JSON strings survive intact.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            # Line comment: skip to EOL.
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            # Block comment: skip to next ``*/``.
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    # Drop trailing commas before closing braces/brackets.
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    return cleaned


def test_tsconfig_test_json_exists_and_parses() -> None:
    """tsconfig.test.json must exist as parseable JSON(C)."""
    assert TSCONFIG_TEST.exists(), (
        f"{TSCONFIG_TEST.relative_to(REPO_ROOT)} is missing. Add it to "
        "extend tsconfig.json and include the test files so "
        "`tsc --noEmit -p tsconfig.test.json` typechecks tests."
    )
    raw = TSCONFIG_TEST.read_text()
    try:
        json.loads(_strip_jsonc(raw))
    except json.JSONDecodeError as exc:  # pragma: no cover - assertion path
        pytest.fail(
            f"{TSCONFIG_TEST.relative_to(REPO_ROOT)} is not valid JSON(C): {exc}"
        )


def test_tsconfig_test_json_includes_test_globs() -> None:
    """tsconfig.test.json must include test source globs."""
    if not TSCONFIG_TEST.exists():
        pytest.fail(
            f"{TSCONFIG_TEST.relative_to(REPO_ROOT)} missing — see "
            "test_tsconfig_test_json_exists_and_parses."
        )
    cfg = json.loads(_strip_jsonc(TSCONFIG_TEST.read_text()))
    include = cfg.get("include") or []
    expected_any = {"src/**/__tests__/**", "src/**/*.test.*"}
    assert any(glob in include for glob in expected_any), (
        f"tsconfig.test.json `include` must reference at least one of "
        f"{sorted(expected_any)} so test files are typechecked. Got: {include!r}"
    )


def test_package_json_has_typecheck_test_script() -> None:
    """package.json must wire a typecheck:test script to tsconfig.test.json."""
    pkg = json.loads(PACKAGE_JSON.read_text())
    scripts = pkg.get("scripts", {})
    assert "typecheck:test" in scripts, (
        "mini_app/frontend/package.json must declare a `typecheck:test` script "
        "that runs `tsc --noEmit -p tsconfig.test.json` (#1616)."
    )
    cmd = scripts["typecheck:test"]
    assert "tsc" in cmd and "--noEmit" in cmd, (
        f"`typecheck:test` should call `tsc --noEmit`; got: {cmd!r}"
    )
    assert "tsconfig.test.json" in cmd, (
        f"`typecheck:test` must point at tsconfig.test.json; got: {cmd!r}"
    )


def test_api_test_does_not_reference_stale_thread_id() -> None:
    """api.test.ts must not mock/assert the removed `thread_id` field.

    StartExpertResponse (mini_app/expert_start.py + mini_app/frontend/src/api.ts)
    returns ``start_link``, ``expert_name``, ``status``. The frontend test
    used to assert ``thread_id`` which is no longer part of the contract.
    """
    text = API_TEST.read_text()
    offenders = [
        (idx + 1, line)
        for idx, line in enumerate(text.splitlines())
        if "thread_id" in line
    ]
    assert not offenders, (
        "Found stale `thread_id` references in api.test.ts at lines "
        + ", ".join(str(n) for n, _ in offenders)
        + ". Update the mock/assertion to match StartExpertResponse "
        "(`start_link`, `expert_name`, `status`)."
    )
