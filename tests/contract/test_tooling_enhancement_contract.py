"""Contract: tooling-enhancement plan invariants.

Pins the additions from the tooling-enhancement plan:

1. Five new dev-group deps are present in pyproject.toml:
   deptry, pip-audit, import-linter, radon, interrogate.
2. [tool.vulture] section exists with the required keys.
3. [tool.importlinter] section exists with the four architecture contracts.
4. Python version is aligned to 3.12 across ruff/mypy/pylint.
5. New Makefile targets are defined:
   deps-audit, vuln-audit, arch-lint, complexity, docs-coverage, audit.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"

_pyproject: dict | None = None


def _data() -> dict:
    global _pyproject
    if _pyproject is None:
        _pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return _pyproject


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Dev deps
# ---------------------------------------------------------------------------

NEW_DEV_DEPS = ("deptry", "pip-audit", "import-linter", "radon", "interrogate")


def test_new_dev_deps_present() -> None:
    """All five new audit tools must appear in [dependency-groups].dev."""
    dev = _data()["dependency-groups"]["dev"]
    dep_names = {
        (entry.split(">=")[0].split("==")[0].strip() if isinstance(entry, str) else "")
        for entry in dev
    }
    missing = [t for t in NEW_DEV_DEPS if t not in dep_names]
    assert missing == [], f"Missing from [dependency-groups].dev: {missing}"


# ---------------------------------------------------------------------------
# 2. [tool.vulture]
# ---------------------------------------------------------------------------

REQUIRED_VULTURE_KEYS = ("paths", "exclude", "min_confidence", "sort_by_size")


def test_vulture_section_exists() -> None:
    """[tool.vulture] must be present in pyproject.toml."""
    assert "vulture" in _data().get("tool", {}), "[tool.vulture] section missing"


def test_vulture_required_keys() -> None:
    """[tool.vulture] must have paths, exclude, min_confidence, sort_by_size."""
    vulture = _data()["tool"]["vulture"]
    missing = [k for k in REQUIRED_VULTURE_KEYS if k not in vulture]
    assert missing == [], f"[tool.vulture] missing keys: {missing}"


def test_vulture_min_confidence_value() -> None:
    """min_confidence must be 80 (keeps false-positive rate acceptable)."""
    assert _data()["tool"]["vulture"]["min_confidence"] == 80


def test_vulture_excludes_archive() -> None:
    """archive/* must be in vulture exclude list to avoid false positives."""
    excludes = _data()["tool"]["vulture"].get("exclude", [])
    assert any("archive" in str(e) for e in excludes), (
        "[tool.vulture].exclude must contain archive/* entry"
    )


# ---------------------------------------------------------------------------
# 3. [tool.importlinter]
# ---------------------------------------------------------------------------

REQUIRED_CONTRACT_NAMES = {
    "Core must not import telegram_bot",
    "Runtime must not import telegram_bot",
    "Core contracts layer is import-independent",
    "src must not import archive",
}


def test_importlinter_section_exists() -> None:
    """[tool.importlinter] must be present in pyproject.toml."""
    assert "importlinter" in _data().get("tool", {}), "[tool.importlinter] section missing"


def test_importlinter_root_packages() -> None:
    """import-linter root_packages must include src and telegram_bot."""
    roots = _data()["tool"]["importlinter"].get("root_packages", [])
    assert "src" in roots, "import-linter root_packages must include 'src'"
    assert "telegram_bot" in roots, "import-linter root_packages must include 'telegram_bot'"


def test_importlinter_contracts_present() -> None:
    """All four architecture contracts must be declared."""
    contracts = _data()["tool"]["importlinter"].get("contracts", [])
    names = {c.get("name") for c in contracts}
    missing = REQUIRED_CONTRACT_NAMES - names
    assert missing == set(), f"[tool.importlinter] missing contracts: {missing}"


# ---------------------------------------------------------------------------
# 4. Python version alignment (3.12)
# ---------------------------------------------------------------------------


def test_ruff_target_version_is_py312() -> None:
    """ruff target-version must be py312 (aligned with requires-python floor)."""
    tv = _data()["tool"]["ruff"]["target-version"]
    assert tv == "py312", f"[tool.ruff] target-version={tv!r}; expected py312"


def test_mypy_python_version_is_312() -> None:
    """mypy python_version must be 3.12 (aligned with requires-python floor)."""
    pv = _data()["tool"]["mypy"]["python_version"]
    assert pv == "3.12", f"[tool.mypy] python_version={pv!r}; expected 3.12"


def test_pylint_py_version_is_312() -> None:
    """pylint py-version must be 3.12 (aligned with requires-python floor)."""
    pv = _data()["tool"]["pylint"]["main"]["py-version"]
    assert pv == "3.12", f"[tool.pylint.main] py-version={pv!r}; expected 3.12"


# ---------------------------------------------------------------------------
# 5. Makefile targets
# ---------------------------------------------------------------------------

NEW_MAKEFILE_TARGETS = (
    "deps-audit",
    "vuln-audit",
    "arch-lint",
    "complexity",
    "docs-coverage",
    "audit",
)


def test_new_makefile_targets_defined() -> None:
    """All six new audit targets must be defined in the Makefile."""
    text = _makefile_text()
    missing = [
        t for t in NEW_MAKEFILE_TARGETS if not re.search(rf"^{re.escape(t)}:", text, re.MULTILINE)
    ]
    assert missing == [], f"Makefile missing target definitions: {missing}"


def test_vuln_audit_uses_path_venv() -> None:
    """vuln-audit must use --path .venv (works without python3-venv package)."""
    text = _makefile_text()
    match = re.search(r"^vuln-audit:.*\n(?:\t.*\n)*", text, re.MULTILINE)
    assert match, "vuln-audit target not found"
    block = match.group(0)
    assert "--path .venv" in block, "vuln-audit must use pip-audit --path .venv"


def test_audit_target_depends_on_key_tools() -> None:
    """The 'audit' target must depend on lint, type-check, security, deps-audit, vuln-audit."""
    text = _makefile_text()
    match = re.search(r"^audit:(.+?)##", text, re.MULTILINE)
    assert match, "audit: target not found in Makefile"
    deps_line = match.group(1)
    required_deps = ("lint", "type-check", "security", "deps-audit", "vuln-audit")
    missing = [d for d in required_deps if d not in deps_line]
    assert missing == [], f"audit: target missing dependencies: {missing}"
