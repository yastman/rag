"""Contract: curated ``update_current_span(input=...)`` payloads carry no raw PII (#2214).

The Langfuse SDK ``mask=mask_pii`` callback runs on the final serialized
payload, but ad-hoc *curated* ``input=`` dicts that developers hand-build at
``update_current_span(...)`` call sites are the place a raw phone / email /
passport literal could be introduced by mistake (e.g.
``input={"phone": "+380991234567"}``). Only ``telegram_bot/dialogs/filter_dialog.py``
masks explicitly today; nothing guards the other ~27 call sites.

This contract statically scans every ``update_current_span(...)`` /
``_update_current_span(...)`` call in production code and fails if a string
**literal** inside the ``input=`` mapping matches a PII pattern (the same
families ``src.security.pii_redaction.PIIRedactor`` redacts). It is a *shape*
guard: it does not (and cannot) catch PII that arrives via a runtime variable —
that is the SDK ``mask`` callback's job — but it stops hardcoded PII literals
and obvious unmasked raw-field payloads from landing in a curated span input.

Outcome: a developer adding ``update_current_span(input={"email": "a@b.com"})``
fails CI before merge.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

_SCAN_DIRS = (
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "src",
    REPO_ROOT / "mini_app",
    REPO_ROOT / "services",
)

_EXCLUDE_FRAGMENTS = (
    "/tests/",
    "/.venv/",
    "/__pycache__/",
    "/archive/",
    "/_obsolete/",
)

# The span-update call names this contract scans (public SDK method + the repo's
# thin ``_update_current_span(lf, ...)`` helper used by CRM handlers/dialogs).
_SPAN_UPDATE_CALL_NAMES = {"update_current_span", "_update_current_span"}

# PII literal patterns — mirror PIIRedactor families. These intentionally match
# *concrete values*, not field names, so {"phone": phone_var} (a variable) is
# fine while {"phone": "+380991234567"} (a literal) is flagged.
_PII_LITERAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"\+\d{9,14}|\b0\d{9}\b"),
    "passport": re.compile(r"\b[А-ЯІЇЄҐ]{2}\d{6}\b"),
    # 9-10 digit standalone number (Telegram user id / РНОКПП). Excludes
    # shorter ids so values like deal_id=123 do not false-positive.
    "id_number": re.compile(r"\b\d{9,10}\b"),
}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_DIRS:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if any(frag in str(py) for frag in _EXCLUDE_FRAGMENTS):
                continue
            files.append(py)
    return files


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _input_dict_arg(call: ast.Call) -> ast.Dict | None:
    """Return the ``input=`` dict literal of a span-update call, if present."""
    for kw in call.keywords:
        if kw.arg == "input" and isinstance(kw.value, ast.Dict):
            return kw.value
    return None


def _string_literals(node: ast.AST) -> list[str]:
    """Collect all str constant values nested anywhere under *node*."""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _pii_hits(text: str) -> list[str]:
    return [name for name, pat in _PII_LITERAL_PATTERNS.items() if pat.search(text)]


def _collect_violations() -> list[str]:
    violations: list[str] = []
    for py in _iter_python_files():
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = py.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node) not in _SPAN_UPDATE_CALL_NAMES:
                continue
            input_dict = _input_dict_arg(node)
            if input_dict is None:
                continue
            # Only inspect the VALUES of the input mapping (keys are field names
            # like "phone"/"email" and are expected to be present).
            for value in input_dict.values:
                if value is None:  # dict unpacking (**x) entry
                    continue
                for literal in _string_literals(value):
                    hits = _pii_hits(literal)
                    if hits:
                        violations.append(
                            f"{rel}:{node.lineno} — input= contains a raw "
                            f"{'/'.join(hits)} literal: {literal!r}"
                        )
    return violations


@pytest.fixture(scope="module")
def violations() -> list[str]:
    return _collect_violations()


def test_no_raw_pii_literal_in_span_input(violations: list[str]) -> None:
    assert not violations, (
        "Curated update_current_span(input=...) payloads must not embed raw PII "
        "literals (#2214). Use a hashed/truncated/placeholder value or a runtime "
        "variable that the SDK mask redacts. Offending sites:\n  "
        + "\n  ".join(violations)
    )


def test_scanner_finds_span_update_calls() -> None:
    """Guard against a vacuous scan: the repo must contain span-update calls
    with an ``input=`` dict for this contract to be meaningful."""
    count = 0
    for py in _iter_python_files():
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and _call_name(node) in _SPAN_UPDATE_CALL_NAMES
                and _input_dict_arg(node) is not None
            ):
                count += 1
    assert count >= 10, (
        f"Expected many update_current_span(input=...) call sites, found {count}; "
        "the PII-shape scanner may be mis-targeted (#2214)."
    )


class TestPiiShapeDetectorSelfChecks:
    """Negative/positive self-checks so the detector cannot silently rot."""

    def test_flags_raw_email_literal(self) -> None:
        tree = ast.parse('lf.update_current_span(input={"email": "john@example.com"})')
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        d = _input_dict_arg(call)
        assert d is not None
        lits = [lit for v in d.values for lit in _string_literals(v)]
        assert any(_pii_hits(lit) for lit in lits)

    def test_flags_raw_phone_literal(self) -> None:
        tree = ast.parse('lf.update_current_span(input={"phone": "+380991234567"})')
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        d = _input_dict_arg(call)
        assert d is not None
        lits = [lit for v in d.values for lit in _string_literals(v)]
        assert any("phone" in _pii_hits(lit) for lit in lits)

    def test_allows_variable_values(self) -> None:
        """A variable (runtime value) is fine — the SDK mask handles those."""
        tree = ast.parse('lf.update_current_span(input={"phone": phone_var})')
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        d = _input_dict_arg(call)
        assert d is not None
        lits = [lit for v in d.values for lit in _string_literals(v)]
        assert all(not _pii_hits(lit) for lit in lits)

    def test_allows_benign_action_literals(self) -> None:
        tree = ast.parse('lf.update_current_span(input={"action": "create", "field": "text"})')
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        d = _input_dict_arg(call)
        assert d is not None
        lits = [lit for v in d.values for lit in _string_literals(v)]
        assert all(not _pii_hits(lit) for lit in lits)

    def test_short_ids_not_flagged(self) -> None:
        """Small deal_id/task_id integers rendered as short digit strings are
        not PII-length (9-10 digits)."""
        assert not _pii_hits("123")
        assert not _pii_hits("deal-42")
