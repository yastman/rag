"""Contract: ``src/security/`` must not import ``telegram_bot`` or ``src/runtime``.

``src/security/pii_redaction.py`` (PIIRedactor) is a leaf-level utility.
Acceptable callers: ``src/observability/`` and tests.
Forbidden upward imports: ``telegram_bot.*`` or ``src.runtime.*``.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_ROOT = REPO_ROOT / "src" / "security"


def _forbidden_imports_in_file(path: Path) -> list[str]:
    """Return any forbidden import module names found in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    _FORBIDDEN = ("telegram_bot", "telegram_bot.", "src.runtime", "src.runtime.")

    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith(_FORBIDDEN):
                forbidden.append(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith(_FORBIDDEN):
                    forbidden.append(name)
    return forbidden


def test_src_security_has_no_upward_imports() -> None:
    """src/security/ must not import telegram_bot or src/runtime."""
    violations: dict[str, list[str]] = {}
    for path in sorted(SECURITY_ROOT.rglob("*.py")):
        bad = _forbidden_imports_in_file(path)
        if bad:
            violations[path.relative_to(REPO_ROOT).as_posix()] = bad

    assert not violations, (
        "#2787: src/security/ imports upward into telegram_bot or src/runtime. "
        "PIIRedactor must remain a leaf-level utility with no upward dependencies. "
        f"Violations: {violations}"
    )
