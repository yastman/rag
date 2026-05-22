"""Contract test for issue #1947 — config files must not reference dead paths.

Several configs historically carried "if-it-ever-comes-back" guards for
`legacy/`, `tests/legacy/`, `*_old.py`, and `*_backup.py`. None of these
paths or patterns currently exist in the repo. The dead rules quietly mask
the fact that the cleanup is already complete.

This test asserts:

1. `legacy/` and `tests/legacy/` directories are absent.
2. No file matching `*_old.py` or `*_backup.py` exists outside `.git`/`.venv`.
3. `pyproject.toml` does not reference these dead paths in:
     - `[tool.ruff.lint.per-file-ignores]`
     - `[tool.bandit].exclude_dirs`
     - `[tool.pylint.main].ignore`
     - `[tool.pylint.main].ignore-patterns`
     - `[tool.pytest.ini_options].norecursedirs`
     - `[tool.coverage.run].omit`
4. `.pre-commit-config.yaml` does not exclude `^legacy/` from any hook.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

import yaml

REPO = Path(__file__).resolve().parents[2]


def _all_python_files(root: Path) -> list[Path]:
    skip = {".git", ".venv", "venv", "node_modules", ".pytest_cache", ".mypy_cache"}
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in skip for part in p.parts):
            continue
        out.append(p)
    return out


def test_legacy_directories_do_not_exist() -> None:
    assert not (REPO / "legacy").exists(), (
        "legacy/ does not exist; remove guard rules that reference it"
    )
    assert not (REPO / "tests" / "legacy").exists(), (
        "tests/legacy/ does not exist; remove guard rules that reference it"
    )


def test_no_old_or_backup_python_files() -> None:
    offenders = [
        p
        for p in _all_python_files(REPO)
        if p.name.endswith(("_old.py", "_backup.py"))
    ]
    assert offenders == [], (
        f"Found *_old.py / *_backup.py files; either remove them or "
        f"re-justify the pylint ignore-patterns rule: {offenders}"
    )


def _pyproject() -> dict:
    with (REPO / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_pyproject_ruff_per_file_ignores_no_legacy() -> None:
    cfg = _pyproject()
    per_file = cfg["tool"]["ruff"]["lint"].get("per-file-ignores", {})
    for key in per_file:
        assert "legacy" not in key, (
            f"ruff per-file-ignores still references dead legacy path: {key!r}"
        )


def test_pyproject_bandit_exclude_dirs_no_legacy() -> None:
    cfg = _pyproject()
    excludes = cfg["tool"]["bandit"].get("exclude_dirs", [])
    assert "legacy" not in excludes, (
        "bandit.exclude_dirs still includes dead 'legacy' entry"
    )


def test_pyproject_pylint_ignore_no_legacy_and_no_old_backup_patterns() -> None:
    cfg = _pyproject()
    pylint_main = cfg["tool"]["pylint"]["main"]
    assert "legacy" not in pylint_main.get("ignore", []), (
        "pylint.ignore still includes dead 'legacy' entry"
    )
    assert "ignore-patterns" not in pylint_main, (
        "pylint.ignore-patterns is dead (no *_old.py/*_backup.py files exist) "
        "and must be removed"
    )


def test_pyproject_pytest_norecursedirs_no_legacy() -> None:
    cfg = _pyproject()
    norec = cfg["tool"]["pytest"]["ini_options"].get("norecursedirs", [])
    assert "tests/legacy" not in norec, (
        "pytest norecursedirs still references non-existent tests/legacy"
    )


def test_pyproject_coverage_omit_no_legacy() -> None:
    cfg = _pyproject()
    omit = cfg["tool"]["coverage"]["run"].get("omit", [])
    assert "*/legacy/*" not in omit, (
        "coverage.run.omit still references dead */legacy/* glob"
    )


def test_precommit_hooks_no_legacy_exclude() -> None:
    with (REPO / ".pre-commit-config.yaml").open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    for repo in cfg.get("repos", []):
        for hook in repo.get("hooks", []):
            exclude = hook.get("exclude")
            if not exclude:
                continue
            assert "legacy" not in exclude, (
                f"pre-commit hook {hook.get('id')!r} still excludes "
                f"dead path: {exclude!r}"
            )
